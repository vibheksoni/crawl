"""SQLite-backed cache helpers for fetched pages."""

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_CACHE_DIR = ".crawl_cache"
DEFAULT_CACHE_FILENAME = "cache.sqlite3"
TRANSIENT_CACHE_FIELDS = {
    "cache_hit",
    "cache_not_modified",
    "cache_revalidated",
    "cache_fetched_at",
    "revalidation_status_code",
}


def resolve_cache_path(cache_dir: str | None = None) -> Path:
    """Resolve the SQLite cache database path.

    Args:
        cache_dir: Optional custom cache directory or database file path.

    Returns:
        SQLite database file path.
    """
    if not cache_dir:
        return Path(DEFAULT_CACHE_DIR) / DEFAULT_CACHE_FILENAME

    candidate = Path(cache_dir)
    if candidate.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return candidate
    return candidate / DEFAULT_CACHE_FILENAME


def open_cache_connection(cache_dir: str | None = None) -> sqlite3.Connection:
    """Open the cache database and ensure the schema exists.

    Args:
        cache_dir: Optional custom cache directory or database file path.

    Returns:
        Ready-to-use SQLite connection.
    """
    cache_path = resolve_cache_path(cache_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(cache_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_cache (
            url TEXT NOT NULL,
            mode TEXT NOT NULL,
            fetched_at REAL NOT NULL,
            page_data TEXT NOT NULL,
            PRIMARY KEY (url, mode)
        )
        """
    )
    return connection


def load_cache_entry(
    url: str,
    mode: str,
    cache_dir: str | None = None,
) -> dict | None:
    """Load a cached page entry without applying TTL logic.

    Args:
        url: Cached URL.
        mode: Requested fetch mode.
        cache_dir: Optional custom cache directory or database path.

    Returns:
        Cache entry with payload metadata or ``None``.
    """
    connection = open_cache_connection(cache_dir)
    try:
        row = connection.execute(
            "SELECT fetched_at, page_data FROM page_cache WHERE url = ? AND mode = ?",
            (url, mode),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    fetched_at, page_data = row
    try:
        parsed_page_data = json.loads(page_data)
    except json.JSONDecodeError:
        return None

    return {
        "fetched_at": float(fetched_at),
        "page_data": parsed_page_data,
    }


def is_cache_entry_fresh(
    fetched_at: float,
    cache_ttl_seconds: int | None = None,
) -> bool:
    """Check whether a cache entry is still fresh under the provided TTL.

    Args:
        fetched_at: UNIX timestamp when the cache entry was written.
        cache_ttl_seconds: Optional TTL in seconds.

    Returns:
        ``True`` when the entry is still fresh.
    """
    if cache_ttl_seconds is None:
        return True
    return time.time() - float(fetched_at) <= cache_ttl_seconds


def load_cached_page(
    url: str,
    mode: str,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
) -> dict | None:
    """Load a cached page payload when it is still valid.

    Args:
        url: Cached URL.
        mode: Requested fetch mode.
        cache_dir: Optional custom cache directory or database path.
        cache_ttl_seconds: Optional TTL in seconds.

    Returns:
        Cached payload or ``None``.
    """
    entry = load_cache_entry(url=url, mode=mode, cache_dir=cache_dir)
    if entry is None:
        return None
    if not is_cache_entry_fresh(entry["fetched_at"], cache_ttl_seconds=cache_ttl_seconds):
        return None
    return entry["page_data"]


def build_cache_revalidation_headers(page_data: dict | None) -> dict[str, str]:
    """Build conditional request headers from a cached page payload.

    Args:
        page_data: Cached page payload.

    Returns:
        Conditional header mapping.
    """
    headers = page_data.get("headers") or {} if page_data else {}
    revalidation_headers = {}
    etag = headers.get("etag") or headers.get("ETag")
    last_modified = headers.get("last-modified") or headers.get("Last-Modified")
    if etag:
        revalidation_headers["if-none-match"] = str(etag)
    if last_modified:
        revalidation_headers["if-modified-since"] = str(last_modified)
    return revalidation_headers


def merge_revalidated_page_data(
    cached_page_data: dict,
    response_page_data: dict,
    fetched_at: float | None = None,
) -> dict:
    """Merge a conditional HTTP response with an existing cached page payload.

    Args:
        cached_page_data: Previously cached page payload.
        response_page_data: Fresh HTTP response payload.
        fetched_at: Optional cache write timestamp for the cached payload.

    Returns:
        Merged page payload ready for downstream parsing.
    """
    merged_headers = dict(cached_page_data.get("headers") or {})
    merged_headers.update(response_page_data.get("headers") or {})
    merged_page_data = dict(cached_page_data)
    merged_page_data.update(
        {
            "url": response_page_data.get("url", cached_page_data.get("url")),
            "final_url": response_page_data.get("final_url", cached_page_data.get("final_url")),
            "headers": merged_headers,
            "elapsed_ms": response_page_data.get("elapsed_ms"),
            "bytes_transferred": response_page_data.get("bytes_transferred"),
            "ssl_fallback_used": response_page_data.get(
                "ssl_fallback_used",
                cached_page_data.get("ssl_fallback_used", False),
            ),
            "cache_revalidated": True,
            "cache_not_modified": response_page_data.get("status_code") == 304,
            "revalidation_status_code": response_page_data.get("status_code"),
        }
    )
    if fetched_at is not None:
        merged_page_data["cache_fetched_at"] = fetched_at
    return merged_page_data


def save_cached_page(
    url: str,
    mode: str,
    page_data: dict,
    cache_dir: str | None = None,
) -> None:
    """Persist a fetched page payload to SQLite.

    Args:
        url: Cached URL.
        mode: Requested fetch mode.
        page_data: Structured page payload to persist.
        cache_dir: Optional custom cache directory or database path.
    """
    connection = open_cache_connection(cache_dir)
    try:
        connection.execute(
            """
            INSERT INTO page_cache (url, mode, fetched_at, page_data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url, mode) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                page_data = excluded.page_data
            """,
            (
                url,
                mode,
                time.time(),
                json.dumps(
                    {
                        key: value
                        for key, value in page_data.items()
                        if key not in TRANSIENT_CACHE_FIELDS
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

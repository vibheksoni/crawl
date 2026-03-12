"""SQLite-backed cache helpers for fetched pages."""

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_CACHE_DIR = ".crawl_cache"
DEFAULT_CACHE_FILENAME = "cache.sqlite3"


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
    if cache_ttl_seconds is not None and time.time() - float(fetched_at) > cache_ttl_seconds:
        return None

    try:
        return json.loads(page_data)
    except json.JSONDecodeError:
        return None


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
            (url, mode, time.time(), json.dumps(page_data, ensure_ascii=False)),
        )
        connection.commit()
    finally:
        connection.close()

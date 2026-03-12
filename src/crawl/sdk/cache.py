"""Disk cache helpers for fetched pages."""

import hashlib
import json
import time
from pathlib import Path

DEFAULT_CACHE_DIR = ".crawl_cache"


def resolve_cache_dir(cache_dir: str | None = None) -> Path:
    """Resolve the page-cache directory.

    Args:
        cache_dir: Optional custom cache directory.

    Returns:
        Cache directory path.
    """
    return Path(cache_dir or DEFAULT_CACHE_DIR)


def build_cache_path(url: str, mode: str, cache_dir: str | None = None) -> Path:
    """Build a stable on-disk cache path for a URL and mode.

    Args:
        url: Fetched URL.
        mode: Requested fetch mode.
        cache_dir: Optional custom cache directory.

    Returns:
        File path for the cache entry.
    """
    digest = hashlib.sha256(f"{mode}:{url}".encode("utf-8")).hexdigest()
    directory = resolve_cache_dir(cache_dir)
    return directory / f"{digest}.json"


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
        cache_dir: Optional custom cache directory.
        cache_ttl_seconds: Optional TTL in seconds.

    Returns:
        Cached payload or ``None``.
    """
    cache_path = build_cache_path(url, mode, cache_dir=cache_dir)
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    fetched_at = payload.get("fetched_at")
    if cache_ttl_seconds is not None and fetched_at is not None:
        if time.time() - float(fetched_at) > cache_ttl_seconds:
            return None

    return payload.get("page_data")


def save_cached_page(
    url: str,
    mode: str,
    page_data: dict,
    cache_dir: str | None = None,
) -> None:
    """Persist a fetched page payload to disk.

    Args:
        url: Cached URL.
        mode: Requested fetch mode.
        page_data: Structured page payload to persist.
        cache_dir: Optional custom cache directory.
    """
    cache_path = build_cache_path(url, mode, cache_dir=cache_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": url,
        "mode": mode,
        "fetched_at": time.time(),
        "page_data": page_data,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

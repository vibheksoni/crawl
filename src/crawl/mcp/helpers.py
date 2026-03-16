"""Helpers for assembling MCP tool behavior on top of the SDK."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, Awaitable

from .config import (
    DEFAULT_BROWSER_CONSENT_MODE,
    DEFAULT_BROWSER_RESOURCE_MODE,
    DEFAULT_CACHE_ENABLED,
    DEFAULT_CACHE_REVALIDATE,
    DEFAULT_CACHE_TTL_SECONDS,
)
from .models import FETCH_PAGE_VIEWS, INSPECT_DEFAULT_VIEWS, SCRAPE_FORMAT_BY_VIEW


def build_cache_kwargs() -> dict[str, object]:
    """Build shared cache defaults for MCP SDK calls.

    Returns:
        Cache configuration kwargs.
    """
    return {
        "cache": DEFAULT_CACHE_ENABLED,
        "cache_ttl_seconds": DEFAULT_CACHE_TTL_SECONDS,
        "cache_revalidate": DEFAULT_CACHE_REVALIDATE,
    }


def build_page_kwargs(mode: str) -> dict[str, object]:
    """Build shared page-inspection kwargs for SDK calls.

    Args:
        mode: Requested page mode.

    Returns:
        Shared SDK kwargs.
    """
    return {
        "mode": mode,
        "consent_mode": DEFAULT_BROWSER_CONSENT_MODE,
        "max_consent_actions": 2,
        "resource_mode": DEFAULT_BROWSER_RESOURCE_MODE,
        **build_cache_kwargs(),
    }


def normalize_inspect_views(views: Iterable[str] | None) -> list[str]:
    """Normalize and de-duplicate inspect views.

    Args:
        views: Optional requested view list.

    Returns:
        Ordered normalized view list.
    """
    ordered = list(views or INSPECT_DEFAULT_VIEWS)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        value = str(item).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized or list(INSPECT_DEFAULT_VIEWS)


def scrape_formats_for_views(views: Iterable[str]) -> list[str]:
    """Build scrape formats required for a set of inspect views.

    Args:
        views: Requested inspect views.

    Returns:
        Ordered scrape format list.
    """
    formats: list[str] = []
    seen: set[str] = set()
    for view in views:
        fmt = SCRAPE_FORMAT_BY_VIEW.get(view)
        if not fmt or fmt in seen:
            continue
        seen.add(fmt)
        formats.append(fmt)
    return formats


def needs_fetch_page(views: Iterable[str]) -> bool:
    """Determine whether inspect_url needs a fetch_page call.

    Args:
        views: Requested inspect views.

    Returns:
        ``True`` when fetch_page data is required.
    """
    return any(view in FETCH_PAGE_VIEWS for view in views)


def extract_browser_details(page_result: dict) -> dict[str, object] | None:
    """Extract browser diagnostics from a fetch_page result.

    Args:
        page_result: Structured page payload.

    Returns:
        Browser diagnostics or ``None``.
    """
    details = {
        "source": page_result.get("source"),
        "fallback_used": page_result.get("fallback_used"),
        "blocked_reason": page_result.get("blocked_reason"),
        "blocked_resources": page_result.get("blocked_resources"),
        "network_idle": page_result.get("network_idle"),
        "consent_actions": page_result.get("consent_actions"),
        "interactions": page_result.get("interactions"),
    }
    filtered = {key: value for key, value in details.items() if value not in (None, [], {})}
    if filtered.get("source") == "http" and len(filtered) == 1:
        return None
    return filtered or None


async def gather_named(tasks: dict[str, Awaitable[Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    """Run named async tasks and preserve partial results on failure.

    Args:
        tasks: Mapping of task name to awaitable.

    Returns:
        Successful results and per-task error strings.
    """
    if not tasks:
        return {}, {}

    names = list(tasks)
    resolved = await asyncio.gather(*(tasks[name] for name in names), return_exceptions=True)
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, value in zip(names, resolved, strict=True):
        if isinstance(value, Exception):
            errors[name] = str(value)
            continue
        results[name] = value
    return results, errors

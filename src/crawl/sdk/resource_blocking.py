"""Browser resource blocking helpers."""

from typing import Literal

import nodriver.cdp.network as network_cdp

BrowserResourceMode = Literal["none", "safe", "aggressive"]

RESOURCE_TYPE_NAME_MAP = {
    "stylesheet": network_cdp.ResourceType.STYLESHEET,
    "image": network_cdp.ResourceType.IMAGE,
    "media": network_cdp.ResourceType.MEDIA,
    "font": network_cdp.ResourceType.FONT,
    "script": network_cdp.ResourceType.SCRIPT,
    "xhr": network_cdp.ResourceType.XHR,
    "fetch": network_cdp.ResourceType.FETCH,
}

RESOURCE_MODE_PRESETS: dict[str, list[str]] = {
    "none": [],
    "safe": [
        "image",
        "font",
        "media",
    ],
    "aggressive": [
        "image",
        "font",
        "media",
        "stylesheet",
    ],
}

RESOURCE_TYPE_CHOICES = tuple(RESOURCE_TYPE_NAME_MAP.keys())
RESOURCE_MODE_CHOICES = tuple(RESOURCE_MODE_PRESETS.keys())


def normalize_resource_type_name(value: str) -> str:
    """Normalize a resource type name.

    Args:
        value: Raw resource type name.

    Returns:
        Normalized resource type name.
    """
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def resolve_blocked_resource_type_names(
    resource_mode: BrowserResourceMode = "none",
    blocked_resource_types: list[str] | None = None,
) -> list[str]:
    """Resolve the final blocked resource type list.

    Args:
        resource_mode: Named resource blocking preset.
        blocked_resource_types: Optional custom resource type overrides to append.

    Returns:
        Normalized blocked resource type names.
    """
    resolved = []
    seen = set()
    for value in RESOURCE_MODE_PRESETS.get(resource_mode, []):
        if value not in seen:
            resolved.append(value)
            seen.add(value)
    for value in blocked_resource_types or []:
        normalized = normalize_resource_type_name(value)
        if normalized not in RESOURCE_TYPE_NAME_MAP:
            raise ValueError(f"Unsupported blocked resource type: {value}")
        if normalized not in seen:
            resolved.append(normalized)
            seen.add(normalized)
    return resolved


def resource_type_name_to_cdp(value: str) -> network_cdp.ResourceType:
    """Convert a normalized resource type name to the CDP enum.

    Args:
        value: Normalized resource type name.

    Returns:
        Matching CDP resource type.
    """
    return RESOURCE_TYPE_NAME_MAP[value]


def expand_blocked_url_pattern(value: str) -> list[str]:
    """Expand a user-friendly blocked URL pattern into wildcard URL matches.

    Args:
        value: Raw pattern or hostname.

    Returns:
        URL wildcard patterns.
    """
    pattern = value.strip()
    if not pattern:
        return []
    if "://" in pattern:
        return [pattern]
    if "/" in pattern or "*" in pattern:
        return [pattern if pattern.startswith("*://") else f"*://{pattern.lstrip('/')}"]
    host = pattern.lstrip(".")
    return [f"*://{host}/*", f"*://*.{host}/*"]


def normalize_blocked_url_patterns(values: list[str] | None = None) -> list[str]:
    """Normalize custom blocked URL patterns.

    Args:
        values: Raw wildcard URL patterns or hostnames.

    Returns:
        Deduplicated wildcard URL patterns.
    """
    resolved = []
    seen = set()
    for value in values or []:
        for pattern in expand_blocked_url_pattern(value):
            normalized = pattern.strip()
            if not normalized or normalized in seen:
                continue
            resolved.append(normalized)
            seen.add(normalized)
    return resolved

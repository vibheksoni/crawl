"""Helpers for extracting embedded hydration and structured data payloads."""

import json
from typing import Any

from bs4 import BeautifulSoup

SCRIPT_JSON_IDS = ("__NEXT_DATA__", "__NUXT_DATA__")
WINDOW_STATE_NAMES = (
    "__APOLLO_STATE__",
    "__INITIAL_STATE__",
    "__NEXT_DATA__",
    "__NUXT__",
    "__PRELOADED_STATE__",
    "__REMIX_CONTEXT__",
    "__remixContext",
    "NUXT_APP_CONFIG",
)
NEXT_DATA_MARKER = "self.__next_f.push("


def truncate_preview(value: str, limit: int = 400) -> str:
    """Trim a long script payload preview.

    Args:
        value: Payload text to shorten.
        limit: Maximum preview length.

    Returns:
        Short preview string.
    """
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def extract_balanced_value(text: str, start_index: int) -> str | None:
    """Extract a balanced JSON-like value from script text.

    Args:
        text: Script body text.
        start_index: Index immediately after an assignment or function marker.

    Returns:
        Balanced object, array, or string payload when found.
    """
    index = start_index
    while index < len(text) and text[index].isspace():
        index += 1

    if index >= len(text):
        return None

    opening = text[index]
    if opening not in {'{', '[', '"', "'"}:
        return None

    if opening in {'"', "'"}:
        quote = opening
        escaped = False
        for end_index in range(index + 1, len(text)):
            current = text[end_index]
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == quote:
                return text[index : end_index + 1]
        return None

    closing = "}" if opening == "{" else "]"
    depth = 0
    quote: str | None = None
    escaped = False

    for end_index in range(index, len(text)):
        current = text[end_index]
        if quote:
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == quote:
                quote = None
            continue

        if current in {'"', "'"}:
            quote = current
            continue

        if current == opening:
            depth += 1
            continue

        if current == closing:
            depth -= 1
            if depth == 0:
                return text[index : end_index + 1]

    return None


def parse_script_json(value: str) -> Any | None:
    """Parse a JSON payload when possible.

    Args:
        value: Raw JSON text.

    Returns:
        Parsed JSON value or ``None`` when parsing fails.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def extract_json_script_payloads(soup: BeautifulSoup) -> list[dict]:
    """Extract JSON payloads from dedicated script tags.

    Args:
        soup: Parsed page HTML.

    Returns:
        Parsed script payload entries.
    """
    entries = []

    for script_id in SCRIPT_JSON_IDS:
        script = soup.find("script", attrs={"id": script_id})
        if not script:
            continue
        raw_value = script.get_text(strip=True)
        if not raw_value:
            continue

        parsed_value = parse_script_json(raw_value)
        if parsed_value is None:
            entries.append(
                {
                    "name": script_id,
                    "kind": "script_json",
                    "parsed": False,
                    "raw_preview": truncate_preview(raw_value),
                }
            )
            continue

        entries.append(
            {
                "name": script_id,
                "kind": "script_json",
                "parsed": True,
                "value": parsed_value,
            }
        )

    return entries


def extract_json_ld_payloads(soup: BeautifulSoup) -> list[Any]:
    """Extract JSON-LD blocks from HTML.

    Args:
        soup: Parsed page HTML.

    Returns:
        Parsed JSON-LD objects.
    """
    entries = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_value = script.get_text(strip=True)
        if not raw_value:
            continue

        parsed_value = parse_script_json(raw_value)
        if parsed_value is None:
            continue

        if isinstance(parsed_value, list):
            entries.extend(parsed_value)
            continue

        entries.append(parsed_value)

    return entries


def extract_named_state_assignments(script_text: str) -> list[dict]:
    """Extract known window or self state assignments from a script body.

    Args:
        script_text: Script body text.

    Returns:
        Parsed or preview-only state assignments.
    """
    entries = []

    for state_name in WINDOW_STATE_NAMES:
        search_terms = (
            f"window.{state_name}",
            f"self.{state_name}",
            f"globalThis.{state_name}",
        )
        for search_term in search_terms:
            start_index = 0
            while True:
                marker_index = script_text.find(search_term, start_index)
                if marker_index == -1:
                    break

                equals_index = script_text.find("=", marker_index + len(search_term))
                if equals_index == -1:
                    break

                raw_value = extract_balanced_value(script_text, equals_index + 1)
                start_index = marker_index + len(search_term)
                if not raw_value:
                    continue

                parsed_value = parse_script_json(raw_value)
                if parsed_value is None:
                    entries.append(
                        {
                            "name": state_name,
                            "kind": "assignment",
                            "parsed": False,
                            "raw_preview": truncate_preview(raw_value),
                        }
                    )
                    continue

                entries.append(
                    {
                        "name": state_name,
                        "kind": "assignment",
                        "parsed": True,
                        "value": parsed_value,
                    }
                )

    return entries


def extract_next_data_chunks(script_text: str) -> list[dict]:
    """Extract Next.js App Router hydration chunks from script text.

    Args:
        script_text: Script body text.

    Returns:
        Parsed or preview-only chunk entries.
    """
    entries = []
    start_index = 0

    while True:
        marker_index = script_text.find(NEXT_DATA_MARKER, start_index)
        if marker_index == -1:
            break

        payload_index = marker_index + len(NEXT_DATA_MARKER)
        raw_value = extract_balanced_value(script_text, payload_index)
        if raw_value is None:
            break

        parsed_value = parse_script_json(raw_value)
        if parsed_value is None:
            entries.append(
                {
                    "kind": "next_f_push",
                    "parsed": False,
                    "raw_preview": truncate_preview(raw_value),
                }
            )
        else:
            entries.append(
                {
                    "kind": "next_f_push",
                    "parsed": True,
                    "value": parsed_value,
                }
            )

        start_index = payload_index + len(raw_value)

    return entries


def append_text_lines(
    value: Any,
    lines: list[str],
    prefix: str = "",
    depth: int = 0,
    max_lines: int = 400,
) -> None:
    """Flatten a nested JSON-like value into text lines.

    Args:
        value: Nested value to flatten.
        lines: Mutable output line list.
        prefix: Current value path prefix.
        depth: Current recursion depth.
        max_lines: Maximum lines to collect.
    """
    if len(lines) >= max_lines or depth > 6:
        return

    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            append_text_lines(item, lines, prefix=next_prefix, depth=depth + 1, max_lines=max_lines)
            if len(lines) >= max_lines:
                return
        return

    if isinstance(value, list):
        for index, item in enumerate(value[:20]):
            next_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            append_text_lines(item, lines, prefix=next_prefix, depth=depth + 1, max_lines=max_lines)
            if len(lines) >= max_lines:
                return
        return

    normalized = str(value).strip()
    if not normalized:
        return
    if prefix:
        lines.append(f"{prefix}: {normalized}")
    else:
        lines.append(normalized)


def render_app_state_text(app_state: dict, max_lines: int = 400, max_chars: int = 16000) -> str:
    """Render extracted app-state payloads into searchable text.

    Args:
        app_state: Embedded app-state payload map.
        max_lines: Maximum text lines to emit.
        max_chars: Maximum character count to return.

    Returns:
        Searchable flattened text.
    """
    lines: list[str] = []

    for index, item in enumerate(app_state.get("json_ld", [])):
        append_text_lines(item, lines, prefix=f"json_ld[{index}]", max_lines=max_lines)
        if len(lines) >= max_lines:
            break

    for entry in app_state.get("states", []):
        name = entry.get("name") or entry.get("kind", "state")
        if entry.get("parsed"):
            append_text_lines(entry.get("value"), lines, prefix=name, max_lines=max_lines)
        elif entry.get("raw_preview"):
            lines.append(f"{name}: {entry['raw_preview']}")
        if len(lines) >= max_lines:
            break

    for index, entry in enumerate(app_state.get("next_data", [])):
        prefix = f"next_data[{index}]"
        if entry.get("parsed"):
            append_text_lines(entry.get("value"), lines, prefix=prefix, max_lines=max_lines)
        elif entry.get("raw_preview"):
            lines.append(f"{prefix}: {entry['raw_preview']}")
        if len(lines) >= max_lines:
            break

    return "\n".join(lines)[:max_chars].rstrip()


def detect_frameworks(state_entries: list[dict], next_data_entries: list[dict]) -> list[str]:
    """Infer likely frameworks from embedded state names.

    Args:
        state_entries: Named state entries.
        next_data_entries: Next.js chunk entries.

    Returns:
        Sorted framework name list.
    """
    names = {entry.get("name") for entry in state_entries if entry.get("name")}
    frameworks = set()

    if "__NEXT_DATA__" in names or next_data_entries:
        frameworks.add("nextjs")
    if "__NUXT__" in names or "__NUXT_DATA__" in names or "NUXT_APP_CONFIG" in names:
        frameworks.add("nuxt")
    if "__APOLLO_STATE__" in names:
        frameworks.add("apollo")
    if "__INITIAL_STATE__" in names or "__PRELOADED_STATE__" in names:
        frameworks.add("redux")
    if "__REMIX_CONTEXT__" in names or "__remixContext" in names:
        frameworks.add("remix")

    return sorted(frameworks)


def dedupe_state_entries(entries: list[dict]) -> list[dict]:
    """Dedupe repeated state entries while preserving order.

    Args:
        entries: Parsed state entry list.

    Returns:
        Deduped entry list.
    """
    deduped = []
    seen_keys = set()

    for entry in entries:
        raw_preview = entry.get("raw_preview", "")
        key = (entry.get("name"), entry.get("kind"), raw_preview)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(entry)

    return deduped


def extract_app_state(html: str) -> dict:
    """Extract embedded hydration and structured payloads from HTML.

    Args:
        html: Raw page HTML.

    Returns:
        Embedded app-state payload summary and parsed data blocks.
    """
    soup = BeautifulSoup(html, "html.parser")
    state_entries = extract_json_script_payloads(soup)
    next_data_entries = []

    for script in soup.find_all("script"):
        script_text = script.get_text()
        if not script_text or not script_text.strip():
            continue
        state_entries.extend(extract_named_state_assignments(script_text))
        next_data_entries.extend(extract_next_data_chunks(script_text))

    state_entries = dedupe_state_entries(state_entries)
    frameworks = detect_frameworks(state_entries, next_data_entries)
    json_ld = extract_json_ld_payloads(soup)

    return {
        "summary": {
            "frameworks": frameworks,
            "json_ld_count": len(json_ld),
            "next_data_chunks_count": len(next_data_entries),
            "state_count": len(state_entries),
            "state_names": [entry["name"] for entry in state_entries if entry.get("name")],
        },
        "json_ld": json_ld,
        "next_data": next_data_entries,
        "states": state_entries,
    }

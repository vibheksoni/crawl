"""CLI output formatting helpers."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def get_field_value(data, field_path: str):
    """Resolve a dotted field path against nested data.

    Args:
        data: Source data.
        field_path: Dotted field path.

    Returns:
        Resolved value or ``None``.
    """
    current = data
    for part in field_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def select_fields(data, field_paths: list[str]) -> dict:
    """Select a subset of fields from nested data.

    Args:
        data: Source data.
        field_paths: Dotted field paths.

    Returns:
        Flat selected field mapping.
    """
    selected = {}
    for field_path in field_paths:
        selected[field_path] = get_field_value(data, field_path)
    return selected


def render_template(data, template: str) -> str:
    """Render a simple ``{{field.path}}`` template against data.

    Args:
        data: Source data.
        template: Template string.

    Returns:
        Rendered string.
    """
    rendered, _ = render_template_details(data, template)
    return rendered


def render_template_details(data, template: str) -> tuple[str, int]:
    """Render a template and return how many fields resolved.

    Args:
        data: Source data.
        template: Template string.

    Returns:
        Tuple of rendered string and resolved field count.
    """
    resolved_count = 0

    def replace(match: re.Match) -> str:
        nonlocal resolved_count
        field_path = match.group(1).strip()
        value = get_field_value(data, field_path)
        if value is None:
            return ""
        resolved_count += 1
        return str(value)

    return TEMPLATE_PATTERN.sub(replace, template), resolved_count


def normalize_output_rows(result) -> list[dict]:
    """Normalize command output into row dictionaries for JSONL and storage.

    Args:
        result: Command result payload.

    Returns:
        Row list.
    """
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        if isinstance(result.get("data"), list):
            return [item for item in result["data"] if isinstance(item, dict)]
        if isinstance(result.get("urls"), list):
            return [item for item in result["urls"] if isinstance(item, dict)]
        if isinstance(result.get("sources"), list):
            return [item for item in result["sources"] if isinstance(item, dict)]
        if isinstance(result.get("merged_chunks"), list):
            return [item for item in result["merged_chunks"] if isinstance(item, dict)]
        if isinstance(result.get("results"), list):
            return [item for item in result["results"] if isinstance(item, dict)]
        return [result]
    return []


def safe_segment(value: str) -> str:
    """Sanitize a string for filesystem-safe storage.

    Args:
        value: Raw segment.

    Returns:
        Safe segment.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "value"


def store_selected_fields(result, store_fields: list[str], store_dir: str | None = None) -> list[str]:
    """Store selected fields into per-host text files.

    Args:
        result: Command result payload.
        store_fields: Dotted field paths to store.
        store_dir: Optional output directory.

    Returns:
        Written file path list.
    """
    rows = normalize_output_rows(result)
    output_dir = Path(store_dir or "crawl_fields")
    output_dir.mkdir(parents=True, exist_ok=True)
    written_files = set()

    for row in rows:
        url = row.get("url") or row.get("final_url") or "unknown"
        host = safe_segment(urlparse(url).netloc or "unknown")
        host_dir = output_dir / host
        host_dir.mkdir(parents=True, exist_ok=True)

        for field_path in store_fields:
            value = get_field_value(row, field_path)
            if value is None:
                continue
            file_path = host_dir / f"{safe_segment(field_path)}.txt"
            with file_path.open("a", encoding="utf-8") as handle:
                if isinstance(value, (dict, list)):
                    handle.write(json.dumps(value, ensure_ascii=False))
                else:
                    handle.write(str(value))
                handle.write("\n")
            written_files.add(str(file_path.resolve()))

    return sorted(written_files)

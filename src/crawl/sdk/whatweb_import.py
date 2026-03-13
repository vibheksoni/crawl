"""Helpers to import declarative WhatWeb plugin definitions."""

from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_WHATWEB_PLUGIN_DIRS = []
DEFAULT_WHATWEB_OUTPUT_FILE = Path(__file__).resolve().parent / "data" / "plugin_signatures.json"

STRING_FIELD_RE = re.compile(r'(?P<field>\w+)\s+"(?P<value>(?:[^"\\]|\\.)*)"')
ATTRIBUTE_KEYS = ("account", "firmware", "filepath", "model", "module", "os", "string", "version")


def decode_ruby_string(value: str) -> str:
    """Decode a simple Ruby double-quoted string payload.

    Args:
        value: Raw string body without outer quotes.

    Returns:
        Decoded text.
    """
    return bytes(value, "utf-8").decode("unicode_escape")


def find_named_string(content: str, field: str) -> str:
    """Find a top-level WhatWeb string field.

    Args:
        content: Plugin source text.
        field: Field name such as ``name`` or ``website``.

    Returns:
        Decoded field value or an empty string.
    """
    pattern = re.compile(rf'\b{re.escape(field)}\s+"((?:[^"\\]|\\.)*)"')
    match = pattern.search(content)
    if not match:
        return ""
    return decode_ruby_string(match.group(1))


def extract_balanced_block(content: str, marker: str, opening: str, closing: str) -> str:
    """Extract a balanced block after a marker.

    Args:
        content: Source text.
        marker: Marker string preceding the block.
        opening: Opening character.
        closing: Closing character.

    Returns:
        Balanced block text including delimiters or an empty string.
    """
    marker_index = content.find(marker)
    if marker_index == -1:
        return ""
    start_index = content.find(opening, marker_index + len(marker))
    if start_index == -1:
        return ""

    depth = 0
    quote = ""
    escaped = False
    regex_mode = False

    for index in range(start_index, len(content)):
        current = content[index]
        previous = content[index - 1] if index > 0 else ""

        if quote:
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == quote:
                quote = ""
            continue

        if regex_mode:
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == "/" and previous != "\\":
                regex_mode = False
            continue

        if current in {'"', "'"}:
            quote = current
            continue
        if current == "/" and previous not in ("", " ", "\n", "\t", ",", "{", "[", "(", "=>", ":"):
            regex_mode = True
            continue
        if current == opening:
            depth += 1
            continue
        if current == closing:
            depth -= 1
            if depth == 0:
                return content[start_index : index + 1]

    return ""


def extract_hash_blocks(block: str) -> list[str]:
    """Extract top-level Ruby hash blocks from a larger block.

    Args:
        block: Source block text.

    Returns:
        Top-level hash entry strings.
    """
    hashes = []
    depth = 0
    start_index = -1
    quote = ""
    escaped = False
    regex_mode = False

    for index, current in enumerate(block):
        previous = block[index - 1] if index > 0 else ""

        if quote:
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == quote:
                quote = ""
            continue

        if regex_mode:
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == "/" and previous != "\\":
                regex_mode = False
            continue

        if current in {'"', "'"}:
            quote = current
            continue
        if current == "/" and previous in ("=", ">", " ", ",", "{", "[", "(", "\n"):
            regex_mode = True
            continue
        if current == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue
        if current == "}":
            depth -= 1
            if depth == 0 and start_index != -1:
                hashes.append(block[start_index : index + 1])
                start_index = -1
    return hashes


def extract_matches_block(content: str) -> str:
    """Extract the WhatWeb ``matches [...]`` block.

    Args:
        content: Plugin source text.

    Returns:
        Block text including brackets or an empty string.
    """
    match = re.search(r"^\s*matches\s*\[", content, flags=re.MULTILINE)
    if not match:
        return ""
    return extract_balanced_block(content[match.start() :], "matches", "[", "]")


def extract_symbol_string(entry: str, key: str) -> str:
    """Extract a Ruby symbol string value from a hash entry.

    Args:
        entry: Ruby hash entry text.
        key: Symbol name without ``:``.

    Returns:
        Decoded string value or an empty string.
    """
    patterns = [
        re.compile(rf':{re.escape(key)}\s*=>\s*"((?:[^"\\]|\\.)*)"'),
        re.compile(rf":{re.escape(key)}\s*=>\s*'((?:[^'\\]|\\.)*)'"),
    ]
    for pattern in patterns:
        match = pattern.search(entry)
        if match:
            return decode_ruby_string(match.group(1))
    return ""


def extract_symbol_int(entry: str, key: str) -> int | None:
    """Extract a Ruby symbol integer value from a hash entry.

    Args:
        entry: Ruby hash entry text.
        key: Symbol name without ``:``.

    Returns:
        Parsed integer or ``None``.
    """
    match = re.search(rf":{re.escape(key)}\s*=>\s*(\d+)", entry)
    if not match:
        return None
    return int(match.group(1))


def extract_symbol_regex(entry: str, key: str) -> str:
    """Extract a Ruby regex literal body from a hash entry.

    Args:
        entry: Ruby hash entry text.
        key: Symbol name without ``:``.

    Returns:
        Regex body string or an empty string.
    """
    marker = f":{key}"
    marker_index = entry.find(marker)
    if marker_index == -1:
        return ""
    arrow_index = entry.find("=>", marker_index)
    if arrow_index == -1:
        return ""
    slash_index = entry.find("/", arrow_index)
    if slash_index == -1:
        return ""

    escaped = False
    for index in range(slash_index + 1, len(entry)):
        current = entry[index]
        if escaped:
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == "/":
            return entry[slash_index + 1 : index]
    return ""


def map_whatweb_search_context(search: str) -> str:
    """Map a WhatWeb search context into the local grep context format.

    Args:
        search: Raw WhatWeb search context.

    Returns:
        Normalized search context.
    """
    normalized = (search or "body").strip().lower()
    if normalized in {"body", "all", "headers", "url"}:
        return normalized
    if normalized.startswith("headers["):
        return normalized
    if normalized.startswith("meta["):
        return normalized
    if normalized == "uri.path":
        return "url"
    return "body"


def parse_match_entry(entry: str) -> dict | None:
    """Parse one declarative WhatWeb hash entry into a normalized rule.

    Args:
        entry: Ruby hash entry text.

    Returns:
        Normalized rule or ``None`` when unsupported.
    """
    search = map_whatweb_search_context(extract_symbol_string(entry, "search") or "body")
    text = extract_symbol_string(entry, "text")
    regexp = extract_symbol_regex(entry, "regexp")
    version = extract_symbol_regex(entry, "version")
    rule_pattern = regexp or version
    rule_type = "regex"
    version_template = r"\1" if version else ""

    if text:
        rule_pattern = re.escape(text)
        rule_type = "text"
    if not rule_pattern:
        return None

    parsed = {
        "context": search,
        "pattern": rule_pattern,
        "type": rule_type,
        "certainty": extract_symbol_int(entry, "certainty") or 100,
        "name": extract_symbol_string(entry, "name"),
        "url": extract_symbol_string(entry, "url"),
        "status": extract_symbol_int(entry, "status"),
        "version_template": version_template,
        "md5": extract_symbol_string(entry, "md5"),
        "tagpattern": extract_symbol_string(entry, "tagpattern"),
        "attributes": {},
    }

    for key in ATTRIBUTE_KEYS:
        if key == "version":
            continue
        attribute_pattern = extract_symbol_regex(entry, key)
        if attribute_pattern:
            parsed["attributes"][key] = {"pattern": attribute_pattern, "template": r"\1"}
            continue
        attribute_text = extract_symbol_string(entry, key)
        if attribute_text:
            parsed["attributes"][key] = {"pattern": re.escape(attribute_text), "template": ""}

    return parsed


def parse_whatweb_plugin_file(path: str | Path) -> dict | None:
    """Parse one WhatWeb plugin file into a normalized record.

    Args:
        path: Plugin file path.

    Returns:
        Normalized plugin record or ``None``.
    """
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    name = find_named_string(content, "name")
    if not name:
        return None

    matches_block = extract_matches_block(content)
    rules = []
    for entry in extract_hash_blocks(matches_block):
        parsed = parse_match_entry(entry)
        if parsed is not None:
            rules.append(parsed)

    return {
        "name": name,
        "website": find_named_string(content, "website"),
        "description": find_named_string(content, "description"),
        "plugin_version": find_named_string(content, "version"),
        "rules": rules,
        "path": file_path.name,
    }


def import_whatweb_plugins(plugin_dir: str | Path, limit: int | None = None) -> dict:
    """Import all declarative WhatWeb plugin files from a directory.

    Args:
        plugin_dir: Plugin directory path.
        limit: Optional maximum plugin count.

    Returns:
        Imported plugin payload.
    """
    directory = Path(plugin_dir)
    plugins = []
    for index, file_path in enumerate(sorted(directory.glob("*.rb"))):
        if limit is not None and index >= limit:
            break
        parsed = parse_whatweb_plugin_file(file_path)
        if parsed is not None:
            plugins.append(parsed)
    return {
        "count": len(plugins),
        "plugins": plugins,
    }


def build_plugin_signature_file(
    plugin_dirs: list[str | Path],
    output_file: str | Path | None = None,
) -> str:
    """Build a bundled plugin signature cache file from one or more plugin dirs.

    Args:
        plugin_dirs: Plugin directory paths.
        output_file: Optional output file path.

    Returns:
        Absolute output file path.
    """
    combined = []
    for plugin_dir in plugin_dirs:
        payload = import_whatweb_plugins(plugin_dir)
        disabled = "disabled" in str(plugin_dir).lower()
        for plugin in payload["plugins"]:
            if disabled:
                plugin["disabled"] = True
            combined.append(plugin)

    path = Path(output_file or DEFAULT_WHATWEB_OUTPUT_FILE).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"count": len(combined), "plugins": combined}, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)

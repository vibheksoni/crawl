"""Technology fingerprinting helpers."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi.requests import Session


DEFAULT_TECH_FILE = Path(__file__).resolve().parent / "data" / "technologies.json"
DEFAULT_PLUGIN_FILE = Path(__file__).resolve().parent / "data" / "plugin_signatures.json"
TECHNOLOGY_PART_FILES = ["_"] + [chr(code) for code in range(ord("a"), ord("z") + 1)]
TECHNOLOGY_SOURCE_ROOT = "https://raw.githubusercontent.com/enthec/webappanalyzer/main/src"
EXTRACTED_ATTRIBUTE_KEYS = ("account", "firmware", "filepath", "model", "module", "os", "string")


def load_technology_definitions(tech_file: str | None = None) -> dict:
    """Load technology definitions from disk.

    Args:
        tech_file: Optional definitions file path.

    Returns:
        Parsed technology definition payload.
    """
    path = Path(tech_file or DEFAULT_TECH_FILE).resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def load_plugin_signatures(plugin_file: str | None = None) -> dict:
    """Load imported plugin signatures from disk.

    Args:
        plugin_file: Optional plugin signature file path.

    Returns:
        Parsed plugin signature payload.
    """
    path = Path(plugin_file or DEFAULT_PLUGIN_FILE).resolve()
    if not path.exists():
        return {"count": 0, "plugins": []}
    return json.loads(path.read_text(encoding="utf-8"))


def update_technology_definitions(tech_file: str | None = None) -> str:
    """Download the latest technology definitions snapshot.

    Args:
        tech_file: Optional target file path.

    Returns:
        Absolute path to the written definitions file.
    """
    path = Path(tech_file or DEFAULT_TECH_FILE).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    with Session(impersonate="chrome", timeout=30) as session:
        categories = session.get(f"{TECHNOLOGY_SOURCE_ROOT}/categories.json").json()
        technologies = {}
        for part in TECHNOLOGY_PART_FILES:
            payload = session.get(f"{TECHNOLOGY_SOURCE_ROOT}/technologies/{part}.json").json()
            if isinstance(payload, dict):
                technologies.update(payload)

    path.write_text(
        json.dumps({"technologies": technologies, "categories": categories}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(path)


def parse_rule_value(raw_value: str) -> dict:
    """Parse a technology rule value with optional metadata suffixes.

    Args:
        raw_value: Raw rule string.

    Returns:
        Parsed rule metadata.
    """
    parts = [part for part in str(raw_value).split("\\;") if part]
    rule = {
        "pattern": parts[0] if parts else "",
        "confidence": 100,
        "version": "",
    }
    for part in parts[1:]:
        if part.startswith("confidence:"):
            try:
                rule["confidence"] = max(1, int(float(part.split(":", 1)[1])))
            except ValueError:
                continue
        elif part.startswith("version:"):
            rule["version"] = part.split(":", 1)[1]
    return rule


def compile_rule(raw_value: str) -> dict | None:
    """Compile a raw technology rule into a regex-backed record.

    Args:
        raw_value: Raw rule string.

    Returns:
        Compiled rule or ``None`` when invalid.
    """
    rule = parse_rule_value(raw_value)
    pattern = rule["pattern"]
    if not pattern:
        return None
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,}", pattern)
    rule["token"] = max(tokens, key=len).lower() if tokens else ""
    return rule


def render_version(match: re.Match, template: str) -> str:
    """Render a version string from a regex match and template.

    Args:
        match: Regex match object.
        template: Version template using ``\\1`` style groups.

    Returns:
        Rendered version string.
    """
    if not template:
        return ""
    rendered = template
    for index, group in enumerate(match.groups(), start=1):
        rendered = rendered.replace(f"\\{index}", group or "")
    return rendered.strip()


@lru_cache(maxsize=50000)
def get_compiled_regex(pattern: str):
    """Compile and cache a regex pattern.

    Args:
        pattern: Regex pattern string.

    Returns:
        Compiled regex or ``None`` when invalid.
    """
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def normalize_rule_list(raw_values) -> list[dict]:
    """Normalize one or many raw rule strings into compiled rules.

    Args:
        raw_values: Raw rule string or list of strings.

    Returns:
        Compiled rule list.
    """
    if raw_values is None:
        return []
    values = raw_values if isinstance(raw_values, list) else [raw_values]
    rules = []
    for value in values:
        compiled = compile_rule(str(value))
        if compiled is not None:
            rules.append(compiled)
    return rules


def normalize_named_rules(raw_mapping: dict | None) -> dict[str, list[dict]]:
    """Normalize a named mapping of rule strings.

    Args:
        raw_mapping: Name-to-rule mapping.

    Returns:
        Name-to-compiled-rules mapping.
    """
    normalized = {}
    for name, value in (raw_mapping or {}).items():
        rules = normalize_rule_list(value)
        if rules:
            normalized[name.lower()] = rules
    return normalized


def normalize_technology_catalog(catalog: dict) -> dict:
    """Normalize raw technology definitions for matching.

    Args:
        catalog: Raw definitions payload.

    Returns:
        Normalized catalog with compiled rules.
    """
    categories = catalog.get("categories", {})
    technologies = {}
    for name, raw_definition in catalog.get("technologies", {}).items():
        cat_names = raw_definition.get("category_names")
        if not cat_names:
            cat_names = [
                categories[str(category_id)]["name"]
                for category_id in raw_definition.get("cats", [])
                if str(category_id) in categories and categories[str(category_id)].get("name")
            ]
        technologies[name] = {
            "name": name,
            "categories": cat_names or [],
            "website": raw_definition.get("website", ""),
            "html": normalize_rule_list(raw_definition.get("html")),
            "scripts": normalize_rule_list(raw_definition.get("scripts")),
            "url": normalize_rule_list(raw_definition.get("url")),
            "headers": normalize_named_rules(raw_definition.get("headers")),
            "cookies": normalize_named_rules(raw_definition.get("cookies")),
            "meta": normalize_named_rules(raw_definition.get("meta")),
            "implies": list(raw_definition.get("implies") or []),
        }
    return {"technologies": technologies, "categories": categories}


@lru_cache(maxsize=8)
def get_cached_technology_catalog(tech_file: str | None = None) -> dict:
    """Load and cache the normalized technology catalog.

    Args:
        tech_file: Optional definitions file path.

    Returns:
        Cached normalized catalog.
    """
    return normalize_technology_catalog(load_technology_definitions(tech_file))


@lru_cache(maxsize=4)
def get_cached_plugin_signatures(plugin_file: str | None = None) -> dict:
    """Load and cache imported plugin signatures.

    Args:
        plugin_file: Optional plugin signature file path.

    Returns:
        Cached plugin signature payload.
    """
    return load_plugin_signatures(plugin_file)


def extract_cookie_map(headers: dict[str, str] | None = None) -> dict[str, str]:
    """Extract cookie names and values from response headers.

    Args:
        headers: Response headers.

    Returns:
        Cookie name mapping.
    """
    values = []
    for key, value in (headers or {}).items():
        if key.lower() == "set-cookie" and value:
            values.extend([item.strip() for item in str(value).split("\n") if item.strip()])

    cookies = {}
    for item in values:
        head = item.split(";", 1)[0].strip()
        if "=" not in head:
            continue
        name, value = head.split("=", 1)
        if name:
            cookies[name.lower()] = value
    return cookies


def extract_meta_map(soup: BeautifulSoup) -> dict[str, list[str]]:
    """Extract HTML meta values keyed by name/property/http-equiv.

    Args:
        soup: Parsed page HTML.

    Returns:
        Meta key to values mapping.
    """
    meta_map: dict[str, list[str]] = {}
    for tag in soup.find_all("meta"):
        content = (tag.get("content") or "").strip()
        if not content:
            continue
        for attribute in ("name", "property", "http-equiv"):
            key = (tag.get(attribute) or "").strip().lower()
            if not key:
                continue
            meta_map.setdefault(key, [])
            if content not in meta_map[key]:
                meta_map[key].append(content)
    return meta_map


def build_page_features(url: str, html: str, headers: dict[str, str] | None = None) -> dict:
    """Build generic page features inspired by web scanner outputs.

    Args:
        url: Page URL.
        html: Raw page HTML.
        headers: Response headers.

    Returns:
        Generic page feature payload.
    """
    soup = BeautifulSoup(html, "html.parser")
    common_headers = {
        "cache-control",
        "content-length",
        "content-type",
        "date",
        "etag",
        "last-modified",
        "location",
        "server",
        "set-cookie",
        "vary",
    }
    return {
        "url": url,
        "title": soup.title.get_text(strip=True) if soup.title else "",
        "html5": "<!doctype html" in html.lower(),
        "frames": len(soup.find_all(["frame", "iframe"])),
        "open_graph": any(tag.get("property", "").lower().startswith("og:") for tag in soup.find_all("meta")),
        "script_types": sorted({(tag.get("type") or "text/javascript").strip() for tag in soup.find_all("script") if tag.get("type")}),
        "http_server": (headers or {}).get("server", ""),
        "x_powered_by": (headers or {}).get("x-powered-by", "") or (headers or {}).get("X-Powered-By", ""),
        "uncommon_headers": sorted(
            key for key in ((headers or {}).keys()) if key.lower() not in common_headers
        ),
        "cookie_names": sorted(extract_cookie_map(headers).keys()),
    }


def build_tag_pattern(soup: BeautifulSoup) -> str:
    """Build a simple WhatWeb-style HTML tag pattern string.

    Args:
        soup: Parsed page HTML.

    Returns:
        Comma-delimited tag pattern.
    """
    parts = []
    for node in soup.find_all(True):
        parts.append(node.name)
    return ",".join(parts)


def resolve_search_contexts(url: str, html: str, headers: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Build grep/search contexts from page signals.

    Args:
        url: Page URL.
        html: Raw page HTML.
        headers: Response headers.

    Returns:
        Context name to values mapping.
    """
    soup = BeautifulSoup(html, "html.parser")
    body_md5 = hashlib.md5(html.encode("utf-8", errors="ignore")).hexdigest()
    contexts = {
        "body": [html],
        "all": ["\n".join([*(f"{k}: {v}" for k, v in (headers or {}).items()), html])],
        "url": [url],
        "headers": [f"{k}: {v}" for k, v in (headers or {}).items()],
        "script": [(script.get("src") or script.get_text(" ", strip=True) or "").strip() for script in soup.find_all("script")],
        "tagpattern": [build_tag_pattern(soup)],
        "md5": [body_md5],
    }
    meta_map = extract_meta_map(soup)
    for key, values in meta_map.items():
        contexts[f"meta[{key}]"] = values
    for key, value in (headers or {}).items():
        contexts[f"headers[{key.lower()}]"] = [str(value)]
    return contexts


def apply_rules_to_values(values: list[str], rules: list[dict], matched_on: str) -> list[dict]:
    """Apply compiled rules to a list of values.

    Args:
        values: Candidate strings.
        rules: Compiled rule list.
        matched_on: Match context label.

    Returns:
        Evidence payloads.
    """
    evidence = []
    for value in values:
        lowered_value = value.lower()
        for rule in rules:
            token = rule.get("token", "")
            if token and token not in lowered_value:
                continue
            regex = get_compiled_regex(rule["pattern"])
            if regex is None:
                continue
            match = regex.search(value)
            if not match:
                continue
            evidence.append(
                {
                    "matched_on": matched_on,
                    "pattern": rule["pattern"],
                    "confidence": rule["confidence"],
                    "version": render_version(match, rule["version"]),
                }
            )
    return evidence


def build_technology_signals(url: str, html: str, headers: dict[str, str] | None = None) -> dict:
    """Prepare reusable signals for technology matching.

    Args:
        url: Page URL.
        html: Raw page HTML.
        headers: Response headers.

    Returns:
        Prepared page signals.
    """
    soup = BeautifulSoup(html, "html.parser")
    script_values = []
    for script in soup.find_all("script"):
        src = (script.get("src") or "").strip()
        if src:
            script_values.append(src)
    return {
        "url": url,
        "html": html,
        "headers": headers or {},
        "cookies": extract_cookie_map(headers),
        "meta": extract_meta_map(soup),
        "scripts": script_values,
    }


def collect_technology_evidence(
    definition: dict,
    signals: dict,
    aggression: int = 1,
) -> list[dict]:
    """Collect technology evidence for one definition.

    Args:
        definition: Normalized technology definition.
        signals: Prepared page signals.
        aggression: Matching aggression level.

    Returns:
        Evidence list for the technology.
    """
    evidence = []
    evidence.extend(apply_rules_to_values([signals["url"]], definition["url"], "url"))
    if aggression >= 2:
        evidence.extend(apply_rules_to_values(signals["scripts"], definition["scripts"], "script"))
    if aggression >= 3:
        evidence.extend(apply_rules_to_values([signals["html"]], definition["html"], "html"))

    for header_name, rules in definition["headers"].items():
        header_values = []
        for key, value in signals["headers"].items():
            if key.lower() == header_name:
                header_values.append(str(value))
        evidence.extend(apply_rules_to_values(header_values, rules, f"header:{header_name}"))

    for cookie_name, rules in definition["cookies"].items():
        cookie_value = signals["cookies"].get(cookie_name)
        if cookie_value is None:
            continue
        evidence.extend(apply_rules_to_values([cookie_value], rules, f"cookie:{cookie_name}"))

    for meta_name, rules in definition["meta"].items():
        evidence.extend(apply_rules_to_values(signals["meta"].get(meta_name, []), rules, f"meta:{meta_name}"))

    return evidence


def search_technology_definitions(
    search: str | None = None,
    tech_file: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search available technology definitions by keyword.

    Args:
        search: Optional keyword filter.
        tech_file: Optional definitions file path.
        limit: Maximum results to return.

    Returns:
        Matching technology records.
    """
    catalog = get_cached_technology_catalog(tech_file)
    plugin_payload = get_cached_plugin_signatures()
    needle = (search or "").strip().lower()
    results = []
    for definition in catalog["technologies"].values():
        haystack = " ".join([definition["name"], definition["website"], *definition["categories"]]).lower()
        if needle and needle not in haystack:
            continue
        results.append(
            {
                "name": definition["name"],
                "categories": definition["categories"],
                "website": definition["website"],
                "implies": definition["implies"],
                "source": "definitions",
            }
        )
    for plugin in plugin_payload.get("plugins", []):
        haystack = " ".join([plugin["name"], plugin.get("website", ""), plugin.get("description", "")]).lower()
        if needle and needle not in haystack:
            continue
        results.append(
            {
                "name": plugin["name"],
                "categories": ["Imported Signatures"],
                "website": plugin.get("website", ""),
                "implies": [],
                "source": "signature_plugins",
                "disabled": bool(plugin.get("disabled")),
            }
        )
    merged = {}
    for item in results:
        existing = merged.get(item["name"])
        if existing is None:
            merged[item["name"]] = item
            continue
        existing_sources = set(str(existing.get("source", "")).split(","))
        existing_sources.add(item.get("source", ""))
        existing["source"] = ",".join(sorted(source for source in existing_sources if source))
        existing["disabled"] = bool(existing.get("disabled")) and bool(item.get("disabled"))
    deduped = sorted(merged.values(), key=lambda item: item["name"].lower())
    return deduped[: max(1, limit)]


def match_plugin_rule(rule: dict, contexts: dict[str, list[str]], url: str, status_code: int | None = None) -> dict | None:
    """Match one imported plugin rule against prepared contexts.

    Args:
        rule: Imported plugin rule.
        contexts: Prepared search contexts.
        url: Page URL.
        status_code: Optional HTTP status code.

    Returns:
        Match payload or ``None``.
    """
    if rule.get("status") is not None and status_code != rule["status"]:
        return None
    if rule.get("url"):
        expected = rule["url"]
        if expected not in url:
            return None

    if rule.get("md5"):
        values = contexts.get("md5", [])
        if rule["md5"] not in values:
            return None
        return {
            "matched_on": "md5",
            "confidence": rule.get("certainty", 100),
            "version": "",
            "attributes": {},
        }

    if rule.get("tagpattern"):
        values = contexts.get("tagpattern", [])
        if rule["tagpattern"] not in values:
            return None
        return {
            "matched_on": "tagpattern",
            "confidence": rule.get("certainty", 100),
            "version": "",
            "attributes": {},
        }

    values = [value for value in contexts.get(rule.get("context", "body"), []) if value]
    regex = get_compiled_regex(rule["pattern"])
    if regex is None:
        return None

    for value in values:
        match = regex.search(value)
        if not match:
            continue
        attributes = {}
        for key, attribute in rule.get("attributes", {}).items():
            attribute_regex = get_compiled_regex(attribute["pattern"])
            if attribute_regex is None:
                continue
            attribute_match = attribute_regex.search(value)
            if not attribute_match:
                continue
            rendered = render_version(attribute_match, attribute.get("template", ""))
            attributes[key] = rendered if rendered else attribute_match.group(0)
        return {
            "matched_on": rule.get("context", "body"),
            "confidence": rule.get("certainty", 100),
            "version": render_version(match, rule.get("version_template", "")),
            "attributes": attributes,
            "name": rule.get("name", ""),
        }
    return None


def fingerprint_imported_plugins(
    url: str,
    html: str,
    headers: dict[str, str] | None = None,
    plugin_file: str | None = None,
    aggression: int = 1,
    status_code: int | None = None,
) -> list[dict]:
    """Fingerprint imported plugin signatures against a page.

    Args:
        url: Page URL.
        html: Raw page HTML.
        headers: Response headers.
        plugin_file: Optional plugin signature file path.
        aggression: Matching aggression level.
        status_code: Optional HTTP status code.

    Returns:
        Matched plugin payloads.
    """
    contexts = resolve_search_contexts(url, html, headers=headers)
    payload = get_cached_plugin_signatures(plugin_file)
    matches = []

    for plugin in payload.get("plugins", []):
        evidence = []
        for rule in plugin.get("rules", []):
            if aggression <= 1 and rule.get("url"):
                continue
            matched = match_plugin_rule(rule, contexts, url=url, status_code=status_code)
            if matched is not None:
                evidence.append(matched)
        if not evidence:
            continue

        versions = sorted({item["version"] for item in evidence if item["version"]})
        collected_attributes = {key: [] for key in EXTRACTED_ATTRIBUTE_KEYS}
        for item in evidence:
            for key, value in item.get("attributes", {}).items():
                if value and value not in collected_attributes.setdefault(key, []):
                    collected_attributes[key].append(value)

        matches.append(
            {
                "name": plugin["name"],
                "categories": ["Imported Signatures"],
                "website": plugin.get("website", ""),
                "confidence": min(100, sum(item["confidence"] for item in evidence)),
                "versions": versions,
                "version": versions[0] if versions else "",
                "matched_on": sorted({item["matched_on"] for item in evidence}),
                "evidence": evidence,
                "description": plugin.get("description", ""),
                "plugin_version": plugin.get("plugin_version", ""),
                "source": "signature_plugins",
                "attributes": {key: value for key, value in collected_attributes.items() if value},
            }
        )

    matches.sort(key=lambda item: (item["confidence"], item["name"].lower()), reverse=True)
    return matches


def get_technology_definition(name: str, tech_file: str | None = None) -> dict | None:
    """Get one technology definition by exact name.

    Args:
        name: Technology name.
        tech_file: Optional definitions file path.

    Returns:
        Matching technology definition or ``None``.
    """
    catalog = get_cached_technology_catalog(tech_file)
    plugin_match = next((plugin for plugin in get_cached_plugin_signatures().get("plugins", []) if plugin["name"] == name), None)
    if name in catalog["technologies"]:
        definition = dict(catalog["technologies"][name])
        definition["source"] = "definitions,signature_plugins" if plugin_match else "definitions"
        if plugin_match:
            definition["plugin_signature"] = plugin_match
        return definition
    if plugin_match:
        definition = dict(plugin_match)
        definition["source"] = "signature_plugins"
        return definition
    return None


def fingerprint_page(
    url: str,
    html: str,
    headers: dict[str, str] | None = None,
    tech_file: str | None = None,
    include_implied: bool = True,
    aggression: int = 1,
    status_code: int | None = None,
    plugin_file: str | None = None,
) -> dict:
    """Fingerprint technologies and generic page features from a response.

    Args:
        url: Page URL.
        html: Raw page HTML.
        headers: Response headers.
        tech_file: Optional definitions file path.
        include_implied: Whether implied technologies should be expanded.
        aggression: Matching aggression level.
        status_code: Optional HTTP status code.
        plugin_file: Optional imported plugin signature file path.

    Returns:
        Fingerprint payload.
    """
    catalog = get_cached_technology_catalog(tech_file)
    signals = build_technology_signals(url, html, headers=headers)
    matched = {}

    for name, definition in catalog["technologies"].items():
        evidence = collect_technology_evidence(definition, signals, aggression=aggression)
        if not evidence:
            continue
        versions = sorted({item["version"] for item in evidence if item["version"]})
        matched[name] = {
            "name": name,
            "categories": definition["categories"],
            "website": definition["website"],
            "confidence": min(100, sum(item["confidence"] for item in evidence)),
            "versions": versions,
            "version": versions[0] if versions else "",
            "matched_on": sorted({item["matched_on"] for item in evidence}),
            "implies": definition["implies"],
            "evidence": evidence,
            "source": "definitions",
        }

    if include_implied:
        pending = list(matched.values())
        while pending:
            current = pending.pop(0)
            for implied_name in current.get("implies", []):
                if implied_name in matched:
                    continue
                implied = catalog["technologies"].get(implied_name)
                if not implied:
                    continue
                matched[implied_name] = {
                    "name": implied_name,
                    "categories": implied["categories"],
                    "website": implied["website"],
                    "confidence": 100,
                    "versions": [],
                    "version": "",
                    "matched_on": ["implied"],
                    "implies": implied["implies"],
                    "evidence": [],
                    "implied_by": [current["name"]],
                }
                pending.append(matched[implied_name])

    technologies = sorted(
        matched.values(),
        key=lambda item: (item["confidence"], item["name"].lower()),
        reverse=True,
    )
    imported_plugins = fingerprint_imported_plugins(
        url,
        html,
        headers=headers,
        plugin_file=plugin_file,
        aggression=aggression,
        status_code=status_code,
    )
    combined = {item["name"]: item for item in technologies}
    for item in imported_plugins:
        if item["name"] in combined:
            existing = combined[item["name"]]
            existing["confidence"] = max(existing["confidence"], item["confidence"])
            existing["matched_on"] = sorted(set(existing.get("matched_on", [])) | set(item.get("matched_on", [])))
            existing["evidence"] = existing.get("evidence", []) + item.get("evidence", [])
            if not existing.get("version") and item.get("version"):
                existing["version"] = item["version"]
            if item.get("version"):
                versions = set(existing.get("versions", []))
                versions.update(item.get("versions", []))
                existing["versions"] = sorted(versions)
            existing.setdefault("attributes", {})
            for key, values in item.get("attributes", {}).items():
                target = existing["attributes"].setdefault(key, [])
                for value in values:
                    if value not in target:
                        target.append(value)
            existing["source"] = "combined"
        else:
            combined[item["name"]] = item
    technologies = sorted(
        combined.values(),
        key=lambda item: (item["confidence"], item["name"].lower()),
        reverse=True,
    )
    return {
        "url": url,
        "count": len(technologies),
        "aggression": aggression,
        "technologies": technologies,
        "page_features": build_page_features(url, html, headers=headers),
    }


def grep_page(
    url: str,
    html: str,
    headers: dict[str, str] | None = None,
    text: str | None = None,
    regex: str | None = None,
    search: str = "body",
) -> dict:
    """Search a page context for a literal string or regex.

    Args:
        url: Page URL.
        html: Raw page HTML.
        headers: Response headers.
        text: Optional case-insensitive literal match.
        regex: Optional regex pattern.
        search: Search context.

    Returns:
        Grep result payload.
    """
    contexts = resolve_search_contexts(url, html, headers=headers)
    values = [value for value in contexts.get(search, []) if value]
    matches = []

    if text:
        lowered = text.lower()
        matches.extend(value for value in values if lowered in value.lower())

    if regex:
        compiled = re.compile(regex, re.IGNORECASE)
        matches.extend(value for value in values if compiled.search(value))

    deduped = []
    seen = set()
    for value in matches:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)

    return {
        "url": url,
        "search": search,
        "matched": bool(deduped),
        "count": len(deduped),
        "matches": deduped,
    }

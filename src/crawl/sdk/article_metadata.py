"""Article metadata extraction helpers."""

import html
import json
import re
from datetime import datetime

from bs4 import BeautifulSoup

ARTICLE_JSONLD_TYPES = {
    "analysisnewsarticle",
    "article",
    "blogposting",
    "liveblogposting",
    "newsarticle",
    "opinionnewsarticle",
    "reportagenewsarticle",
    "reviewnewsarticle",
    "techarticle",
}
AUTHOR_META_KEYS = (
    "author",
    "article_author",
    "dc.creator",
    "nydn_byline",
    "parsely-author",
    "sailthru.author",
)
PUBLISHED_META_KEYS = (
    "article:published_time",
    "article_date_original",
    "date",
    "datepublished",
    "parsely-pub-date",
    "publish_date",
    "publication_date",
    "pub_date",
    "sailthru.date",
)
MODIFIED_META_KEYS = (
    "article:modified_time",
    "article_date_updated",
    "date_modified",
    "datemodified",
    "lastmodified",
    "modified_time",
)
SITE_NAME_META_KEYS = (
    "application-name",
    "article_publication_name",
    "og:site_name",
    "site_name",
)
TITLE_META_KEYS = (
    "og:title",
    "parsely-title",
    "sailthru.title",
    "title",
    "twitter:title",
)
DESCRIPTION_META_KEYS = (
    "description",
    "og:description",
    "twitter:description",
)
IMAGE_META_KEYS = (
    "image",
    "og:image",
    "thumbnail",
    "thumbnailurl",
    "twitter:image",
    "twitter:image:src",
)
SECTION_META_KEYS = (
    "article:section",
    "articlesection",
    "content_section",
    "parsely-section",
    "section",
)
KEYWORDS_META_KEYS = (
    "keywords",
    "news_keywords",
)


def normalize_metadata_text(value) -> str:
    """Normalize metadata text values.

    Args:
        value: Raw metadata value.

    Returns:
        Cleaned text string.
    """
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_iso_datetime(value: str | None) -> str | None:
    """Parse a wide range of date strings into ISO-8601 format.

    Args:
        value: Raw date string.

    Returns:
        ISO-8601 string or ``None``.
    """
    normalized_value = normalize_metadata_text(value)
    if not normalized_value:
        return None
    normalized_value = normalized_value.replace("Z", "+00:00") if normalized_value.endswith("Z") else normalized_value
    for pattern in (
        "%A, %B %d, %Y, %I:%M %p",
        "%A, %B %d, %Y, %H:%M %p",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%y-%m-%d",
        "%Y%m%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(normalized_value, pattern).isoformat()
        except ValueError:
            continue
    return normalized_value


def normalize_author_name(value: str) -> str:
    """Normalize a candidate author name.

    Args:
        value: Raw author value.

    Returns:
        Cleaned author name or an empty string.
    """
    text = normalize_metadata_text(value)
    text = re.sub(r"^[Bb]y\s+", "", text)
    text = re.sub(r"\s+\|\s+.*$", "", text)
    text = re.sub(r"\s+[\(<].*$", "", text)
    text = re.sub(r"\s+\d+$", "", text)
    return text.strip(" ,;:-")


def split_author_candidates(value) -> list[str]:
    """Split author metadata into distinct author names.

    Args:
        value: Raw author payload.

    Returns:
        Deduped author list.
    """
    if value is None:
        return []
    if isinstance(value, list):
        authors = []
        for item in value:
            authors.extend(split_author_candidates(item))
        return dedupe_strings(authors)
    if isinstance(value, dict):
        for key in ("name", "author", "creator"):
            if key in value:
                return split_author_candidates(value[key])
        return []

    text = normalize_metadata_text(value)
    if not text:
        return []
    pieces = re.split(r"\s*(?:,| and | \| |;)\s*", text)
    authors = [normalize_author_name(piece) for piece in pieces]
    authors = [author for author in authors if len(author) >= 2 and not re.search(r"https?://", author)]
    return dedupe_strings(authors)


def split_keyword_candidates(value) -> list[str]:
    """Split keyword metadata into distinct values.

    Args:
        value: Raw keyword payload.

    Returns:
        Deduped keyword list.
    """
    if value is None:
        return []
    if isinstance(value, list):
        keywords = []
        for item in value:
            keywords.extend(split_keyword_candidates(item))
        return dedupe_strings(keywords)
    text = normalize_metadata_text(value)
    if not text:
        return []
    return dedupe_strings(re.split(r"\s*,\s*", text))


def dedupe_strings(values: list[str]) -> list[str]:
    """Dedupe non-empty strings while preserving order.

    Args:
        values: Candidate values.

    Returns:
        Deduped string list.
    """
    deduped = []
    seen = set()
    for value in values:
        normalized = normalize_metadata_text(value)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(normalized)
    return deduped


def extract_meta_map(soup: BeautifulSoup) -> dict[str, list[str]]:
    """Extract a normalized meta-tag map.

    Args:
        soup: Parsed document tree.

    Returns:
        Meta values keyed by normalized name/property/itemprop.
    """
    meta_map: dict[str, list[str]] = {}
    for meta in soup.find_all("meta"):
        key = meta.get("property") or meta.get("name") or meta.get("itemprop") or meta.get("http-equiv")
        content = meta.get("content")
        if not key or content is None:
            continue
        normalized_key = normalize_metadata_text(key).lower()
        normalized_content = normalize_metadata_text(content)
        if not normalized_content:
            continue
        meta_map.setdefault(normalized_key, []).append(normalized_content)
    return meta_map


def get_first_meta_value(meta_map: dict[str, list[str]], keys: tuple[str, ...]) -> str:
    """Return the first matching meta value for a list of keys.

    Args:
        meta_map: Normalized meta map.
        keys: Candidate meta keys.

    Returns:
        First matching value or an empty string.
    """
    for key in keys:
        values = meta_map.get(key.lower())
        if values:
            return values[0]
    return ""


def extract_canonical_link(soup: BeautifulSoup) -> str:
    """Extract a canonical URL from ``<link rel='canonical'>`` when present.

    Args:
        soup: Parsed document tree.

    Returns:
        Canonical URL or an empty string.
    """
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        return normalize_metadata_text(canonical.get("href"))
    return ""


def parse_embedded_metadata_json(value: str) -> dict:
    """Parse embedded metadata JSON stored inside meta tags.

    Args:
        value: Raw meta-tag content.

    Returns:
        Parsed dictionary or an empty mapping.
    """
    text = normalize_metadata_text(value)
    if not text or not text.startswith("{"):
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def extract_embedded_site_name(soup: BeautifulSoup) -> str:
    """Extract publisher site name from embedded site-configuration nodes.

    Args:
        soup: Parsed document tree.

    Returns:
        Site name hint or an empty string.
    """
    node = soup.find(attrs={"data-parsely-site": True})
    if node and node.get("data-parsely-site"):
        return normalize_metadata_text(node.get("data-parsely-site"))
    return ""


def collect_jsonld_candidates(soup: BeautifulSoup) -> list[dict]:
    """Collect JSON-LD objects that may describe the article.

    Args:
        soup: Parsed document tree.

    Returns:
        Candidate JSON-LD dictionaries.
    """
    candidates = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_text = script.string or script.get_text()
        raw_text = raw_text.strip() if raw_text else ""
        if not raw_text:
            continue
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            continue
        for item in flatten_jsonld_payload(payload):
            item_type = normalize_metadata_text(item.get("@type", "")).lower()
            if item_type in ARTICLE_JSONLD_TYPES:
                candidates.append(item)
    return candidates


def flatten_jsonld_payload(payload) -> list[dict]:
    """Flatten JSON-LD data into a list of dictionaries.

    Args:
        payload: Parsed JSON-LD payload.

    Returns:
        Flat list of candidate objects.
    """
    if isinstance(payload, dict):
        if "@graph" in payload and isinstance(payload["@graph"], list):
            return [item for item in payload["@graph"] if isinstance(item, dict)]
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def pick_best_jsonld_candidate(candidates: list[dict]) -> dict:
    """Pick the richest JSON-LD candidate.

    Args:
        candidates: Candidate JSON-LD objects.

    Returns:
        Best candidate or an empty mapping.
    """
    if not candidates:
        return {}
    return max(
        candidates,
        key=lambda item: (
            bool(item.get("headline") or item.get("name")),
            bool(item.get("author") or item.get("creator")),
            bool(item.get("datePublished") or item.get("dateCreated")),
            bool(item.get("publisher")),
        ),
    )


def estimate_reading_time_minutes(text: str, words_per_minute: int = 220) -> int:
    """Estimate reading time from article text.

    Args:
        text: Article text.
        words_per_minute: Reading-speed assumption.

    Returns:
        Estimated reading time in minutes.
    """
    word_count = len(re.findall(r"\w+", text or ""))
    if word_count == 0:
        return 0
    return max(1, round(word_count / max(1, words_per_minute)))


def extract_body_author_candidates(soup: BeautifulSoup) -> list[str]:
    """Extract author names from visible byline-like elements.

    Args:
        soup: Parsed document tree.

    Returns:
        Candidate author list.
    """
    for selector in (
        "article [rel='author']",
        "main [rel='author']",
        "article [itemprop='author']",
        "main [itemprop='author']",
        "article .author",
        "main .author",
        "article .byline",
        "main .byline",
        "article .post-author",
        "main .post-author",
        "article .entry-author",
        "main .entry-author",
        "article .article-author",
        "main .article-author",
        "article a[href*='/authors/']",
        "main a[href*='/authors/']",
        "header a[href*='/authors/']",
    ):
        authors = []
        selected_nodes = soup.select(selector)
        if "/authors/" in selector and selected_nodes:
            selected_nodes = selected_nodes[:1]
        for node in selected_nodes:
            authors.extend(split_author_candidates(node.get_text(" ", strip=True)))
        authors = dedupe_strings(authors)
        if authors:
            return authors[:4]
    return []


def extract_body_date_candidates(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Extract publish and modified dates from visible time nodes.

    Args:
        soup: Parsed document tree.

    Returns:
        Tuple of published and modified ISO strings.
    """
    published = None
    modified = None

    for selector in ("time[itemprop='datePublished']", "time.published", ".published time", ".post-date time"):
        node = soup.select_one(selector)
        if node:
            published = parse_iso_datetime(node.get("datetime") or node.get_text(" ", strip=True))
            if published:
                break

    if published is None:
        for selector in ("article time", "main time"):
            nodes = soup.select(selector)
            if nodes:
                published = parse_iso_datetime(nodes[0].get("datetime") or nodes[0].get_text(" ", strip=True))
                if len(nodes) > 1:
                    modified = parse_iso_datetime(nodes[1].get("datetime") or nodes[1].get_text(" ", strip=True))
                break

    for selector in ("time[itemprop='dateModified']", "time.updated", ".updated time", ".post-modified time"):
        node = soup.select_one(selector)
        if node:
            modified = parse_iso_datetime(node.get("datetime") or node.get_text(" ", strip=True))
            if modified:
                break

    return published, modified


def extract_article_metadata(html_text: str, article_text: str = "") -> dict:
    """Extract rich article metadata from JSON-LD, meta tags, and body cues.

    Args:
        html_text: Raw HTML content.
        article_text: Extracted article text for reading-time estimation.

    Returns:
        Normalized article metadata payload.
    """
    soup = BeautifulSoup(html_text or "", "html.parser")
    meta_map = extract_meta_map(soup)
    parsely_page = parse_embedded_metadata_json(get_first_meta_value(meta_map, ("parsely-page",)))
    jsonld_candidate = pick_best_jsonld_candidate(collect_jsonld_candidates(soup))
    body_authors = extract_body_author_candidates(soup)
    body_published, body_modified = extract_body_date_candidates(soup)

    title = normalize_metadata_text(
        jsonld_candidate.get("headline")
        or jsonld_candidate.get("name")
        or parsely_page.get("title")
        or get_first_meta_value(meta_map, TITLE_META_KEYS)
        or (soup.title.get_text(" ", strip=True) if soup.title else "")
    )
    description = normalize_metadata_text(
        jsonld_candidate.get("description")
        or get_first_meta_value(meta_map, DESCRIPTION_META_KEYS)
    )
    site_name = normalize_metadata_text(
        (jsonld_candidate.get("publisher") or {}).get("name")
        if isinstance(jsonld_candidate.get("publisher"), dict)
        else ""
    ) or get_first_meta_value(meta_map, SITE_NAME_META_KEYS) or extract_embedded_site_name(soup)
    canonical_url = normalize_metadata_text(
        jsonld_candidate.get("url")
        or parsely_page.get("link")
        or extract_canonical_link(soup)
        or get_first_meta_value(meta_map, ("og:url", "twitter:url"))
    )
    section = normalize_metadata_text(
        jsonld_candidate.get("articleSection")
        or parsely_page.get("section")
        or get_first_meta_value(meta_map, SECTION_META_KEYS)
    )
    image = normalize_metadata_text(
        jsonld_candidate.get("thumbnailUrl")
        or jsonld_candidate.get("image")
        or parsely_page.get("image_url")
        or get_first_meta_value(meta_map, IMAGE_META_KEYS)
    )
    language = normalize_metadata_text(
        soup.html.get("lang", "") if soup.html else ""
    ) or get_first_meta_value(meta_map, ("lang", "content-language", "og:locale"))

    authors = dedupe_strings(
        split_author_candidates(jsonld_candidate.get("author"))
        + split_author_candidates(jsonld_candidate.get("creator"))
        + split_author_candidates(parsely_page.get("author"))
        + split_author_candidates(parsely_page.get("authors"))
        + split_author_candidates(get_first_meta_value(meta_map, AUTHOR_META_KEYS))
        + body_authors
    )

    published = (
        parse_iso_datetime(jsonld_candidate.get("datePublished"))
        or parse_iso_datetime(jsonld_candidate.get("dateCreated"))
        or parse_iso_datetime(parsely_page.get("pub_date"))
        or parse_iso_datetime(get_first_meta_value(meta_map, PUBLISHED_META_KEYS))
        or body_published
    )
    modified = (
        parse_iso_datetime(jsonld_candidate.get("dateModified"))
        or parse_iso_datetime(get_first_meta_value(meta_map, MODIFIED_META_KEYS))
        or body_modified
    )

    keywords = dedupe_strings(
        split_keyword_candidates(jsonld_candidate.get("keywords"))
        + split_keyword_candidates(parsely_page.get("tags"))
        + split_keyword_candidates(get_first_meta_value(meta_map, KEYWORDS_META_KEYS))
    )
    reading_time_minutes = estimate_reading_time_minutes(article_text)

    return {
        "title": title,
        "description": description,
        "site_name": site_name,
        "authors": authors,
        "author": authors[0] if authors else "",
        "date_published": published,
        "date_modified": modified,
        "section": section,
        "keywords": keywords,
        "canonical_url": canonical_url,
        "image": image,
        "language": language,
        "reading_time_minutes": reading_time_minutes,
    }

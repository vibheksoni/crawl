"""Feed discovery and validation helpers."""

import json
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

FEED_CONTENT_TYPES = {
    "application/atom+xml",
    "application/feed+json",
    "application/rdf+xml",
    "application/rss+xml",
    "application/xml",
    "text/xml",
}
FEED_HINT_TOKENS = ("atom", "feed", "feeds", "rdf", "rss", "xml")
COMMON_FEED_SUFFIXES = (
    "feed",
    "feed.xml",
    "feeds",
    "feeds/default",
    "feeds/posts/default",
    "index.atom",
    "index.rdf",
    "index.rss",
    "index.xml",
    "atom",
    "atom.xml",
    "rdf",
    "rss",
    "rss.xml",
    "?feed=atom",
    "?feed=rdf",
    "?feed=rss",
    "?feed=rss2",
)


def local_xml_name(tag: str) -> str:
    """Strip XML namespaces from a tag name.

    Args:
        tag: Raw XML tag name.

    Returns:
        Namespace-free tag name.
    """
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def find_xml_child_text(parent, child_name: str) -> str:
    """Find the text of a direct XML child by local name.

    Args:
        parent: XML parent element.
        child_name: Desired child local tag name.

    Returns:
        Child text or an empty string.
    """
    if parent is None:
        return ""
    target_name = child_name.lower()
    for child in list(parent):
        if local_xml_name(child.tag).lower() == target_name and child.text:
            return child.text.strip()
    return ""


def is_probable_feed_url(url: str) -> bool:
    """Check whether a URL strongly resembles a feed endpoint.

    Args:
        url: URL or path to inspect.

    Returns:
        ``True`` when the URL looks like a feed endpoint.
    """
    lowered_url = (url or "").lower()
    return lowered_url.endswith((".atom", ".rdf", ".rss", ".xml", "/feed", "/feeds"))


def might_be_feed_url(url: str) -> bool:
    """Check whether a URL weakly resembles a feed endpoint.

    Args:
        url: URL or path to inspect.

    Returns:
        ``True`` when the URL contains feed-like hints.
    """
    lowered_url = (url or "").lower()
    return any(token in lowered_url for token in FEED_HINT_TOKENS)


def discover_feed_candidates(html: str, page_url: str) -> list[dict]:
    """Discover likely feed URLs from HTML markup and common path guesses.

    Args:
        html: Source HTML page.
        page_url: URL of the source page.

    Returns:
        Candidate feed URL payloads with source and score metadata.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []

    for link in soup.find_all("link", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        rel_values = {value.lower() for value in link.get("rel", [])}
        feed_type = (link.get("type") or "").lower().strip()
        if (
            feed_type in FEED_CONTENT_TYPES
            or ("alternate" in rel_values and "feed" in rel_values)
            or ("alternate" in rel_values and any(token in feed_type for token in ("atom", "rss", "rdf", "json")))
        ):
            candidates.append(
                {
                    "url": urljoin(page_url, href),
                    "source": "link",
                    "score": 100,
                    "type": feed_type or None,
                    "title": (link.get("title") or "").strip() or None,
                }
            )

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        absolute_url = urljoin(page_url, href)
        if is_probable_feed_url(href):
            candidates.append({"url": absolute_url, "source": "anchor", "score": 80})
        elif might_be_feed_url(href):
            candidates.append({"url": absolute_url, "source": "anchor", "score": 50})

    for suffix in COMMON_FEED_SUFFIXES:
        candidates.append(
            {
                "url": urljoin(page_url, suffix),
                "source": "guess",
                "score": 20,
            }
        )

    return merge_feed_candidates(candidates)


def discover_feed_spider_links(
    html: str,
    page_url: str,
    limit: int = 10,
) -> list[str]:
    """Select internal HTML pages that are promising places to look for feeds.

    Args:
        html: Source HTML page.
        page_url: URL of the source page.
        limit: Maximum internal pages to return.

    Returns:
        Ranked internal URLs to spider for more feed hints.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    parsed_page_url = urlparse(page_url)
    path_tokens = {token for token in parsed_page_url.path.split("/") if token}
    scored_urls = []
    seen_urls = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        candidate_url = urljoin(page_url, href)
        parsed_candidate = urlparse(candidate_url)
        if parsed_candidate.netloc != parsed_page_url.netloc:
            continue
        if parsed_candidate.scheme not in {"http", "https"}:
            continue
        if candidate_url in seen_urls:
            continue
        seen_urls.add(candidate_url)

        candidate_tokens = {token for token in parsed_candidate.path.split("/") if token}
        score = len(path_tokens & candidate_tokens)
        if might_be_feed_url(candidate_url):
            score += 5
        anchor_text = anchor.get_text(" ", strip=True).lower()
        if any(token in anchor_text for token in ("blog", "news", "posts", "updates")):
            score += 2
        scored_urls.append((score, len(candidate_url), candidate_url))

    scored_urls.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [item[2] for item in scored_urls[: max(1, limit)]]


def merge_feed_candidates(candidates: list[dict], max_candidates: int | None = None) -> list[dict]:
    """Dedupe candidate feed URLs while preserving the strongest signals.

    Args:
        candidates: Raw candidate payloads.
        max_candidates: Optional maximum number of candidates to keep.

    Returns:
        Deduped candidate payloads sorted by score.
    """
    merged_by_url = {}

    for candidate in candidates:
        candidate_url = candidate.get("url")
        if not candidate_url:
            continue
        existing = merged_by_url.get(candidate_url)
        if existing is None:
            merged_by_url[candidate_url] = {
                "url": candidate_url,
                "score": int(candidate.get("score", 0)),
                "sources": [candidate.get("source")] if candidate.get("source") else [],
                "discovered_from": [candidate.get("discovered_from")] if candidate.get("discovered_from") else [],
                "type": candidate.get("type"),
                "title": candidate.get("title"),
            }
            continue

        existing["score"] = max(existing["score"], int(candidate.get("score", 0)))
        source = candidate.get("source")
        if source and source not in existing["sources"]:
            existing["sources"].append(source)
        discovered_from = candidate.get("discovered_from")
        if discovered_from and discovered_from not in existing["discovered_from"]:
            existing["discovered_from"].append(discovered_from)
        if not existing.get("type") and candidate.get("type"):
            existing["type"] = candidate.get("type")
        if not existing.get("title") and candidate.get("title"):
            existing["title"] = candidate.get("title")

    merged_candidates = sorted(
        merged_by_url.values(),
        key=lambda item: (-item["score"], item["url"]),
    )
    if max_candidates is None:
        return merged_candidates
    return merged_candidates[: max(1, max_candidates)]


def analyze_feed_document(content: str, page_url: str, content_type: str = "") -> dict:
    """Validate and summarize a feed document candidate.

    Args:
        content: Raw document text.
        page_url: URL of the document.
        content_type: Response content type.

    Returns:
        Feed analysis payload.
    """
    stripped_content = (content or "").strip()
    lowered_content_type = (content_type or "").lower()

    if not stripped_content:
        return {"is_feed": False, "url": page_url}

    if "json" in lowered_content_type or stripped_content.startswith("{"):
        try:
            payload = json.loads(stripped_content)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and str(payload.get("version", "")).startswith("https://jsonfeed.org/version/"):
            items = payload.get("items", [])
            return {
                "is_feed": True,
                "url": page_url,
                "feed_format": "jsonfeed",
                "title": payload.get("title", "") or "",
                "description": payload.get("description", "") or "",
                "entry_count": len(items) if isinstance(items, list) else 0,
                "entry_urls": [
                    item.get("url")
                    for item in (items or [])[:5]
                    if isinstance(item, dict) and item.get("url")
                ],
            }

    preview = stripped_content[:400].lower()
    if "<html" in preview or "<head" in preview:
        html_soup = BeautifulSoup(stripped_content, "html.parser")
        if html_soup.find("html") or html_soup.find("head"):
            return {"is_feed": False, "url": page_url}

    try:
        root = ElementTree.fromstring(stripped_content)
    except ElementTree.ParseError:
        root = None

    if root is not None:
        root_name = local_xml_name(root.tag).lower()

        if root_name == "rss":
            channel = next((child for child in list(root) if local_xml_name(child.tag).lower() == "channel"), None)
            items = [child for child in list(channel or []) if local_xml_name(child.tag).lower() == "item"]
            return {
                "is_feed": True,
                "url": page_url,
                "feed_format": "rss",
                "title": find_xml_child_text(channel, "title"),
                "description": find_xml_child_text(channel, "description"),
                "entry_count": len(items),
                "entry_urls": [find_xml_child_text(item, "link") for item in items[:5] if find_xml_child_text(item, "link")],
            }

        if root_name == "feed":
            entries = [child for child in list(root) if local_xml_name(child.tag).lower() == "entry"]
            entry_urls = []
            for entry in entries[:5]:
                for child in list(entry):
                    if local_xml_name(child.tag).lower() == "link":
                        href = child.attrib.get("href")
                        if href:
                            entry_urls.append(href)
                            break
            return {
                "is_feed": True,
                "url": page_url,
                "feed_format": "atom",
                "title": find_xml_child_text(root, "title"),
                "description": find_xml_child_text(root, "subtitle"),
                "entry_count": len(entries),
                "entry_urls": entry_urls,
            }

        if root_name == "rdf":
            channel = next((child for child in list(root) if local_xml_name(child.tag).lower() == "channel"), None)
            items = [child for child in list(root) if local_xml_name(child.tag).lower() == "item"]
            return {
                "is_feed": True,
                "url": page_url,
                "feed_format": "rdf",
                "title": find_xml_child_text(channel, "title"),
                "description": find_xml_child_text(channel, "description"),
                "entry_count": len(items),
                "entry_urls": [find_xml_child_text(item, "link") for item in items[:5] if find_xml_child_text(item, "link")],
            }

    if any(token in lowered_content_type for token in ("rss", "atom", "rdf", "xml")) and any(
        marker in stripped_content[:400].lower() for marker in ("<rss", "<feed", "<rdf")
    ):
        return {
            "is_feed": True,
            "url": page_url,
            "feed_format": "xml",
            "title": "",
            "description": "",
            "entry_count": 0,
            "entry_urls": [],
        }

    return {"is_feed": False, "url": page_url}

"""Readable article extraction helpers."""

import re

from bs4 import BeautifulSoup, Tag

CONTENT_SCORE_BY_TAG = {
    "article": 10.0,
    "div": 5.0,
    "main": 8.0,
    "pre": 3.0,
    "section": 3.0,
    "td": 3.0,
    "blockquote": 3.0,
    "address": -3.0,
    "dl": -3.0,
    "dt": -3.0,
    "dd": -3.0,
    "form": -3.0,
    "li": -3.0,
    "ol": -3.0,
    "ul": -3.0,
    "h1": -5.0,
    "h2": -5.0,
    "h3": -5.0,
    "h4": -5.0,
    "h5": -5.0,
    "h6": -5.0,
    "th": -5.0,
}
LIKELY_CONTENT_RE = re.compile(r"article|body|content|entry|main|page|post|story|text|blog", re.I)
UNLIKELY_CONTENT_RE = re.compile(
    r"-ad-|banner|comment|combx|footer|gdpr|header|menu|nav|pagination|popup|related|reply|rss|share|sidebar|social|sponsor|widget",
    re.I,
)
UNLIKELY_ROLE_VALUES = {"alert", "alertdialog", "banner", "complementary", "dialog", "menu", "menubar", "navigation"}
STRIP_TAGS = {"script", "style", "noscript", "template", "svg", "canvas"}
CLEAN_TAGS = {"aside", "button", "dialog", "footer", "form", "header", "input", "nav", "select", "textarea"}
BLOCK_TAGS = {"article", "blockquote", "div", "main", "p", "pre", "section", "table", "td"}
FAST_PATH_SELECTORS = ("main", "article", "[role='main']", ".article", ".post", ".entry-content", ".post-content", ".story", ".content")


def normalize_article_text(text: str) -> str:
    """Normalize text extracted from an article candidate.

    Args:
        text: Raw text content.

    Returns:
        Whitespace-normalized text.
    """
    return re.sub(r"\s+", " ", text or "").strip()


def get_node_text(node: Tag) -> str:
    """Extract normalized text from a node.

    Args:
        node: Candidate element.

    Returns:
        Normalized node text.
    """
    return normalize_article_text(node.get_text(" ", strip=True))


def get_link_density(node: Tag) -> float:
    """Compute the ratio of link text to total text for a node.

    Args:
        node: Candidate element.

    Returns:
        Link density ratio.
    """
    text = get_node_text(node)
    if not text:
        return 0.0
    link_text = normalize_article_text(" ".join(anchor.get_text(" ", strip=True) for anchor in node.find_all("a")))
    return min(1.0, len(link_text) / max(1, len(text)))


def get_class_weight(node: Tag) -> float:
    """Compute a heuristic weight from class, id, and role attributes.

    Args:
        node: Candidate element.

    Returns:
        Positive or negative content weight.
    """
    attrs = node.attrs if isinstance(getattr(node, "attrs", None), dict) else {}
    score = 0.0
    values = [attrs.get("id", ""), " ".join(attrs.get("class", []))]
    for value in values:
        if not value:
            continue
        if LIKELY_CONTENT_RE.search(value):
            score += 25.0
        if UNLIKELY_CONTENT_RE.search(value):
            score -= 25.0
    role = str(attrs.get("role", "")).lower().strip()
    if role in UNLIKELY_ROLE_VALUES:
        score -= 25.0
    if role in {"article", "main"}:
        score += 25.0
    return score


def is_unlikely_candidate(node: Tag) -> bool:
    """Determine whether a node is likely to be boilerplate.

    Args:
        node: Candidate element.

    Returns:
        ``True`` when the node is unlikely to contain article text.
    """
    attrs = node.attrs if isinstance(getattr(node, "attrs", None), dict) else {}
    match_string = " ".join(
        [
            str(attrs.get("id", "")),
            " ".join(attrs.get("class", [])),
            str(attrs.get("role", "")),
        ]
    ).strip()
    if not match_string:
        return False
    return bool(UNLIKELY_CONTENT_RE.search(match_string) and not LIKELY_CONTENT_RE.search(match_string))


def initialize_candidate_score(node: Tag) -> float:
    """Compute the base score for a candidate container node.

    Args:
        node: Candidate container.

    Returns:
        Base content score.
    """
    return CONTENT_SCORE_BY_TAG.get(node.name, 0.0) + get_class_weight(node)


def score_text_node(node: Tag) -> float:
    """Score a paragraph-like node for article extraction.

    Args:
        node: Paragraph-like element.

    Returns:
        Content score contribution.
    """
    text = get_node_text(node)
    if len(text) < 25:
        return 0.0
    comma_count = text.count(",") + text.count("，") + text.count("、")
    sentenceish_count = text.count(".") + text.count("!") + text.count("?")
    return 1.0 + comma_count + min(len(text) / 100.0, 3.0) + min(sentenceish_count / 2.0, 3.0)


def clean_article_container(container: Tag) -> Tag:
    """Remove obvious boilerplate and low-value nodes from an extracted article.

    Args:
        container: Extracted article container.

    Returns:
        Cleaned article container.
    """
    for tag in list(container.find_all(STRIP_TAGS)):
        tag.decompose()
    for tag in list(container.find_all(CLEAN_TAGS)):
        tag.decompose()

    for node in list(container.find_all(True)):
        if is_unlikely_candidate(node):
            node.decompose()
            continue
        text = get_node_text(node)
        text_length = len(text)
        link_density = get_link_density(node)
        link_count = len(node.find_all("a"))
        image_count = len(node.find_all("img"))
        if node.name in {"div", "section", "article"}:
            if text_length < 40 and image_count == 0 and link_count > 1:
                node.decompose()
                continue
            if text_length < 100 and link_density > 0.6 and image_count == 0:
                node.decompose()
                continue
        if node.name in {"p", "li"} and text_length < 20 and image_count == 0 and link_count > 0:
            node.decompose()
            continue
    return container


def get_fast_path_candidate(body: Tag) -> Tag | None:
    """Find an obvious article container without running the full scorer.

    Args:
        body: Parsed document body.

    Returns:
        High-confidence article container or ``None``.
    """
    for selector in FAST_PATH_SELECTORS:
        candidate = body.select_one(selector)
        if candidate is None:
            continue
        text = get_node_text(candidate)
        if len(text) < 200:
            continue
        if len(candidate.find_all("p")) < 2:
            continue
        if get_link_density(candidate) > 0.35:
            continue
        return candidate
    return None


def extract_article_fragment(
    html: str,
    min_text_length: int = 25,
) -> tuple[Tag | None, dict]:
    """Extract the most readable article-like fragment from HTML.

    Args:
        html: Raw HTML content.
        min_text_length: Minimum paragraph text length to consider.

    Returns:
        Tuple of extracted fragment and extraction metadata.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in list(soup.find_all(STRIP_TAGS)):
        tag.decompose()
    for tag in list(soup.find_all(CLEAN_TAGS)):
        tag.decompose()
    for node in list(soup.find_all(True)):
        if node.name not in {"body", "a"} and is_unlikely_candidate(node):
            node.decompose()

    body = soup.body or soup
    fast_candidate = get_fast_path_candidate(body)
    if fast_candidate is not None:
        clean_article_container(fast_candidate)
        return fast_candidate, {"score": 100.0, "candidate_count": 1, "fallback_used": False}

    candidates_by_id: dict[int, dict] = {}

    for node in body.find_all(["p", "pre", "td", "blockquote"]):
        text = get_node_text(node)
        if len(text) < min_text_length:
            continue
        parent = node.parent if isinstance(node.parent, Tag) else None
        grandparent = parent.parent if parent and isinstance(parent.parent, Tag) else None
        if parent is None:
            continue
        score = score_text_node(node)
        for multiplier, candidate in ((1.0, parent), (0.5, grandparent)):
            if candidate is None:
                continue
            entry = candidates_by_id.setdefault(
                id(candidate),
                {
                    "node": candidate,
                    "score": initialize_candidate_score(candidate),
                },
            )
            entry["score"] += score * multiplier

    if not candidates_by_id:
        fallback = body.find(["main", "article"]) or body
        return fallback, {"score": 0.0, "candidate_count": 0, "fallback_used": True}

    scored_candidates = []
    for entry in candidates_by_id.values():
        adjusted_score = entry["score"] * (1.0 - get_link_density(entry["node"]))
        scored_candidates.append(
            {
                "node": entry["node"],
                "score": adjusted_score,
            }
        )

    scored_candidates.sort(key=lambda item: item["score"], reverse=True)
    top_candidate = scored_candidates[0]["node"]
    top_score = scored_candidates[0]["score"]
    parent = top_candidate.parent if isinstance(top_candidate.parent, Tag) else body
    container = soup.new_tag("article")
    sibling_threshold = max(10.0, top_score * 0.2)
    top_class = " ".join(top_candidate.get("class", []))

    for sibling in parent.find_all(recursive=False):
        if not isinstance(sibling, Tag):
            continue
        include = sibling is top_candidate
        sibling_entry = candidates_by_id.get(id(sibling))
        if sibling_entry and sibling_entry["score"] * (1.0 - get_link_density(sibling)) >= sibling_threshold:
            include = True
        if not include and top_class and top_class == " ".join(sibling.get("class", [])):
            include = True
        if not include and sibling.name == "p":
            text = get_node_text(sibling)
            if len(text) >= 80 and get_link_density(sibling) < 0.25:
                include = True
        if include:
            container.append(sibling.extract())

    clean_article_container(container)
    return container, {
        "score": round(top_score, 6),
        "candidate_count": len(scored_candidates),
        "fallback_used": False,
    }


def extract_article_content(html: str) -> dict:
    """Extract article-like content and metadata from HTML.

    Args:
        html: Raw HTML content.

    Returns:
        Article content payload.
    """
    fragment, metadata = extract_article_fragment(html)
    if fragment is None:
        return {
            "html": "",
            "text": "",
            "excerpt": "",
            "score": 0.0,
            "candidate_count": 0,
            "fallback_used": True,
        }

    text = get_node_text(fragment)
    excerpt = normalize_article_text(" ".join(part.get_text(" ", strip=True) for part in fragment.find_all(["p", "li"])[:2]))
    return {
        "html": str(fragment),
        "text": text,
        "excerpt": excerpt[:400],
        "score": metadata["score"],
        "candidate_count": metadata["candidate_count"],
        "fallback_used": metadata["fallback_used"],
    }

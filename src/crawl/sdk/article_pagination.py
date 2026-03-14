"""Multi-page article pagination helpers."""

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .urlnorm import get_url_dedupe_key

NEGATIVE_PAGINATION_RE = re.compile(
    r"author|back|comment|contact|older posts|newer posts|previous|prev|related|reply|share|sidebar|social",
    re.I,
)
NEXT_PAGINATION_RE = re.compile(
    r"continue|next|next page|older entries|older posts|page suivante|weiter|次|次のページ|下一页|suivant|volgende",
    re.I,
)
PAGE_HINT_RE = re.compile(r"(?:^|[\W_])(page|p|pg)(?:[\W_]*)(\d+)(?:$|[\W_])", re.I)
TRAILING_NUMBER_RE = re.compile(r"(?:[-_/]|page/)(\d+)(?:\.[a-z0-9]+)?$", re.I)
TITLE_SPLIT_RE = re.compile(r"\s+(?:\||-|\u2013|\u2014|:)\s+")
NON_HTML_EXTENSION_RE = re.compile(r"\.(?:avif|gif|jpg|jpeg|json|mp3|mp4|pdf|png|svg|webm|webp|xml|zip)$", re.I)


def normalize_pagination_text(value: str) -> str:
    """Normalize pagination text for scoring.

    Args:
        value: Raw label or attribute value.

    Returns:
        Whitespace-normalized lowercase text.
    """
    return re.sub(r"\s+", " ", value or "").strip().lower()


def parse_page_number(url: str) -> int | None:
    """Extract a likely page number from a URL.

    Args:
        url: Candidate page URL.

    Returns:
        Page number or ``None``.
    """
    parsed = urlparse(url)
    for key in ("page", "paged", "p", "pg"):
        values = parse_qs(parsed.query).get(key)
        if values:
            try:
                return int(values[0])
            except ValueError:
                continue

    match = PAGE_HINT_RE.search(parsed.path)
    if match:
        try:
            return int(match.group(2))
        except ValueError:
            return None

    match = TRAILING_NUMBER_RE.search(parsed.path)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def strip_page_marker(path: str) -> str:
    """Strip common page-number markers from a URL path.

    Args:
        path: URL path.

    Returns:
        Path without trailing page markers.
    """
    stripped = PAGE_HINT_RE.sub("", path or "")
    stripped = TRAILING_NUMBER_RE.sub("", stripped)
    return stripped.rstrip("/") or "/"


def normalize_article_title(title: str) -> str:
    """Normalize an article title for related-title comparisons.

    Args:
        title: Raw article title.

    Returns:
        Lowercased simplified title.
    """
    normalized = normalize_pagination_text(title)
    normalized = TITLE_SPLIT_RE.split(normalized)[0]
    normalized = re.sub(r"\bpage\s+\d+\b", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def titles_look_related(base_title: str, candidate_title: str) -> bool:
    """Check whether two article titles appear to describe the same article.

    Args:
        base_title: First-page title.
        candidate_title: Candidate next-page title.

    Returns:
        ``True`` when the titles look related.
    """
    normalized_base = normalize_article_title(base_title)
    normalized_candidate = normalize_article_title(candidate_title)
    if not normalized_base or not normalized_candidate:
        return True
    if normalized_base == normalized_candidate:
        return True
    if normalized_base in normalized_candidate or normalized_candidate in normalized_base:
        return True
    base_tokens = set(normalized_base.split())
    candidate_tokens = set(normalized_candidate.split())
    if not base_tokens or not candidate_tokens:
        return False
    overlap = len(base_tokens & candidate_tokens) / max(1, len(base_tokens | candidate_tokens))
    return overlap >= 0.6


def score_next_page_candidate(
    candidate_url: str,
    label: str,
    rel_values: list[str] | None,
    current_url: str,
    canonical_url: str | None = None,
) -> dict | None:
    """Score a candidate pagination link.

    Args:
        candidate_url: Candidate destination URL.
        label: Candidate text or title label.
        rel_values: Link rel values.
        current_url: Current page URL.
        canonical_url: Optional article canonical URL.

    Returns:
        Candidate score payload or ``None`` when invalid.
    """
    parsed_candidate = urlparse(candidate_url)
    parsed_current = urlparse(current_url)
    parsed_canonical = urlparse(canonical_url or current_url)
    if parsed_candidate.scheme not in {"http", "https"}:
        return None
    if parsed_candidate.netloc != parsed_current.netloc:
        return None
    if NON_HTML_EXTENSION_RE.search(parsed_candidate.path):
        return None
    if candidate_url == current_url:
        return None

    normalized_label = normalize_pagination_text(label)
    class_score = 0.0
    rel_values = [normalize_pagination_text(value) for value in (rel_values or [])]
    if any(value == "next" for value in rel_values):
        class_score += 60.0
    if NEXT_PAGINATION_RE.search(normalized_label):
        class_score += 25.0
    if NEGATIVE_PAGINATION_RE.search(normalized_label):
        class_score -= 40.0
    if len(normalized_label) > 80:
        class_score -= 20.0

    current_page_number = parse_page_number(current_url) or 1
    candidate_page_number = parse_page_number(candidate_url)
    if candidate_page_number is not None:
        if candidate_page_number == current_page_number + 1:
            class_score += 30.0
        elif candidate_page_number > current_page_number + 1:
            class_score += 8.0
        elif candidate_page_number <= current_page_number:
            class_score -= 25.0

    current_base_path = strip_page_marker(parsed_canonical.path)
    candidate_base_path = strip_page_marker(parsed_candidate.path)
    if candidate_base_path == current_base_path:
        class_score += 20.0
    elif candidate_page_number is not None and (
        candidate_base_path.startswith(current_base_path) or current_base_path.startswith(candidate_base_path)
    ):
        class_score += 10.0
    else:
        class_score -= 60.0 if candidate_page_number is None else 20.0

    if parsed_candidate.query and parsed_candidate.path == parsed_current.path:
        class_score += 10.0

    if class_score < 30.0:
        return None

    return {
        "url": candidate_url,
        "score": round(class_score, 6),
        "label": normalized_label,
        "page_number": candidate_page_number,
        "rel": rel_values,
    }


def discover_next_page_candidates(
    html: str,
    current_url: str,
    canonical_url: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Discover and rank likely next-page links for an article.

    Args:
        html: Current page HTML.
        current_url: Current page URL.
        canonical_url: Optional article canonical URL.
        limit: Maximum candidates to return.

    Returns:
        Ranked candidate payloads.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []
    seen_urls = set()

    for link in soup.find_all("link", href=True):
        rel_values = [normalize_pagination_text(value) for value in link.get("rel", [])]
        if "next" not in rel_values:
            continue
        candidate_url = urljoin(current_url, link.get("href", ""))
        candidate = score_next_page_candidate(
            candidate_url,
            label="next",
            rel_values=rel_values,
            current_url=current_url,
            canonical_url=canonical_url,
        )
        if candidate and get_url_dedupe_key(candidate["url"]) not in seen_urls:
            seen_urls.add(get_url_dedupe_key(candidate["url"]))
            candidates.append(candidate)

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        candidate_url = urljoin(current_url, href)
        label = " ".join(
            value
            for value in (
                anchor.get_text(" ", strip=True),
                anchor.get("title", ""),
                anchor.get("aria-label", ""),
                " ".join(anchor.get("class", [])),
                anchor.get("id", ""),
            )
            if value
        )
        candidate = score_next_page_candidate(
            candidate_url,
            label=label,
            rel_values=anchor.get("rel", []),
            current_url=current_url,
            canonical_url=canonical_url,
        )
        if candidate and get_url_dedupe_key(candidate["url"]) not in seen_urls:
            seen_urls.add(get_url_dedupe_key(candidate["url"]))
            candidates.append(candidate)

    candidates.sort(key=lambda item: (item["score"], item["url"]), reverse=True)
    return candidates[: max(1, limit)]

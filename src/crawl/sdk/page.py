"""Page parsing and content extraction helpers."""

import re
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

FALLBACK_STATUS_CODES = {403, 429, 503, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529, 530}
FALLBACK_HTML_MARKERS = (
    "attention required",
    "captcha",
    "cf-challenge",
    "cloudflare",
    "datadome",
    "enable javascript and cookies",
    "just a moment",
    "verify you are human",
)


def strip_fragment(url: str) -> str:
    """Remove the fragment component from a URL.

    Args:
        url: URL to normalize.

    Returns:
        URL without a fragment.
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    return parsed._replace(fragment="", path=path).geturl()


def matches_patterns(url: str, patterns: list[str] | None) -> bool:
    """Check whether a URL matches any of the provided patterns.

    Args:
        url: URL to inspect.
        patterns: Regex or substring patterns.

    Returns:
        ``True`` if any pattern matches or no patterns were supplied.
    """
    if not patterns:
        return True

    for pattern in patterns:
        try:
            if re.search(pattern, url):
                return True
        except re.error:
            if pattern in url:
                return True
    return False


def normalize_allowed_domains(allowed_domains: list[str] | None) -> set[str]:
    """Normalize allowed-domain entries into netloc values.

    Args:
        allowed_domains: Optional list of domains or URLs.

    Returns:
        Set of normalized netlocs.
    """
    if not allowed_domains:
        return set()

    normalized = set()
    for domain in allowed_domains:
        parsed = urlparse(domain if "://" in domain else f"https://{domain}")
        if parsed.netloc:
            normalized.add(parsed.netloc)
    return normalized


def is_same_scope(
    url: str,
    base_domain: str,
    allow_subdomains: bool = False,
    allowed_domains: set[str] | None = None,
) -> bool:
    """Check whether a URL belongs to the allowed crawl scope.

    Args:
        url: URL to inspect.
        base_domain: Root domain used for crawl scope.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.

    Returns:
        ``True`` when the URL is inside the allowed scope.
    """
    netloc = urlparse(url).netloc
    if not netloc:
        return False
    if allowed_domains and netloc in allowed_domains:
        return True
    if netloc == base_domain:
        return True
    if allow_subdomains and netloc.endswith(f".{base_domain}"):
        return True
    if allowed_domains:
        return any(netloc.endswith(f".{domain}") for domain in allowed_domains)
    return False


def normalize_headers(headers) -> dict[str, str]:
    """Convert response headers into a JSON-serializable mapping.

    Args:
        headers: Header collection from an HTTP response.

    Returns:
        Plain string header mapping.
    """
    if headers is None:
        return {}
    return {str(key): str(value) for key, value in headers.items()}


def normalize_crawl_budget(budget: dict[str, int] | None) -> dict[str, int]:
    """Normalize crawl budget keys and values.

    Args:
        budget: Optional crawl budget mapping.

    Returns:
        Sanitized crawl budget mapping.
    """
    if not budget:
        return {}

    normalized = {}
    for key, value in budget.items():
        try:
            remaining = max(0, int(value))
        except (TypeError, ValueError):
            continue

        if key == "*":
            normalized["*"] = remaining
            continue

        parsed = urlparse(key)
        path = parsed.path if parsed.scheme or parsed.netloc else key
        path = path or "/"
        if not path.startswith("/"):
            path = f"/{path}"
        normalized[path] = remaining

    return normalized


def consume_crawl_budget(url: str, budget_state: dict[str, int] | None) -> bool:
    """Consume crawl budget for a URL if capacity remains.

    Args:
        url: URL being admitted to the crawl queue.
        budget_state: Mutable crawl budget state.

    Returns:
        ``True`` when the URL can be admitted, otherwise ``False``.
    """
    if not budget_state:
        return True

    path = urlparse(url).path or "/"
    matched_prefixes = [prefix for prefix in budget_state if prefix != "*" and path.startswith(prefix)]
    matched_prefix = max(matched_prefixes, key=len) if matched_prefixes else None

    if "*" in budget_state and budget_state["*"] <= 0:
        return False
    if matched_prefix and budget_state[matched_prefix] <= 0:
        return False

    if "*" in budget_state:
        budget_state["*"] -= 1
    if matched_prefix:
        budget_state[matched_prefix] -= 1
    return True


def extract_page_metadata(soup, page_url: str) -> dict:
    """Extract metadata from a parsed page.

    Args:
        soup: BeautifulSoup parsed HTML tree.
        page_url: URL of the current page.

    Returns:
        Metadata dictionary.
    """
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag.get("content", "").strip() if desc_tag else ""

    image_tag = soup.find("meta", attrs={"property": "og:image"}) or soup.find(
        "meta",
        attrs={"name": "twitter:image"},
    )
    image = image_tag.get("content", "").strip() if image_tag else ""
    if image:
        image = urljoin(page_url, image)

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical_url = canonical_tag.get("href", "").strip() if canonical_tag else ""
    if canonical_url:
        canonical_url = urljoin(page_url, canonical_url)

    return {
        "title": title,
        "description": description,
        "image": image,
        "canonical_url": canonical_url,
    }


def parse_page_meta(
    html: str,
    page_url: str,
    base_domain: str,
    allow_subdomains: bool = False,
    allowed_domains: set[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict:
    """Extract metadata and scoped links from HTML.

    Args:
        html: Raw HTML content.
        page_url: URL of the current page.
        base_domain: Domain used to filter same-site links.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.

    Returns:
        Page metadata and discovered links.
    """
    soup = BeautifulSoup(html, "html.parser")
    metadata = extract_page_metadata(soup, page_url)

    links = []
    seen_links = set()
    for anchor in soup.find_all("a", href=True):
        full_url = strip_fragment(urljoin(page_url, anchor["href"]))
        if full_url in seen_links:
            continue
        if not is_same_scope(
            full_url,
            base_domain,
            allow_subdomains=allow_subdomains,
            allowed_domains=allowed_domains,
        ):
            continue
        if not matches_patterns(full_url, include_patterns):
            continue
        if exclude_patterns and matches_patterns(full_url, exclude_patterns):
            continue
        if full_url not in seen_links:
            seen_links.add(full_url)
            links.append(full_url)

    return {
        "title": metadata["title"],
        "description": metadata["description"],
        "image": metadata["image"],
        "canonical_url": metadata["canonical_url"],
        "metadata": metadata,
        "links": links,
    }


def should_browser_fallback(status_code: int | None, html: str) -> bool:
    """Determine whether a browser fallback is warranted.

    Args:
        status_code: HTTP status code if available.
        html: Response body HTML.

    Returns:
        ``True`` when the response likely needs browser rendering or anti-bot bypass.
    """
    if status_code is not None:
        if status_code in FALLBACK_STATUS_CODES or status_code >= 500:
            return True

    lowered = html.lower()
    if not lowered.strip():
        return True
    if any(marker in lowered for marker in FALLBACK_HTML_MARKERS):
        return True

    return False


def render_page_content(html: str, output_format: Literal["markdown", "text"]) -> str:
    """Convert page HTML into markdown or plain text.

    Args:
        html: Raw HTML content.
        output_format: Either ``markdown`` or ``text``.

    Returns:
        Rendered page content.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    if output_format == "text":
        return soup.get_text(separator="\n", strip=True)

    content = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "a", "ul", "ol", "li"]):
        if element.name.startswith("h"):
            level = int(element.name[1])
            content.append(f"{'#' * level} {element.get_text(strip=True)}")
        elif element.name == "p":
            content.append(element.get_text(strip=True))
        elif element.name == "a":
            content.append(f"[{element.get_text(strip=True)}]({element.get('href', '')})")
        elif element.name in ["ul", "ol"]:
            for list_item in element.find_all("li", recursive=False):
                content.append(f"- {list_item.get_text(strip=True)}")

    return "\n\n".join(content)

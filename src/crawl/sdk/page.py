"""Page parsing and content extraction helpers."""

import fnmatch
import hashlib
import re
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

FALLBACK_STATUS_CODES = {403, 429, 503, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529, 530}
FALLBACK_HTML_MARKERS = (
    "__cf_bm",
    "access denied",
    "attention required",
    "captcha",
    "cf-challenge",
    "cf-turnstile",
    "challenge-platform",
    "cloudflare",
    "data-sitekey",
    "ddos protection",
    "forbidden",
    "g-recaptcha",
    "hcaptcha",
    "datadome",
    "enable javascript and cookies",
    "just a moment",
    "security check",
    "verify you are human",
)
RESOURCE_ATTRIBUTE_MAP = {
    "link": "href",
    "script": "src",
    "img": "src",
    "source": "src",
    "video": "src",
    "audio": "src",
    "iframe": "src",
}
NON_CONTENT_TAGS = {"base", "iframe", "noscript", "script", "style"}
SIGNATURE_ALLOWED_ATTRIBUTES = {"class", "id"}


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
    return matches_patterns_with_mode(url, patterns, pattern_mode="auto")


def matches_patterns_with_mode(
    url: str,
    patterns: list[str] | None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
) -> bool:
    """Check whether a URL matches any of the provided patterns using a specific mode.

    Args:
        url: URL to inspect.
        patterns: Pattern list.
        pattern_mode: Matching mode.

    Returns:
        ``True`` if any pattern matches or no patterns were supplied.
    """
    if not patterns:
        return True

    for pattern in patterns:
        if pattern_mode == "substring":
            if pattern in url:
                return True
            continue

        if pattern_mode == "glob":
            if fnmatch.fnmatch(url, pattern):
                return True
            continue

        if pattern_mode == "regex":
            try:
                if re.search(pattern, url):
                    return True
            except re.error:
                continue
            continue

        if fnmatch.fnmatch(url, pattern):
            return True
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


def is_html_content_type(content_type: str) -> bool:
    """Check whether a content type should be parsed as HTML-like content.

    Args:
        content_type: Response content type.

    Returns:
        ``True`` when the response should be parsed as HTML/XML text.
    """
    lowered = (content_type or "").lower()
    return any(token in lowered for token in ("html", "xhtml", "xml", "svg"))


def extract_resource_links(
    soup,
    page_url: str,
    base_domain: str,
    allow_subdomains: bool = False,
    allowed_domains: set[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
) -> list[str]:
    """Extract resource URLs from a parsed page.

    Args:
        soup: BeautifulSoup parsed HTML tree.
        page_url: URL of the current page.
        base_domain: Domain used for crawl scope.
        allow_subdomains: Whether subdomains are in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns.
        exclude_patterns: Optional exclude patterns.
        pattern_mode: Pattern matching mode.

    Returns:
        Scoped resource URL list.
    """
    resources = []
    seen_resources = set()

    for tag_name, attribute_name in RESOURCE_ATTRIBUTE_MAP.items():
        for element in soup.find_all(tag_name):
            value = element.get(attribute_name)
            if not value:
                continue
            full_url = strip_fragment(urljoin(page_url, value))
            if full_url in seen_resources:
                continue
            if not is_same_scope(
                full_url,
                base_domain,
                allow_subdomains=allow_subdomains,
                allowed_domains=allowed_domains,
            ):
                continue
            if not matches_patterns_with_mode(full_url, include_patterns, pattern_mode=pattern_mode):
                continue
            if exclude_patterns and matches_patterns_with_mode(full_url, exclude_patterns, pattern_mode=pattern_mode):
                continue
            seen_resources.add(full_url)
            resources.append(full_url)

    return resources


def normalize_html_for_signature(html: str) -> str:
    """Normalize HTML for structural content hashing.

    Args:
        html: Raw HTML content.

    Returns:
        Normalized HTML string.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(NON_CONTENT_TAGS):
        tag.decompose()

    for element in soup.find_all(True):
        attrs_to_remove = []
        for attr_name in list(element.attrs.keys()):
            if attr_name in {"href", "src"}:
                attrs_to_remove.append(attr_name)
                continue
            if attr_name in SIGNATURE_ALLOWED_ATTRIBUTES or attr_name.startswith("data-"):
                continue
            attrs_to_remove.append(attr_name)
        for attr_name in attrs_to_remove:
            element.attrs.pop(attr_name, None)

    return soup.decode(formatter="minimal")


def compute_page_signature(html: str) -> str:
    """Compute a normalized structural signature for a page.

    Args:
        html: Raw HTML content.

    Returns:
        Stable signature hex string.
    """
    normalized_html = normalize_html_for_signature(html)
    return hashlib.blake2b(normalized_html.encode("utf-8"), digest_size=16).hexdigest()


def parse_page_meta(
    html: str,
    page_url: str,
    base_domain: str,
    allow_subdomains: bool = False,
    allowed_domains: set[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    full_resources: bool = False,
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
        pattern_mode: Pattern matching mode.
        full_resources: Whether to include resource URLs in crawl discovery.

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
        if not matches_patterns_with_mode(full_url, include_patterns, pattern_mode=pattern_mode):
            continue
        if exclude_patterns and matches_patterns_with_mode(full_url, exclude_patterns, pattern_mode=pattern_mode):
            continue
        if full_url not in seen_links:
            seen_links.add(full_url)
            links.append(full_url)

    resources = extract_resource_links(
        soup,
        page_url,
        base_domain,
        allow_subdomains=allow_subdomains,
        allowed_domains=allowed_domains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        pattern_mode=pattern_mode,
    )
    discovered_links = links + [resource for resource in resources if resource not in links] if full_resources else links

    return {
        "title": metadata["title"],
        "description": metadata["description"],
        "image": metadata["image"],
        "canonical_url": metadata["canonical_url"],
        "metadata": metadata,
        "links": discovered_links,
        "page_links": links,
        "resources": resources,
    }


def should_browser_fallback(status_code: int | None, html: str, headers: dict[str, str] | None = None) -> bool:
    """Determine whether a browser fallback is warranted.

    Args:
        status_code: HTTP status code if available.
        html: Response body HTML.
        headers: Optional response headers.

    Returns:
        ``True`` when the response likely needs browser rendering or anti-bot bypass.
    """
    if status_code is not None:
        if status_code in FALLBACK_STATUS_CODES or status_code >= 500:
            return True

    lowered = html.lower()
    if not lowered.strip():
        return True
    server_header = (headers or {}).get("server", "").lower()
    if any(token in server_header for token in ("cloudflare", "akamai", "imperva", "ddos-guard")):
        if any(marker in lowered for marker in ("captcha", "forbidden", "access denied", "just a moment", "verify")):
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

"""Robots.txt and sitemap discovery helpers."""

from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from .page import normalize_headers


async def request_text(session: AsyncSession, url: str) -> tuple[str, dict]:
    """Fetch plain text with an SSL-verification fallback.

    Args:
        session: Async HTTP session.
        url: URL to fetch.

    Returns:
        Tuple of response text and lightweight response metadata.
    """
    try:
        response = await session.get(url)
        ssl_fallback_used = False
    except Exception as error:
        if "SSL certificate problem" not in str(error):
            raise
        response = await session.get(url, verify=False)
        ssl_fallback_used = True

    return response.text, {
        "final_url": response.url,
        "status_code": response.status_code,
        "headers": normalize_headers(response.headers),
        "ssl_fallback_used": ssl_fallback_used,
    }


def build_robots_url(url: str) -> str:
    """Construct the robots.txt URL for a site.

    Args:
        url: Any URL on the site.

    Returns:
        robots.txt URL for the site's origin.
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def local_name(tag: str) -> str:
    """Strip XML namespaces from a tag name.

    Args:
        tag: XML tag.

    Returns:
        Namespace-free tag name.
    """
    return tag.rsplit("}", 1)[-1]


def extract_loc_values(root: ElementTree.Element, parent_tag: str) -> list[str]:
    """Extract `<loc>` values under a given parent tag.

    Args:
        root: XML root element.
        parent_tag: Parent tag name such as ``url`` or ``sitemap``.

    Returns:
        List of discovered URLs.
    """
    values = []
    for parent in root.iter():
        if local_name(parent.tag) != parent_tag:
            continue
        for child in parent:
            if local_name(child.tag) == "loc" and child.text:
                values.append(child.text.strip())
    return values


def discover_sitemap_urls_from_html(html: str, page_url: str) -> list[str]:
    """Discover sitemap URLs from page markup.

    Args:
        html: Raw HTML content.
        page_url: URL of the page containing sitemap hints.

    Returns:
        Sitemap URL list.
    """
    soup = BeautifulSoup(html, "html.parser")
    sitemap_urls = []

    for link in soup.find_all("link", href=True):
        rel_values = [value.lower() for value in link.get("rel", [])]
        href = link.get("href", "").strip()
        if not href:
            continue
        lowered_href = href.lower()
        if "sitemap" in rel_values or "sitemap" in lowered_href:
            absolute_url = urljoin(page_url, href)
            if absolute_url not in sitemap_urls:
                sitemap_urls.append(absolute_url)

    return sitemap_urls


async def load_robots_rules(
    session: AsyncSession,
    start_url: str,
    user_agent: str = "*",
) -> dict:
    """Load robots.txt rules and sitemap hints for a site.

    Args:
        session: Async HTTP session.
        start_url: Starting URL for the crawl.
        user_agent: User agent used for robots matching.

    Returns:
        Robots metadata and parser object when available.
    """
    robots_url = build_robots_url(start_url)
    parser = RobotFileParser()

    try:
        robots_text, metadata = await request_text(session, robots_url)
    except Exception:
        return {
            "robots_url": robots_url,
            "parser": None,
            "crawl_delay": None,
            "sitemaps": [],
            "status_code": None,
        }

    parser.set_url(robots_url)
    parser.parse(robots_text.splitlines())

    crawl_delay = parser.crawl_delay(user_agent)
    if crawl_delay is None and user_agent != "*":
        crawl_delay = parser.crawl_delay("*")

    sitemaps = parser.site_maps() or []

    return {
        "robots_url": robots_url,
        "parser": parser,
        "crawl_delay": crawl_delay,
        "sitemaps": sitemaps,
        "status_code": metadata["status_code"],
    }


async def collect_sitemap_urls(
    session: AsyncSession,
    sitemap_urls: list[str],
    limit: int = 1000,
) -> list[str]:
    """Resolve sitemap and sitemap-index documents into page URLs.

    Args:
        session: Async HTTP session.
        sitemap_urls: Seed sitemap URLs.
        limit: Maximum number of discovered page URLs.

    Returns:
        Flattened list of sitemap page URLs.
    """
    pending = list(sitemap_urls)
    visited_sitemaps = set()
    discovered_urls = []

    while pending and len(discovered_urls) < limit:
        sitemap_url = pending.pop(0)
        if sitemap_url in visited_sitemaps:
            continue
        visited_sitemaps.add(sitemap_url)

        try:
            sitemap_text, _ = await request_text(session, sitemap_url)
            root = ElementTree.fromstring(sitemap_text)
        except Exception:
            continue

        root_name = local_name(root.tag)
        if root_name == "urlset":
            for url in extract_loc_values(root, "url"):
                if url not in discovered_urls:
                    discovered_urls.append(url)
                    if len(discovered_urls) >= limit:
                        break
        elif root_name == "sitemapindex":
            for child_sitemap in extract_loc_values(root, "sitemap"):
                if child_sitemap not in visited_sitemaps:
                    pending.append(child_sitemap)

    return discovered_urls

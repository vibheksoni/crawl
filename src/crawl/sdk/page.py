"""Page parsing and content extraction helpers."""

from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def strip_fragment(url: str) -> str:
    """Remove the fragment component from a URL.

    Args:
        url: URL to normalize.

    Returns:
        URL without a fragment.
    """
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


async def extract_cookies(browser) -> dict:
    """Extract browser cookies into a plain name/value mapping.

    Args:
        browser: nodriver browser instance.

    Returns:
        Cookie mapping keyed by cookie name.
    """
    raw = await browser.cookies.get_all()
    cookies = {}
    for cookie in raw:
        cookies[cookie.name] = cookie.value
    return cookies


def parse_page_meta(html: str, page_url: str, base_domain: str) -> dict:
    """Extract title, description, and same-domain links from HTML.

    Args:
        html: Raw HTML content.
        page_url: URL of the current page.
        base_domain: Domain used to filter same-site links.

    Returns:
        Page metadata and discovered links.
    """
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag.get("content", "") if desc_tag else ""

    links = []
    for anchor in soup.find_all("a", href=True):
        full_url = strip_fragment(urljoin(page_url, anchor["href"]))
        if urlparse(full_url).netloc == base_domain:
            links.append(full_url)

    return {"title": title, "description": description, "links": links}


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

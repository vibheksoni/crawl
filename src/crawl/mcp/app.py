"""FastMCP application wrapper around the crawl SDK."""

from typing import Literal

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from crawl.sdk import crawl as sdk_crawl
from crawl.sdk import fetch as sdk_fetch
from crawl.sdk import fetch_page as sdk_fetch_page
from crawl.sdk import screenshot as sdk_screenshot
from crawl.sdk import websearch as sdk_websearch

mcp = FastMCP("crawl-mcp")


@mcp.tool()
async def websearch(
    query: str,
    max_results: int = 10,
    pages: int = 1,
    provider: Literal["google", "searxng", "auto", "hybrid"] = "google",
    searxng_url: str | None = None,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Run the SDK web search through the MCP transport.

    Args:
        query: Search query string.
        max_results: Maximum results per page.
        pages: Number of pages to scrape.
        provider: Search provider to use.
        searxng_url: Optional SearXNG base URL.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        Search results with links, titles, descriptions, and metadata.
    """
    return await sdk_websearch(
        query=query,
        max_results=max_results,
        pages=pages,
        provider=provider,
        searxng_url=searxng_url,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )


@mcp.tool()
async def fetch(
    url: str,
    output_format: Literal["markdown", "text"] = "markdown",
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> str:
    """Run the SDK fetch operation through the MCP transport.

    Args:
        url: URL to fetch.
        output_format: Either ``markdown`` or ``text``.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        Rendered page content.
    """
    return await sdk_fetch(
        url=url,
        output_format=output_format,
        mode=mode,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )


@mcp.tool()
async def fetch_page(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    full_resources: bool = False,
    include_headers: bool = False,
    include_html: bool = False,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Run the SDK structured page fetch through the MCP transport.

    Args:
        url: URL to fetch.
        mode: Fetch strategy.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        pattern_mode: Pattern matching mode.
        full_resources: Whether to include resource URLs in discovery.
        include_headers: Whether to include response headers.
        include_html: Whether to include raw HTML.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        Structured page details and discovered links.
    """
    return await sdk_fetch_page(
        url=url,
        mode=mode,
        allow_subdomains=allow_subdomains,
        allowed_domains=allowed_domains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        pattern_mode=pattern_mode,
        full_resources=full_resources,
        include_headers=include_headers,
        include_html=include_html,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )


@mcp.tool()
async def crawl(
    url: str,
    max_pages: int = 10,
    mode: Literal["fast", "auto"] = "auto",
    max_concurrency: int = 4,
    max_depth: int = 2,
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    full_resources: bool = False,
    dedupe_by_signature: bool = False,
    include_headers: bool = False,
    respect_robots_txt: bool = False,
    sitemap_url: str | None = None,
    seed_sitemap: bool = False,
    user_agent: str = "*",
    budget: dict[str, int] | None = None,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Run the SDK site crawler through the MCP transport.

    Args:
        url: Starting URL to crawl.
        max_pages: Maximum pages to crawl.
        mode: Crawl strategy, either ``fast`` or ``auto``.
        max_concurrency: Maximum parallel HTTP requests.
        max_depth: Maximum crawl depth from the start URL.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        pattern_mode: Pattern matching mode.
        full_resources: Whether to include resource URLs in crawl discovery.
        dedupe_by_signature: Whether to stop expanding duplicate-content pages.
        include_headers: Whether to include response headers in results.
        respect_robots_txt: Whether to enforce robots.txt access rules.
        sitemap_url: Optional sitemap URL to seed the crawl.
        seed_sitemap: Whether sitemap URLs should seed the crawl.
        user_agent: User agent name used for robots.txt evaluation.
        budget: Optional crawl budget mapping keyed by ``*`` or path prefixes.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        headers: Optional extra headers for HTTP and browser fetches.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        Crawled URL metadata and crawl statistics.
    """
    return await sdk_crawl(
        url=url,
        max_pages=max_pages,
        mode=mode,
        max_concurrency=max_concurrency,
        max_depth=max_depth,
        allow_subdomains=allow_subdomains,
        allowed_domains=allowed_domains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        pattern_mode=pattern_mode,
        full_resources=full_resources,
        dedupe_by_signature=dedupe_by_signature,
        include_headers=include_headers,
        respect_robots_txt=respect_robots_txt,
        sitemap_url=sitemap_url,
        seed_sitemap=seed_sitemap,
        user_agent=user_agent,
        budget=budget,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )


@mcp.tool()
async def screenshot(url: str, width: int = -1, height: int = -1, full_page: bool = True) -> Image:
    """Run the SDK screenshot operation through the MCP transport.

    Args:
        url: URL to capture.
        width: Requested viewport width, or ``-1`` for auto.
        height: Requested viewport height, or ``-1`` for auto.
        full_page: Whether to capture the full page.

    Returns:
        JPEG-compressed screenshot image.
    """
    image_bytes = await sdk_screenshot(url=url, width=width, height=height, full_page=full_page)
    return Image(data=image_bytes)


def run() -> None:
    """Run the FastMCP server."""
    mcp.run()

"""FastMCP application wrapper around the crawl SDK."""

from typing import Literal

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from crawl.sdk import crawl as sdk_crawl
from crawl.sdk import contacts as sdk_contacts
from crawl.sdk import fetch as sdk_fetch
from crawl.sdk import fetch_page as sdk_fetch_page
from crawl.sdk import batch_scrape as sdk_batch_scrape
from crawl.sdk import export_dataset as sdk_export_dataset
from crawl.sdk import extract as sdk_extract
from crawl.sdk import forms as sdk_forms
from crawl.sdk import get_technology_definition as sdk_get_technology_definition
from crawl.sdk import map_site as sdk_map_site
from crawl.sdk import query_page as sdk_query_page
from crawl.sdk import research as sdk_research
from crawl.sdk import scrape as sdk_scrape
from crawl.sdk import screenshot as sdk_screenshot
from crawl.sdk import search_technology_definitions as sdk_search_technology_definitions
from crawl.sdk import tech as sdk_tech
from crawl.sdk import tech_grep as sdk_tech_grep
from crawl.sdk import update_technology_definitions as sdk_update_technology_definitions
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
    scrape_results: bool = False,
    scrape_limit: int = 3,
    scrape_formats: list[Literal["markdown", "text", "html", "links", "metadata", "app_state", "contacts", "technologies"]] | None = None,
    only_main_content: bool = True,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
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
        scrape_results: Whether to scrape the top search results.
        scrape_limit: Maximum search results to scrape.
        scrape_formats: Requested scrape formats for result scraping.
        only_main_content: Whether to prefer main content while scraping results.
        cache: Whether to use disk caching for result scraping.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override for result scraping.
        headers: Optional extra headers for result scraping.
        accept_invalid_certs: Whether to ignore certificate errors for result scraping.
        max_retries: Maximum retry attempts after the initial request for scraped results.
        retry_backoff_ms: Base retry backoff in milliseconds for scraped results.

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
        scrape_results=scrape_results,
        scrape_limit=scrape_limit,
        scrape_formats=scrape_formats,
        only_main_content=only_main_content,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def fetch(
    url: str,
    output_format: Literal["markdown", "text"] = "markdown",
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
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
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

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
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def scrape(
    url: str,
    formats: list[Literal["markdown", "text", "html", "links", "metadata", "fit_markdown", "app_state", "contacts", "technologies"]] | None = None,
    only_main_content: bool = True,
    query: str | None = None,
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run the SDK multi-format scrape through the MCP transport."""
    return await sdk_scrape(
        url=url,
        formats=formats,
        only_main_content=only_main_content,
        query=query,
        mode=mode,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        pattern_mode=pattern_mode,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def batch_scrape(
    urls: list[str],
    formats: list[Literal["markdown", "text", "html", "links", "metadata", "fit_markdown", "app_state", "contacts", "technologies"]] | None = None,
    only_main_content: bool = True,
    query: str | None = None,
    mode: Literal["auto", "http", "browser"] = "auto",
    max_concurrency: int = 4,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run the SDK multi-URL scrape through the MCP transport."""
    return await sdk_batch_scrape(
        urls=urls,
        formats=formats,
        only_main_content=only_main_content,
        query=query,
        mode=mode,
        max_concurrency=max_concurrency,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def map(
    url: str,
    search: str | None = None,
    limit: int = 100,
    mode: Literal["fast", "auto"] = "fast",
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    respect_robots_txt: bool = False,
    sitemap_url: str | None = None,
    seed_sitemap: bool = False,
    user_agent: str = "*",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    state_path: str | None = None,
) -> dict:
    """Run the SDK site mapping through the MCP transport."""
    return await sdk_map_site(
        url=url,
        search=search,
        limit=limit,
        mode=mode,
        allow_subdomains=allow_subdomains,
        allowed_domains=allowed_domains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        pattern_mode=pattern_mode,
        respect_robots_txt=respect_robots_txt,
        sitemap_url=sitemap_url,
        seed_sitemap=seed_sitemap,
        user_agent=user_agent,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        state_path=state_path,
    )


@mcp.tool()
async def query(
    url: str,
    query: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run the SDK query-focused page extraction through the MCP transport."""
    return await sdk_query_page(
        url=url,
        query=query,
        mode=mode,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def research(
    query: str,
    max_results: int = 10,
    pages: int = 1,
    research_limit: int = 5,
    max_concurrency: int = 4,
    provider: Literal["google", "searxng", "auto", "hybrid"] = "auto",
    searxng_url: str | None = None,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run the SDK multi-source research workflow through the MCP transport."""
    return await sdk_research(
        query=query,
        max_results=max_results,
        pages=pages,
        research_limit=research_limit,
        max_concurrency=max_concurrency,
        provider=provider,
        searxng_url=searxng_url,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def extract(
    url: str,
    schema: dict,
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run the SDK selector-based extraction through the MCP transport."""
    return await sdk_extract(
        url=url,
        schema=schema,
        mode=mode,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def forms(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    include_fill_suggestions: bool = False,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run the SDK form extraction through the MCP transport."""
    return await sdk_forms(
        url=url,
        mode=mode,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        include_fill_suggestions=include_fill_suggestions,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def contacts(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run the SDK contact extraction through the MCP transport."""
    return await sdk_contacts(
        url=url,
        mode=mode,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


@mcp.tool()
async def tech(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    max_pages: int = 1,
    max_depth: int = 0,
    allow_subdomains: bool = False,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    aggression: int = 1,
) -> dict:
    """Run the SDK technology fingerprinting workflow through the MCP transport."""
    return await sdk_tech(
        url=url,
        mode=mode,
        max_pages=max_pages,
        max_depth=max_depth,
        allow_subdomains=allow_subdomains,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        aggression=aggression,
    )


@mcp.tool()
async def tech_list(search: str | None = None, limit: int = 50) -> dict:
    """List available technology definitions."""
    results = sdk_search_technology_definitions(search=search, limit=limit)
    return {"count": len(results), "results": results}


@mcp.tool()
async def tech_info(name: str) -> dict:
    """Get one technology definition by exact name."""
    result = sdk_get_technology_definition(name)
    if result is None:
        raise ValueError(f"Unknown technology: {name}")
    return result


@mcp.tool()
async def tech_update() -> str:
    """Refresh the bundled technology definitions file."""
    return sdk_update_technology_definitions()


@mcp.tool()
async def tech_grep(
    url: str,
    text: str | None = None,
    regex: str | None = None,
    search: str = "body",
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
) -> dict:
    """Run an ad-hoc signal grep through the SDK transport."""
    return await sdk_tech_grep(
        url=url,
        text=text,
        regex=regex,
        search=search,
        mode=mode,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
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
    include_requests: bool = False,
    interaction_mode: Literal["none", "auto"] = "none",
    max_interactions: int = 3,
    session_dir: str | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    include_headers: bool = False,
    include_html: bool = False,
    include_app_state: bool = False,
    include_contacts: bool = False,
    include_technologies: bool = False,
    technology_aggression: int = 1,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
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
        include_requests: Whether to capture browser requests.
        interaction_mode: Interaction mode for simple page interactions.
        max_interactions: Maximum interactions to perform.
        session_dir: Optional persistent browser profile directory.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        include_headers: Whether to include response headers.
        include_html: Whether to include raw HTML.
        include_app_state: Whether to extract embedded hydration payloads.
        include_contacts: Whether to extract contact and social details.
        include_technologies: Whether to extract technology fingerprints.
        technology_aggression: Technology fingerprint aggression level.
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
        include_requests=include_requests,
        interaction_mode=interaction_mode,
        max_interactions=max_interactions,
        session_dir=session_dir,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        include_headers=include_headers,
        include_html=include_html,
        include_app_state=include_app_state,
        include_contacts=include_contacts,
        include_technologies=include_technologies,
        technology_aggression=technology_aggression,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
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
    mode: Literal["fast", "auto", "browser"] = "auto",
    crawl_strategy: Literal["bfs", "best_first"] = "bfs",
    crawl_query: str | None = None,
    max_concurrency: int = 4,
    max_depth: int = 2,
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    full_resources: bool = False,
    dedupe_by_signature: bool = False,
    include_technologies: bool = False,
    include_requests: bool = False,
    interaction_mode: Literal["none", "auto"] = "none",
    max_interactions: int = 3,
    session_dir: str | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    auto_throttle: bool = False,
    autoscale_concurrency: bool = False,
    min_concurrency: int = 1,
    cpu_target_percent: float = 75.0,
    memory_target_percent: float = 80.0,
    technology_aggression: int = 1,
    minimum_delay_ms: int = 0,
    maximum_delay_ms: int = 5000,
    state_path: str | None = None,
    include_headers: bool = False,
    respect_robots_txt: bool = False,
    sitemap_url: str | None = None,
    seed_sitemap: bool = False,
    user_agent: str = "*",
    budget: dict[str, int] | None = None,
    delay_ms: int = 0,
    path_delays: dict[str, int] | None = None,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    cache_revalidate: bool = False,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Run the SDK site crawler through the MCP transport.

    Args:
        url: Starting URL to crawl.
        max_pages: Maximum pages to crawl.
        mode: Crawl strategy, either ``fast``, ``auto``, or ``browser``.
        crawl_strategy: Frontier strategy.
        crawl_query: Optional relevance query for best-first crawling.
        max_concurrency: Maximum parallel HTTP requests.
        max_depth: Maximum crawl depth from the start URL.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        pattern_mode: Pattern matching mode.
        full_resources: Whether to include resource URLs in crawl discovery.
        dedupe_by_signature: Whether to stop expanding duplicate-content pages.
        include_technologies: Whether to extract technology fingerprints for each page.
        include_requests: Whether to capture browser requests.
        interaction_mode: Interaction mode for simple page interactions.
        max_interactions: Maximum interactions to perform.
        session_dir: Optional persistent browser profile directory.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        auto_throttle: Whether to adapt delay from observed timings.
        autoscale_concurrency: Whether to adapt concurrency from system load.
        min_concurrency: Lower bound for autoscaled concurrency.
        cpu_target_percent: Preferred CPU ceiling for autoscaling.
        memory_target_percent: Preferred memory ceiling for autoscaling.
        technology_aggression: Technology fingerprint aggression level.
        minimum_delay_ms: Lower bound for adaptive delay.
        maximum_delay_ms: Upper bound for adaptive delay.
        state_path: Optional persisted crawl state file.
        include_headers: Whether to include response headers in results.
        respect_robots_txt: Whether to enforce robots.txt access rules.
        sitemap_url: Optional sitemap URL to seed the crawl.
        seed_sitemap: Whether sitemap URLs should seed the crawl.
        user_agent: User agent name used for robots.txt evaluation.
        budget: Optional crawl budget mapping keyed by ``*`` or path prefixes.
        delay_ms: Default crawl delay in milliseconds.
        path_delays: Optional per-path delay mapping in milliseconds.
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
        crawl_strategy=crawl_strategy,
        crawl_query=crawl_query,
        max_concurrency=max_concurrency,
        max_depth=max_depth,
        allow_subdomains=allow_subdomains,
        allowed_domains=allowed_domains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        pattern_mode=pattern_mode,
        full_resources=full_resources,
        dedupe_by_signature=dedupe_by_signature,
        include_technologies=include_technologies,
        include_requests=include_requests,
        interaction_mode=interaction_mode,
        max_interactions=max_interactions,
        session_dir=session_dir,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        auto_throttle=auto_throttle,
        autoscale_concurrency=autoscale_concurrency,
        min_concurrency=min_concurrency,
        cpu_target_percent=cpu_target_percent,
        memory_target_percent=memory_target_percent,
        technology_aggression=technology_aggression,
        minimum_delay_ms=minimum_delay_ms,
        maximum_delay_ms=maximum_delay_ms,
        state_path=state_path,
        include_headers=include_headers,
        respect_robots_txt=respect_robots_txt,
        sitemap_url=sitemap_url,
        seed_sitemap=seed_sitemap,
        user_agent=user_agent,
        budget=budget,
        delay_ms=delay_ms,
        path_delays=path_delays,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
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


@mcp.tool()
async def dataset_export(
    dataset_name: str = "default",
    dataset_dir: str | None = None,
    output_format: Literal["json", "jsonl", "csv"] = "json",
    collect_all_keys: bool = True,
) -> str:
    """Export a persisted dataset from local storage."""
    return sdk_export_dataset(
        dataset_name=dataset_name,
        dataset_dir=dataset_dir,
        output_format=output_format,
        collect_all_keys=collect_all_keys,
    )


def run() -> None:
    """Run the FastMCP server."""
    mcp.run()

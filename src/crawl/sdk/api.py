"""Reusable SDK operations for web search, fetch, crawl, and screenshot."""

import asyncio
import io
import os
import tempfile
import time
from collections import deque
from typing import Literal
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from PIL import Image as PILImage

from .browser import browser_session, configure_page_request_settings
from .cache import load_cached_page, save_cached_page
from .discovery import collect_sitemap_urls, discover_sitemap_urls_from_html, load_robots_rules
from .google import (
    extract_ai_overview,
    extract_organic_results,
    extract_people_also_ask,
    extract_video_results,
)
from .page import (
    compute_page_signature,
    consume_crawl_budget,
    is_same_scope,
    is_html_content_type,
    matches_patterns_with_mode,
    normalize_allowed_domains,
    normalize_crawl_budget,
    normalize_delay_map,
    normalize_headers,
    parse_page_meta,
    render_page_content,
    resolve_delay_ms,
    should_browser_fallback,
    strip_fragment,
)
from .proxy import normalize_proxy_urls, pick_proxy
from .scrape import ScrapeFormat, build_scrape_result
from .searxng import search_searxng


def dedupe_search_items(items: list[dict]) -> list[dict]:
    """Dedupe search items by link while preserving order.

    Args:
        items: Search item payloads.

    Returns:
        Deduped item list.
    """
    deduped = []
    seen_links = set()

    for item in items:
        link = item.get("link")
        if link and link in seen_links:
            continue
        if link:
            seen_links.add(link)
        deduped.append(item)

    return deduped


def tokenize_query(text: str) -> list[str]:
    """Tokenize a query into lowercase search terms.

    Args:
        text: Query or text to tokenize.

    Returns:
        Token list.
    """
    return [token.lower() for token in text.replace("/", " ").replace("-", " ").split() if token.strip()]


def score_map_result(item: dict, search: str | None = None) -> float:
    """Score a mapped page for optional URL discovery relevance.

    Args:
        item: Crawl result item.
        search: Optional relevance query.

    Returns:
        Relevance score.
    """
    if not search:
        return 0.0

    haystack = " ".join(
        [
            item.get("url", ""),
            item.get("final_url", ""),
            item.get("title", ""),
            item.get("description", ""),
        ]
    ).lower()
    score = 0.0
    for token in tokenize_query(search):
        if token in haystack:
            score += 1.0
        if token in item.get("url", "").lower():
            score += 0.5
    return score


def merge_search_payloads(
    primary: dict,
    secondary: dict,
    max_results: int,
    pages: int,
) -> dict:
    """Merge two search payloads into a single normalized response.

    Args:
        primary: Primary search payload.
        secondary: Secondary search payload.
        max_results: Maximum results per page.
        pages: Number of requested pages.

    Returns:
        Combined search payload.
    """
    combined_results = dedupe_search_items(primary.get("results", []) + secondary.get("results", []))
    combined_videos = dedupe_search_items(primary.get("videos", []) + secondary.get("videos", []))

    people_also_ask = []
    for question in primary.get("people_also_ask", []) + secondary.get("people_also_ask", []):
        if question not in people_also_ask:
            people_also_ask.append(question)

    def merge_misc_list(key: str) -> list:
        merged = []
        for item in primary.get(key, []) + secondary.get(key, []):
            if item not in merged:
                merged.append(item)
        return merged

    return {
        "provider": "hybrid",
        "provider_url": [primary.get("provider_url"), secondary.get("provider_url")],
        "providers": [primary.get("provider"), secondary.get("provider")],
        "query": primary.get("query") or secondary.get("query"),
        "pages_scraped": max(primary.get("pages_scraped", 0), secondary.get("pages_scraped", 0)),
        "ai_overview": primary.get("ai_overview") or secondary.get("ai_overview", ""),
        "results": combined_results[: max_results * pages],
        "videos": combined_videos[:max_results],
        "people_also_ask": people_also_ask,
        "answers": merge_misc_list("answers"),
        "infoboxes": merge_misc_list("infoboxes"),
        "suggestions": merge_misc_list("suggestions"),
        "corrections": merge_misc_list("corrections"),
        "unresponsive_engines": merge_misc_list("unresponsive_engines"),
        "count": min(len(combined_results), max_results * pages),
    }


async def attach_scraped_search_results(
    search_payload: dict,
    scrape_limit: int = 3,
    scrape_formats: list[ScrapeFormat] | None = None,
    only_main_content: bool = True,
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Attach scraped content to the top search results.

    Args:
        search_payload: Existing search payload.
        scrape_limit: Maximum results to scrape.
        scrape_formats: Requested scrape formats.
        only_main_content: Whether to prefer main content.
        mode: Fetch strategy for result scraping.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        Search payload with scraped result attachments.
    """
    target_results = [item for item in search_payload.get("results", []) if item.get("link")][: max(0, scrape_limit)]
    if not target_results:
        search_payload["scraped_results"] = []
        return search_payload

    scraped_payload = await batch_scrape(
        [item["link"] for item in target_results],
        formats=scrape_formats or ["markdown"],
        only_main_content=only_main_content,
        mode=mode,
        max_concurrency=min(max(1, scrape_limit), 4),
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )

    scraped_by_url = {
        item.get("url"): item
        for item in scraped_payload.get("data", [])
        if item.get("url")
    }

    for result in search_payload.get("results", []):
        scraped = scraped_by_url.get(result.get("link"))
        if scraped:
            result["scrape"] = scraped

    search_payload["scraped_results"] = scraped_payload.get("data", [])
    search_payload["scrape_limit"] = scrape_limit
    search_payload["scrape_formats"] = scrape_formats or ["markdown"]
    return search_payload


async def search_google(
    query: str,
    max_results: int = 10,
    pages: int = 1,
    proxy_url: str | None = None,
) -> dict:
    """Search Google and return normalized results.

    Args:
        query: Search query string.
        max_results: Maximum results per page.
        pages: Number of pages to scrape.
        proxy_url: Optional proxy URL.

    Returns:
        Search results with links, titles, descriptions, and metadata.
    """
    all_results = []
    all_videos = []
    all_paa = []
    ai_overview = ""
    seen_urls = set()
    current_page = 0

    browser_args = [f"--proxy-server={proxy_url}"] if proxy_url else None
    async with browser_session(headless=False, browser_args=browser_args) as browser:
        page_obj = await browser.get(f"https://www.google.com/search?q={quote_plus(query)}")
        await page_obj.sleep(3)

        try:
            show_more = await page_obj.find("Show more", best_match=True, timeout=2)
            if show_more:
                await show_more.click()
                await page_obj.sleep(1)
        except Exception:
            pass

        for current_page in range(1, pages + 1):
            html = await page_obj.get_content()
            soup = BeautifulSoup(html, "html.parser")

            page_results = extract_organic_results(soup, max_results)
            for result in page_results:
                if result["link"] not in seen_urls:
                    seen_urls.add(result["link"])
                    result["page"] = current_page
                    all_results.append(result)

            for video in extract_video_results(soup):
                if video["link"] not in seen_urls:
                    seen_urls.add(video["link"])
                    video["page"] = current_page
                    all_videos.append(video)

            for question in extract_people_also_ask(soup):
                if question not in all_paa:
                    all_paa.append(question)

            if current_page == 1:
                ai_overview = extract_ai_overview(soup)

            if current_page < pages:
                next_page = current_page + 1
                next_btn = await page_obj.select(f"a[aria-label='Page {next_page}']")
                if not next_btn:
                    break
                await next_btn.click()
                await page_obj.sleep(3)

    return {
        "provider": "google",
        "provider_url": None,
        "query": query,
        "pages_scraped": min(current_page, pages),
        "ai_overview": ai_overview,
        "results": all_results,
        "videos": all_videos,
        "people_also_ask": all_paa,
        "answers": [],
        "infoboxes": [],
        "suggestions": [],
        "corrections": [],
        "unresponsive_engines": [],
        "count": len(all_results),
    }


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
    scrape_formats: list[ScrapeFormat] | None = None,
    only_main_content: bool = True,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
) -> dict:
    """Search the web through Google or SearXNG and normalize the results.

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

    Returns:
        Search results with links, titles, descriptions, and metadata.
    """
    normalized_proxy_urls = normalize_proxy_urls(proxy_url=proxy_url, proxy_urls=proxy_urls)
    selected_proxy = pick_proxy(normalized_proxy_urls, 0)

    if provider == "searxng":
        search_payload = await search_searxng(
            query=query,
            max_results=max_results,
            pages=pages,
            searxng_url=searxng_url,
            proxy_url=selected_proxy,
        )
    elif provider == "hybrid":
        searxng_result, google_result = await asyncio.gather(
            search_searxng(
                query=query,
                max_results=max_results,
                pages=pages,
                searxng_url=searxng_url,
                proxy_url=selected_proxy,
            ),
            search_google(query=query, max_results=max_results, pages=pages, proxy_url=selected_proxy),
        )
        search_payload = merge_search_payloads(searxng_result, google_result, max_results=max_results, pages=pages)
    elif provider == "auto":
        try:
            search_payload = await search_searxng(
                query=query,
                max_results=max_results,
                pages=pages,
                searxng_url=searxng_url,
                proxy_url=selected_proxy,
            )
        except Exception:
            search_payload = await search_google(query=query, max_results=max_results, pages=pages, proxy_url=selected_proxy)
    else:
        search_payload = await search_google(query=query, max_results=max_results, pages=pages, proxy_url=selected_proxy)

    if scrape_results:
        return await attach_scraped_search_results(
            search_payload,
            scrape_limit=scrape_limit,
            scrape_formats=scrape_formats,
            only_main_content=only_main_content,
            mode="auto",
            cache=cache,
            cache_dir=cache_dir,
            cache_ttl_seconds=cache_ttl_seconds,
            user_agent=user_agent,
            headers=headers,
            accept_invalid_certs=accept_invalid_certs,
            proxy_url=proxy_url,
            proxy_urls=proxy_urls,
        )

    return search_payload


async def request_page(session: AsyncSession, url: str) -> dict:
    """Fetch a page over HTTP with an SSL-verification fallback.

    Args:
        session: Async HTTP session.
        url: URL to fetch.

    Returns:
        Structured HTTP response data.
    """
    return await request_page_with_verify_override(session, url)


async def request_page_with_verify_override(
    session: AsyncSession,
    url: str,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
) -> dict:
    """Fetch a page over HTTP with configurable certificate handling.

    Args:
        session: Async HTTP session.
        url: URL to fetch.
        accept_invalid_certs: Whether to skip certificate verification.
        proxy_url: Optional proxy URL.

    Returns:
        Structured HTTP response data.
    """
    started_at = time.perf_counter()
    try:
        response = await session.get(
            url,
            verify=False if accept_invalid_certs else None,
            proxy=proxy_url,
        )
        ssl_fallback_used = accept_invalid_certs
    except Exception as error:
        if accept_invalid_certs or "SSL certificate problem" not in str(error):
            raise
        response = await session.get(url, verify=False, proxy=proxy_url)
        ssl_fallback_used = True

    return {
        "url": url,
        "final_url": response.url,
        "status_code": response.status_code,
        "headers": normalize_headers(response.headers),
        "content_type": response.headers.get("content-type", ""),
        "html": response.text,
        "bytes_transferred": len(response.content or b""),
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
        "ssl_fallback_used": ssl_fallback_used,
    }


def build_http_headers(
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Build request headers for HTTP fetches.

    Args:
        user_agent: Optional user-agent override.
        headers: Optional extra headers.

    Returns:
        Combined header mapping or ``None``.
    """
    merged = {}
    if headers:
        merged.update(headers)
    if user_agent:
        merged["user-agent"] = user_agent
    return merged or None


async def request_browser_page(
    url: str,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
) -> dict:
    """Fetch a page through the browser.

    Args:
        url: URL to fetch.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional proxy URL.

    Returns:
        Structured browser response data.
    """
    started_at = time.perf_counter()
    browser_args = [f"--proxy-server={proxy_url}"] if proxy_url else None
    async with browser_session(headless=False, browser_args=browser_args) as browser:
        page = await browser.get("about:blank")
        await configure_page_request_settings(
            page,
            user_agent=user_agent,
            headers=headers,
            accept_invalid_certs=accept_invalid_certs,
        )
        await page.get(url)
        await page.sleep(2)

        html = await page.get_content()
        return {
            "url": url,
            "final_url": page.url,
            "status_code": None,
            "headers": {},
            "content_type": "text/html",
            "html": html,
            "bytes_transferred": len(html.encode("utf-8")),
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
            "ssl_fallback_used": False,
        }


def build_page_result(
    page_data: dict,
    page_meta: dict,
    depth: int = 0,
    include_headers: bool = False,
    include_html: bool = False,
    source: Literal["http", "browser"] = "http",
    fallback_used: bool = False,
    cache_hit: bool = False,
    signature: str | None = None,
) -> dict:
    """Build a normalized page result payload.

    Args:
        page_data: Raw page fetch data.
        page_meta: Parsed page metadata.
        depth: Crawl depth for the page.
        include_headers: Whether to include response headers.
        include_html: Whether to include raw HTML.
        source: Source used to fetch the page.
        fallback_used: Whether browser fallback was used after HTTP.

    Returns:
        Normalized page result payload.
    """
    result = {
        "url": page_data["url"],
        "final_url": page_data["final_url"],
        "depth": depth,
        "source": source,
        "fallback_used": fallback_used,
        "cache_hit": cache_hit,
        "status_code": page_data["status_code"],
        "content_type": page_data["content_type"],
        "elapsed_ms": page_data.get("elapsed_ms"),
        "bytes_transferred": page_data.get("bytes_transferred"),
        "title": page_meta["title"],
        "description": page_meta["description"],
        "links_found": len(page_meta["links"]),
        "page_links_found": len(page_meta.get("page_links", [])),
        "resources_found": len(page_meta.get("resources", [])),
        "links": page_meta.get("links", []),
        "page_links": page_meta.get("page_links", []),
        "resources": page_meta.get("resources", []),
        "metadata": page_meta["metadata"],
        "signature": signature,
    }

    if include_headers:
        result["headers"] = page_data["headers"]
    if include_html:
        result["html"] = page_data["html"]

    return result


async def _fetch_page(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_headers: bool = False,
    include_html: bool = False,
    session: AsyncSession | None = None,
    depth: int = 0,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    proxy_index: int = 0,
    full_resources: bool = False,
) -> tuple[dict, list[str]]:
    """Fetch a page and return normalized details plus discovered links.

    Args:
        url: URL to fetch.
        mode: Fetch strategy.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        include_headers: Whether to include response headers.
        include_html: Whether to include raw HTML.
        session: Optional reusable HTTP session.
        depth: Crawl depth for the page.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        proxy_index: Round-robin proxy selection index.
        full_resources: Whether to include resource URLs in discovery.

    Returns:
        Tuple of page result payload and discovered links.
    """
    allowed_domain_set = normalize_allowed_domains(allowed_domains)
    normalized_proxy_urls = normalize_proxy_urls(proxy_url=proxy_url, proxy_urls=proxy_urls)
    selected_proxy = pick_proxy(normalized_proxy_urls, proxy_index)
    page_data = None
    source: Literal["http", "browser"] = "http"
    fallback_used = False
    cache_hit = False

    if cache:
        cached_page_data = load_cached_page(
            url=url,
            mode=mode,
            cache_dir=cache_dir,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        if cached_page_data is not None:
            page_data = cached_page_data
            source = page_data.get("source", source)
            fallback_used = page_data.get("fallback_used", False)
            cache_hit = True

    if page_data is None:
        if mode == "browser":
            page_data = await request_browser_page(
                url,
                user_agent=user_agent,
                headers=headers,
                accept_invalid_certs=accept_invalid_certs,
                proxy_url=selected_proxy,
            )
            source = "browser"
        else:
            try:
                request_headers = build_http_headers(user_agent=user_agent, headers=headers)
                if session is None:
                    async with AsyncSession(
                        impersonate="chrome",
                        timeout=15,
                        headers=request_headers,
                    ) as owned_session:
                        page_data = await request_page_with_verify_override(
                            owned_session,
                            url,
                            accept_invalid_certs=accept_invalid_certs,
                            proxy_url=selected_proxy,
                        )
                else:
                    page_data = await request_page_with_verify_override(
                        session,
                        url,
                        accept_invalid_certs=accept_invalid_certs,
                        proxy_url=selected_proxy,
                    )
            except Exception:
                if mode != "auto":
                    raise
                page_data = await request_browser_page(
                    url,
                    user_agent=user_agent,
                    headers=headers,
                    accept_invalid_certs=accept_invalid_certs,
                    proxy_url=selected_proxy,
                )
                source = "browser"
                fallback_used = True

            if source == "http" and mode == "auto" and should_browser_fallback(
                page_data["status_code"],
                page_data["html"],
                headers=page_data["headers"],
            ):
                browser_data = await request_browser_page(
                    url,
                    user_agent=user_agent,
                    headers=headers,
                    accept_invalid_certs=accept_invalid_certs,
                    proxy_url=selected_proxy,
                )
                browser_data["status_code"] = page_data["status_code"]
                browser_data["ssl_fallback_used"] = page_data["ssl_fallback_used"]
                page_data = browser_data
                source = "browser"
                fallback_used = True

        page_data["source"] = source
        page_data["fallback_used"] = fallback_used
        if cache:
            save_cached_page(url=url, mode=mode, page_data=page_data, cache_dir=cache_dir)

    scope_domain = urlparse(page_data["final_url"]).netloc or urlparse(url).netloc
    if is_html_content_type(page_data["content_type"]):
        page_meta = parse_page_meta(
            page_data["html"],
            page_data["final_url"],
            scope_domain,
            allow_subdomains=allow_subdomains,
            allowed_domains=allowed_domain_set,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            pattern_mode=pattern_mode,
            full_resources=full_resources,
        )
        signature = compute_page_signature(page_data["html"])
    else:
        page_meta = {
            "title": "",
            "description": "",
            "image": "",
            "canonical_url": "",
            "metadata": {
                "title": "",
                "description": "",
                "image": "",
                "canonical_url": "",
            },
            "links": [],
            "page_links": [],
            "resources": [],
        }
        signature = None

    result = build_page_result(
        page_data,
        page_meta,
        depth=depth,
        include_headers=include_headers,
        include_html=include_html,
        source=source,
        fallback_used=fallback_used,
        cache_hit=cache_hit,
        signature=signature,
    )
    return result, page_meta["links"]


async def fetch_page(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_headers: bool = False,
    include_html: bool = False,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    full_resources: bool = False,
) -> dict:
    """Fetch a page and return structured details.

    Args:
        url: URL to fetch.
        mode: Fetch strategy.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        include_headers: Whether to include response headers.
        include_html: Whether to include raw HTML.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        full_resources: Whether to include resource URLs in discovery.

    Returns:
        Structured page details and discovered links.
    """
    result, _ = await _fetch_page(
        url=url,
        mode=mode,
        allow_subdomains=allow_subdomains,
        allowed_domains=allowed_domains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        include_headers=include_headers,
        include_html=include_html,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        pattern_mode=pattern_mode,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        full_resources=full_resources,
    )
    return result


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
    only_main_content: bool = True,
) -> str:
    """Fetch a URL and convert the page into markdown or plain text.

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
        only_main_content: Whether to prefer main content.

    Returns:
        Rendered page content.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=True,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )
    return render_page_content(page["html"], output_format, only_main_content=only_main_content)


async def scrape(
    url: str,
    formats: list[ScrapeFormat] | None = None,
    only_main_content: bool = True,
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Scrape a page into one or more content formats.

    Args:
        url: URL to scrape.
        formats: Requested scrape formats.
        only_main_content: Whether to prefer main content.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        Multi-format scrape payload.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=True,
        include_headers=True,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        pattern_mode=pattern_mode,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )
    return build_scrape_result(page, formats=formats, only_main_content=only_main_content)


async def batch_scrape(
    urls: list[str],
    formats: list[ScrapeFormat] | None = None,
    only_main_content: bool = True,
    mode: Literal["auto", "http", "browser"] = "auto",
    max_concurrency: int = 4,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Scrape multiple URLs with bounded concurrency.

    Args:
        urls: URL list to scrape.
        formats: Requested scrape formats.
        only_main_content: Whether to prefer main content.
        mode: Fetch strategy.
        max_concurrency: Maximum concurrent scrape tasks.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        Batch scrape payload with per-URL results.
    """
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def scrape_one(index: int, target_url: str) -> dict:
        async with semaphore:
            try:
                result = await scrape(
                    url=target_url,
                    formats=formats,
                    only_main_content=only_main_content,
                    mode=mode,
                    cache=cache,
                    cache_dir=cache_dir,
                    cache_ttl_seconds=cache_ttl_seconds,
                    user_agent=user_agent,
                    headers=headers,
                    accept_invalid_certs=accept_invalid_certs,
                    pattern_mode=pattern_mode,
                    proxy_url=proxy_url,
                    proxy_urls=proxy_urls,
                )
                result["index"] = index
                return result
            except Exception as error:
                return {
                    "url": target_url,
                    "index": index,
                    "error": str(error),
                }

    results = await asyncio.gather(*(scrape_one(index, target_url) for index, target_url in enumerate(urls)))
    return {
        "total": len(urls),
        "completed": sum(1 for item in results if "error" not in item),
        "failed": sum(1 for item in results if "error" in item),
        "data": results,
    }


async def map_site(
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
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> dict:
    """Map a site into discovered URLs with optional relevance ordering.

    Args:
        url: Starting URL to map.
        search: Optional relevance query.
        limit: Maximum pages to include.
        mode: Crawl strategy.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns.
        exclude_patterns: Optional exclude patterns.
        pattern_mode: Pattern matching mode.
        respect_robots_txt: Whether to enforce robots.txt access rules.
        sitemap_url: Optional sitemap URL to seed the crawl.
        seed_sitemap: Whether sitemap URLs should seed the crawl.
        user_agent: User agent name used for robots.txt evaluation.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.

    Returns:
        URL map payload with optional relevance scores.
    """
    crawl_result = await crawl(
        url=url,
        max_pages=limit,
        mode=mode,
        max_depth=limit,
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
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
    )

    items = []
    for result in crawl_result["results"]:
        if "error" in result or "blocked_by" in result:
            continue
        item = {
            "url": result.get("final_url") or result.get("url"),
            "title": result.get("title", ""),
            "description": result.get("description", ""),
        }
        if search:
            item["score"] = score_map_result(result, search=search)
        items.append(item)

    if search:
        items.sort(key=lambda item: (item.get("score", 0.0), item.get("url", "")), reverse=True)

    deduped_urls = []
    seen_urls = set()
    for item in items:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        deduped_urls.append(item)

    return {
        "url": url,
        "search": search,
        "total": len(deduped_urls[:limit]),
        "urls": deduped_urls[:limit],
    }


async def crawl_one_page(
    session: AsyncSession,
    url: str,
    depth: int,
    mode: Literal["fast", "auto"],
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_headers: bool = False,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    proxy_index: int = 0,
    full_resources: bool = False,
) -> tuple[dict, list[str]]:
    """Fetch and parse a single crawled page.

    Args:
        session: Async HTTP session.
        url: Page URL to fetch.
        depth: Crawl depth for the page.
        mode: Crawl mode.
        allow_subdomains: Whether subdomains should be considered in-scope.
        allowed_domains: Additional explicitly allowed domains.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        include_headers: Whether to include response headers.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        proxy_index: Round-robin proxy selection index.
        full_resources: Whether to include resource URLs in discovery.

    Returns:
        Tuple containing the result payload and discovered links.
    """
    try:
        return await _fetch_page(
            url=url,
            mode="http" if mode == "fast" else "auto",
            allow_subdomains=allow_subdomains,
            allowed_domains=allowed_domains,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            include_headers=include_headers,
            session=session,
            depth=depth,
            cache=cache,
            cache_dir=cache_dir,
            cache_ttl_seconds=cache_ttl_seconds,
            user_agent=user_agent,
            headers=headers,
            accept_invalid_certs=accept_invalid_certs,
            pattern_mode=pattern_mode,
            proxy_url=proxy_url,
            proxy_urls=proxy_urls,
            proxy_index=proxy_index,
            full_resources=full_resources,
        )
    except Exception as error:
        return {"url": url, "depth": depth, "error": str(error)}, []


async def crawl(
    url: str,
    max_pages: int = 10,
    mode: Literal["fast", "auto"] = "auto",
    max_concurrency: int = 4,
    max_depth: int = 2,
    allow_subdomains: bool = False,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
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
    allowed_domains: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    full_resources: bool = False,
    dedupe_by_signature: bool = False,
    delay_ms: int = 0,
    path_delays: dict[str, int] | None = None,
) -> dict:
    """Crawl a site using a browser-assisted or HTTP-only strategy.

    Args:
        url: Starting URL to crawl.
        max_pages: Maximum pages to crawl.
        mode: Crawl strategy, either ``fast`` or ``auto``.
        max_concurrency: Maximum parallel HTTP requests.
        max_depth: Maximum crawl depth from the start URL.
        allow_subdomains: Whether subdomains should be considered in-scope.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
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
        allowed_domains: Additional explicitly allowed domains.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        full_resources: Whether to include resource URLs in crawl discovery.
        dedupe_by_signature: Whether to stop expanding duplicate-content pages.
        delay_ms: Default crawl delay in milliseconds.
        path_delays: Optional per-path delay mapping in milliseconds.

    Returns:
        Crawled URL metadata and crawl statistics.
    """
    start_url = strip_fragment(url)
    base_domain = urlparse(url).netloc
    visited = set()
    normalized_budget = normalize_crawl_budget(budget)
    normalized_delay_map = normalize_delay_map(path_delays)
    normalized_proxy_urls = normalize_proxy_urls(proxy_url=proxy_url, proxy_urls=proxy_urls)
    queued = set()
    to_visit = deque()
    results = []
    seen_signatures = {}
    max_concurrency = max(1, max_concurrency)
    robots_info = {
        "robots_url": None,
        "parser": None,
        "crawl_delay": None,
        "sitemaps": [],
        "status_code": None,
    }
    sitemap_seeds = []
    allowed_domain_set = normalize_allowed_domains(allowed_domains)

    request_headers = build_http_headers(user_agent=user_agent, headers=headers)
    async with AsyncSession(impersonate="chrome", timeout=15, headers=request_headers) as session:
        if consume_crawl_budget(start_url, normalized_budget):
            queued.add(start_url)
            to_visit.append((start_url, 0))

        if respect_robots_txt or seed_sitemap or sitemap_url:
            robots_info = await load_robots_rules(session, start_url, user_agent=user_agent)

        if seed_sitemap or sitemap_url:
            candidate_sitemaps = []
            if sitemap_url:
                candidate_sitemaps.append(sitemap_url)
            if seed_sitemap:
                candidate_sitemaps.extend(robots_info["sitemaps"])

            if seed_sitemap and not candidate_sitemaps:
                try:
                    root_page = await request_page_with_verify_override(
                        session,
                        start_url,
                        accept_invalid_certs=accept_invalid_certs,
                        proxy_url=pick_proxy(normalized_proxy_urls, 0),
                    )
                    candidate_sitemaps.extend(
                        discover_sitemap_urls_from_html(root_page["html"], root_page["final_url"])
                    )
                except Exception:
                    pass

            seen_sitemaps = set()
            filtered_sitemaps = []
            for candidate in candidate_sitemaps:
                normalized = strip_fragment(candidate)
                if normalized not in seen_sitemaps:
                    seen_sitemaps.add(normalized)
                    filtered_sitemaps.append(normalized)

            sitemap_seeds = await collect_sitemap_urls(session, filtered_sitemaps, limit=max_pages * 10)
            for sitemap_seed in sitemap_seeds:
                normalized_seed = strip_fragment(sitemap_seed)
                if normalized_seed in queued:
                    continue
                if not is_same_scope(
                    normalized_seed,
                    base_domain,
                    allow_subdomains=allow_subdomains,
                    allowed_domains=allowed_domain_set,
                ):
                    continue
                if not matches_patterns_with_mode(normalized_seed, include_patterns, pattern_mode=pattern_mode):
                    continue
                if exclude_patterns and matches_patterns_with_mode(
                    normalized_seed,
                    exclude_patterns,
                    pattern_mode=pattern_mode,
                ):
                    continue
                if consume_crawl_budget(normalized_seed, normalized_budget):
                    queued.add(normalized_seed)
                    to_visit.append((normalized_seed, 0))

        while to_visit and len(visited) < max_pages:
            remaining_slots = max_pages - len(visited)
            batch_size = min(max_concurrency, remaining_slots)
            batch = []

            while to_visit and len(batch) < batch_size:
                current_url, current_depth = to_visit.popleft()
                queued.discard(current_url)
                if current_url in visited:
                    continue
                if current_depth > max_depth:
                    continue
                if respect_robots_txt and robots_info["parser"] is not None:
                    if not robots_info["parser"].can_fetch(user_agent, current_url):
                        visited.add(current_url)
                        results.append(
                            {
                                "url": current_url,
                                "depth": current_depth,
                                "blocked_by": "robots.txt",
                            }
                        )
                        continue
                visited.add(current_url)
                batch.append((current_url, current_depth))

            if not batch:
                continue

            page_results = await asyncio.gather(
                *(
                    crawl_one_page(
                        session,
                        current_url,
                        current_depth,
                        mode,
                        allow_subdomains=allow_subdomains,
                        allowed_domains=allowed_domains,
                        include_patterns=include_patterns,
                        exclude_patterns=exclude_patterns,
                        include_headers=include_headers,
                        cache=cache,
                        cache_dir=cache_dir,
                        cache_ttl_seconds=cache_ttl_seconds,
                        user_agent=user_agent,
                        headers=headers,
                        accept_invalid_certs=accept_invalid_certs,
                        pattern_mode=pattern_mode,
                        proxy_url=proxy_url,
                        proxy_urls=normalized_proxy_urls,
                        proxy_index=len(results) + batch_index,
                        full_resources=full_resources,
                    )
                    for batch_index, (current_url, current_depth) in enumerate(batch)
                )
            )

            for result, links in page_results:
                signature = result.get("signature")
                if signature and signature in seen_signatures:
                    result["duplicate_of_signature"] = signature
                    result["is_duplicate"] = True
                elif signature:
                    seen_signatures[signature] = result["url"]
                results.append(result)
                if dedupe_by_signature and result.get("is_duplicate"):
                    continue
                next_depth = result.get("depth", 0) + 1
                if next_depth > max_depth:
                    continue
                for link in links:
                    normalized_link = strip_fragment(link)
                    if normalized_link not in visited and normalized_link not in queued:
                        if consume_crawl_budget(normalized_link, normalized_budget):
                            queued.add(normalized_link)
                            to_visit.append((normalized_link, next_depth))

            if results:
                batch_delay_ms = 0
                for result, _ in page_results:
                    batch_delay_ms = max(
                        batch_delay_ms,
                        resolve_delay_ms(
                            result.get("final_url", result.get("url", "")),
                            normalized_delay_map,
                            default_delay_ms=delay_ms,
                        ),
                    )

                robots_delay_ms = 0
                if robots_info["crawl_delay"]:
                    robots_delay_ms = int(float(robots_info["crawl_delay"]) * 1000)

                effective_delay_ms = max(batch_delay_ms, robots_delay_ms)
                if effective_delay_ms > 0:
                    await asyncio.sleep(effective_delay_ms / 1000)

    return {
        "start_url": url,
        "mode": mode,
        "max_concurrency": max_concurrency,
        "max_depth": max_depth,
        "allow_subdomains": allow_subdomains,
        "allowed_domains": allowed_domains or [],
        "respect_robots_txt": respect_robots_txt,
        "robots_url": robots_info["robots_url"],
        "crawl_delay": robots_info["crawl_delay"],
        "sitemap_seed_count": len(sitemap_seeds),
        "budget": budget or {},
        "budget_remaining": normalized_budget,
        "cache": cache,
        "pattern_mode": pattern_mode,
        "proxy_urls": normalized_proxy_urls,
        "full_resources": full_resources,
        "dedupe_by_signature": dedupe_by_signature,
        "delay_ms": delay_ms,
        "path_delays": normalized_delay_map,
        "pages_crawled": len(results),
        "results": results,
    }


async def screenshot(url: str, width: int = -1, height: int = -1, full_page: bool = True) -> bytes:
    """Take a screenshot of a webpage and compress it as JPEG.

    Args:
        url: URL to capture.
        width: Requested viewport width, or ``-1`` for auto.
        height: Requested viewport height, or ``-1`` for auto.
        full_page: Whether to capture the full page.

    Returns:
        JPEG-compressed screenshot bytes.
    """
    temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix=".png")
    os.close(temp_file_descriptor)

    try:
        async with browser_session(headless=False) as browser:
            page = await browser.get(url)
            await page.sleep(2)

            if width > 0 and height > 0:
                await page.set_window_size(width, height)

            await page.save_screenshot(filename=temp_file_path, format="png", full_page=full_page)

        image = PILImage.open(temp_file_path)
        image = image.convert("RGB")

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)
        output.seek(0)
        return output.read()
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

"""Reusable SDK operations for web search, fetch, crawl, and screenshot."""

import asyncio
import io
import os
import tempfile
from collections import deque
from typing import Literal
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from PIL import Image as PILImage

from .browser import browser_session
from .cache import load_cached_page, save_cached_page
from .discovery import collect_sitemap_urls, load_robots_rules
from .google import (
    extract_ai_overview,
    extract_organic_results,
    extract_people_also_ask,
    extract_video_results,
)
from .page import (
    consume_crawl_budget,
    is_same_scope,
    matches_patterns,
    normalize_headers,
    normalize_crawl_budget,
    parse_page_meta,
    render_page_content,
    should_browser_fallback,
    strip_fragment,
)
from .searxng import search_searxng


async def websearch(
    query: str,
    max_results: int = 10,
    pages: int = 1,
    provider: Literal["google", "searxng"] = "google",
    searxng_url: str | None = None,
) -> dict:
    """Search the web through Google or SearXNG and normalize the results.

    Args:
        query: Search query string.
        max_results: Maximum results per page.
        pages: Number of pages to scrape.
        provider: Search provider to use.
        searxng_url: Optional SearXNG base URL.

    Returns:
        Search results with links, titles, descriptions, and metadata.
    """
    if provider == "searxng":
        return await search_searxng(
            query=query,
            max_results=max_results,
            pages=pages,
            searxng_url=searxng_url,
        )

    all_results = []
    all_videos = []
    all_paa = []
    ai_overview = ""
    seen_urls = set()
    current_page = 0

    async with browser_session(headless=False) as browser:
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
        "count": len(all_results),
    }


async def request_page(session: AsyncSession, url: str) -> dict:
    """Fetch a page over HTTP with an SSL-verification fallback.

    Args:
        session: Async HTTP session.
        url: URL to fetch.

    Returns:
        Structured HTTP response data.
    """
    try:
        response = await session.get(url)
        ssl_fallback_used = False
    except Exception as error:
        if "SSL certificate problem" not in str(error):
            raise
        response = await session.get(url, verify=False)
        ssl_fallback_used = True

    return {
        "url": url,
        "final_url": response.url,
        "status_code": response.status_code,
        "headers": normalize_headers(response.headers),
        "content_type": response.headers.get("content-type", ""),
        "html": response.text,
        "ssl_fallback_used": ssl_fallback_used,
    }


async def request_browser_page(url: str) -> dict:
    """Fetch a page through the browser.

    Args:
        url: URL to fetch.

    Returns:
        Structured browser response data.
    """
    async with browser_session(headless=False) as browser:
        page = await browser.get(url)
        await page.sleep(2)

        return {
            "url": url,
            "final_url": page.url,
            "status_code": None,
            "headers": {},
            "content_type": "text/html",
            "html": await page.get_content(),
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
        "title": page_meta["title"],
        "description": page_meta["description"],
        "links_found": len(page_meta["links"]),
        "metadata": page_meta["metadata"],
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
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_headers: bool = False,
    include_html: bool = False,
    session: AsyncSession | None = None,
    depth: int = 0,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
) -> tuple[dict, list[str]]:
    """Fetch a page and return normalized details plus discovered links.

    Args:
        url: URL to fetch.
        mode: Fetch strategy.
        allow_subdomains: Whether subdomains should be considered in-scope.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        include_headers: Whether to include response headers.
        include_html: Whether to include raw HTML.
        session: Optional reusable HTTP session.
        depth: Crawl depth for the page.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.

    Returns:
        Tuple of page result payload and discovered links.
    """
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
            page_data = await request_browser_page(url)
            source = "browser"
        else:
            try:
                if session is None:
                    async with AsyncSession(impersonate="chrome", timeout=15) as owned_session:
                        page_data = await request_page(owned_session, url)
                else:
                    page_data = await request_page(session, url)
            except Exception:
                if mode != "auto":
                    raise
                page_data = await request_browser_page(url)
                source = "browser"
                fallback_used = True

            if source == "http" and mode == "auto" and should_browser_fallback(page_data["status_code"], page_data["html"]):
                browser_data = await request_browser_page(url)
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
    page_meta = parse_page_meta(
        page_data["html"],
        page_data["final_url"],
        scope_domain,
        allow_subdomains=allow_subdomains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )

    result = build_page_result(
        page_data,
        page_meta,
        depth=depth,
        include_headers=include_headers,
        include_html=include_html,
        source=source,
        fallback_used=fallback_used,
        cache_hit=cache_hit,
    )
    return result, page_meta["links"]


async def fetch_page(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    allow_subdomains: bool = False,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_headers: bool = False,
    include_html: bool = False,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
) -> dict:
    """Fetch a page and return structured details.

    Args:
        url: URL to fetch.
        mode: Fetch strategy.
        allow_subdomains: Whether subdomains should be considered in-scope.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        include_headers: Whether to include response headers.
        include_html: Whether to include raw HTML.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.

    Returns:
        Structured page details and discovered links.
    """
    result, _ = await _fetch_page(
        url=url,
        mode=mode,
        allow_subdomains=allow_subdomains,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        include_headers=include_headers,
        include_html=include_html,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    return result


async def fetch(
    url: str,
    output_format: Literal["markdown", "text"] = "markdown",
    mode: Literal["auto", "http", "browser"] = "auto",
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
) -> str:
    """Fetch a URL and convert the page into markdown or plain text.

    Args:
        url: URL to fetch.
        output_format: Either ``markdown`` or ``text``.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.

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
    )
    return render_page_content(page["html"], output_format)


async def crawl_one_page(
    session: AsyncSession,
    url: str,
    depth: int,
    mode: Literal["fast", "auto"],
    allow_subdomains: bool = False,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_headers: bool = False,
    cache: bool = False,
    cache_dir: str | None = None,
    cache_ttl_seconds: int | None = None,
) -> tuple[dict, list[str]]:
    """Fetch and parse a single crawled page.

    Args:
        session: Async HTTP session.
        url: Page URL to fetch.
        depth: Crawl depth for the page.
        mode: Crawl mode.
        allow_subdomains: Whether subdomains should be considered in-scope.
        include_patterns: Optional include patterns for discovered links.
        exclude_patterns: Optional exclude patterns for discovered links.
        include_headers: Whether to include response headers.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.

    Returns:
        Tuple containing the result payload and discovered links.
    """
    try:
        return await _fetch_page(
            url=url,
            mode="http" if mode == "fast" else "auto",
            allow_subdomains=allow_subdomains,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            include_headers=include_headers,
            session=session,
            depth=depth,
            cache=cache,
            cache_dir=cache_dir,
            cache_ttl_seconds=cache_ttl_seconds,
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

    Returns:
        Crawled URL metadata and crawl statistics.
    """
    start_url = strip_fragment(url)
    base_domain = urlparse(url).netloc
    visited = set()
    normalized_budget = normalize_crawl_budget(budget)
    queued = set()
    to_visit = deque()
    results = []
    max_concurrency = max(1, max_concurrency)
    robots_info = {
        "robots_url": None,
        "parser": None,
        "crawl_delay": None,
        "sitemaps": [],
        "status_code": None,
    }
    sitemap_seeds = []

    async with AsyncSession(impersonate="chrome", timeout=15) as session:
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
                if not is_same_scope(normalized_seed, base_domain, allow_subdomains=allow_subdomains):
                    continue
                if not matches_patterns(normalized_seed, include_patterns):
                    continue
                if exclude_patterns and matches_patterns(normalized_seed, exclude_patterns):
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
                        include_patterns=include_patterns,
                        exclude_patterns=exclude_patterns,
                        include_headers=include_headers,
                        cache=cache,
                        cache_dir=cache_dir,
                        cache_ttl_seconds=cache_ttl_seconds,
                    )
                    for current_url, current_depth in batch
                )
            )

            for result, links in page_results:
                results.append(result)
                next_depth = result.get("depth", 0) + 1
                if next_depth > max_depth:
                    continue
                for link in links:
                    normalized_link = strip_fragment(link)
                    if normalized_link not in visited and normalized_link not in queued:
                        if consume_crawl_budget(normalized_link, normalized_budget):
                            queued.add(normalized_link)
                            to_visit.append((normalized_link, next_depth))

            if robots_info["crawl_delay"]:
                await asyncio.sleep(float(robots_info["crawl_delay"]))

    return {
        "start_url": url,
        "mode": mode,
        "max_concurrency": max_concurrency,
        "max_depth": max_depth,
        "allow_subdomains": allow_subdomains,
        "respect_robots_txt": respect_robots_txt,
        "robots_url": robots_info["robots_url"],
        "crawl_delay": robots_info["crawl_delay"],
        "sitemap_seed_count": len(sitemap_seeds),
        "budget": budget or {},
        "budget_remaining": normalized_budget,
        "cache": cache,
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

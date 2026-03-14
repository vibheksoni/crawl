"""Reusable SDK operations for web search, fetch, crawl, and screenshot."""

import asyncio
import heapq
import io
import os
import tempfile
import time
import warnings
from collections import deque
from typing import Literal
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from curl_cffi.requests import AsyncSession
from PIL import Image as PILImage

from .app_state import extract_app_state, render_app_state_text
from .article import extract_article_content
from .article_metadata import extract_article_metadata
from .article_pagination import discover_next_page_candidates, titles_look_related
from .autoscale import choose_autoscaled_concurrency, sample_system_load
from .browser import (
    browser_session,
    collect_request_capture,
    configure_page_request_settings,
    enable_request_capture,
    perform_basic_interactions,
)
from .cache import (
    build_cache_revalidation_headers,
    is_cache_entry_fresh,
    load_cache_entry,
    merge_revalidated_page_data,
    save_cached_page,
)
from .chunking import rank_text_chunks
from .contacts import extract_contacts_from_html
from .discovery import collect_sitemap_urls, discover_sitemap_urls_from_html, load_robots_rules
from .crawl_state import load_crawl_state, save_crawl_state, serialize_frontier
from .extract import extract_structured_data
from .feeds import analyze_feed_document, discover_feed_candidates, discover_feed_spider_links, merge_feed_candidates
from .forms import extract_forms
from .google import (
    extract_ai_overview,
    extract_organic_results,
    extract_people_also_ask,
    extract_video_results,
)
from .hooks import run_named_hook
from .page import (
    compute_page_signature,
    consume_crawl_budget,
    detect_block_reason,
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
from .similarity import (
    add_simhash_to_index,
    compute_simhash,
    find_simhash_match,
    format_simhash,
    parse_simhash,
)
from .tech import fingerprint_page, grep_page
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


def score_url_candidate(url: str, query: str | None = None) -> float:
    """Score a queued URL candidate for best-first crawling.

    Args:
        url: Candidate URL.
        query: Optional crawl relevance query.

    Returns:
        Candidate score.
    """
    if not query:
        return 0.0

    lowered_url = url.lower()
    score = 0.0
    for token in tokenize_query(query):
        if token in lowered_url:
            score += 1.0
        path_parts = lowered_url.replace("-", "/").replace("_", "/")
        if token in path_parts:
            score += 0.5
    return score


def frontier_push(
    frontier,
    url: str,
    depth: int,
    strategy: Literal["bfs", "best_first"] = "bfs",
    query: str | None = None,
) -> None:
    """Push a URL into a crawl frontier.

    Args:
        frontier: Frontier container.
        url: URL to enqueue.
        depth: Crawl depth.
        strategy: Frontier strategy.
        query: Optional relevance query.
    """
    if strategy == "best_first":
        score = score_url_candidate(url, query=query)
        heapq.heappush(frontier, (-score, depth, url))
    else:
        frontier.append((url, depth))


def frontier_pop(
    frontier,
    strategy: Literal["bfs", "best_first"] = "bfs",
) -> tuple[str, int]:
    """Pop the next URL from a crawl frontier.

    Args:
        frontier: Frontier container.
        strategy: Frontier strategy.

    Returns:
        URL and depth pair.
    """
    if strategy == "best_first":
        _, depth, url = heapq.heappop(frontier)
        return url, depth
    return frontier.popleft()


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
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
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
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

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
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
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
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
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
        cache_revalidate: Whether stale scraped-result cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override for result scraping.
        headers: Optional extra headers for result scraping.
        accept_invalid_certs: Whether to ignore certificate errors for result scraping.
        max_retries: Maximum retry attempts after the initial request for scraped results.
        retry_backoff_ms: Base retry backoff in milliseconds for scraped results.

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
            cache_revalidate=cache_revalidate,
            user_agent=user_agent,
            headers=headers,
            accept_invalid_certs=accept_invalid_certs,
            proxy_url=proxy_url,
            proxy_urls=proxy_urls,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
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
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    retry_status_codes: list[int] | None = None,
) -> dict:
    """Fetch a page over HTTP with configurable certificate handling.

    Args:
        session: Async HTTP session.
        url: URL to fetch.
        headers: Optional per-request headers.
        accept_invalid_certs: Whether to skip certificate verification.
        proxy_url: Optional proxy URL.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        retry_status_codes: Optional retryable status override.

    Returns:
        Structured HTTP response data.
    """
    started_at = time.perf_counter()
    response = None
    ssl_fallback_used = False
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = await session.get(
                url,
                headers=headers,
                verify=False if accept_invalid_certs else None,
                proxy=proxy_url,
            )
            ssl_fallback_used = accept_invalid_certs
        except Exception as error:
            last_error = error
            if not accept_invalid_certs and "SSL certificate problem" in str(error):
                response = await session.get(url, headers=headers, verify=False, proxy=proxy_url)
                ssl_fallback_used = True
            else:
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(compute_backoff_ms(attempt, retry_backoff_ms) / 1000)
                continue

        if response is not None and should_retry_status(response.status_code, retry_status_codes=retry_status_codes):
            if attempt >= max_retries:
                break
            retry_after_ms = parse_retry_after_ms(normalize_headers(response.headers))
            delay_ms = retry_after_ms if retry_after_ms is not None else compute_backoff_ms(attempt, retry_backoff_ms)
            await asyncio.sleep(delay_ms / 1000)
            continue
        break

    if response is None and last_error is not None:
        raise last_error

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


def merge_http_headers(
    base_headers: dict[str, str] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Merge two HTTP header mappings for a single request.

    Args:
        base_headers: Existing header mapping.
        extra_headers: Additional headers that should override duplicates.

    Returns:
        Combined header mapping or ``None``.
    """
    if not base_headers and not extra_headers:
        return None
    merged = {}
    if base_headers:
        merged.update(base_headers)
    if extra_headers:
        merged.update(extra_headers)
    return merged


def default_retry_status_codes() -> list[int]:
    """Return the default HTTP status codes that should be retried."""
    return [408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524]


def parse_retry_after_ms(headers: dict[str, str] | None = None) -> int | None:
    """Parse a Retry-After header into milliseconds when available.

    Args:
        headers: Response headers.

    Returns:
        Delay in milliseconds or ``None``.
    """
    if not headers:
        return None
    raw_value = headers.get("retry-after")
    if not raw_value:
        raw_value = headers.get("Retry-After")
    if not raw_value:
        return None
    try:
        return max(0, int(float(raw_value) * 1000))
    except ValueError:
        return None


def should_retry_status(status_code: int | None, retry_status_codes: list[int] | None = None) -> bool:
    """Determine whether a status code should trigger a retry.

    Args:
        status_code: HTTP status code.
        retry_status_codes: Optional retryable status override.

    Returns:
        ``True`` if the status should be retried.
    """
    if status_code is None:
        return False
    codes = retry_status_codes or default_retry_status_codes()
    return status_code in codes


def compute_backoff_ms(attempt: int, retry_backoff_ms: int = 500) -> int:
    """Compute exponential backoff in milliseconds.

    Args:
        attempt: Zero-based retry attempt.
        retry_backoff_ms: Base backoff.

    Returns:
        Backoff duration in milliseconds.
    """
    return max(0, retry_backoff_ms) * (2**attempt)


def compute_auto_throttle_delay_ms(
    batch_results: list[dict],
    minimum_delay_ms: int = 0,
    maximum_delay_ms: int = 5000,
) -> int:
    """Compute a simple adaptive delay from batch timings and retry hints.

    Args:
        batch_results: Crawl result batch payloads.
        minimum_delay_ms: Lower bound for the delay.
        maximum_delay_ms: Upper bound for the delay.

    Returns:
        Adaptive delay in milliseconds.
    """
    elapsed_values = [item.get("elapsed_ms", 0) for item in batch_results if item.get("elapsed_ms")]
    retry_after_values = [
        parse_retry_after_ms(item.get("headers"))
        for item in batch_results
        if item.get("headers")
    ]
    retry_after_values = [value for value in retry_after_values if value is not None]

    delay_ms = minimum_delay_ms
    if elapsed_values:
        average_elapsed = sum(elapsed_values) / len(elapsed_values)
        delay_ms = max(delay_ms, int(average_elapsed * 0.5))
    if retry_after_values:
        delay_ms = max(delay_ms, max(retry_after_values))

    return min(maximum_delay_ms, max(minimum_delay_ms, delay_ms))


async def request_browser_page(
    url: str,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    session_dir: str | None = None,
    capture_requests: bool = False,
    interaction_mode: Literal["none", "auto"] = "none",
    max_interactions: int = 3,
) -> dict:
    """Fetch a page through the browser.

    Args:
        url: URL to fetch.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional proxy URL.
        session_dir: Optional persistent browser profile directory.
        capture_requests: Whether to capture browser requests.
        interaction_mode: Interaction mode for simple page interactions.
        max_interactions: Maximum interactions to perform.

    Returns:
        Structured browser response data.
    """
    started_at = time.perf_counter()
    browser_args = [f"--proxy-server={proxy_url}"] if proxy_url else None
    async with browser_session(
        headless=False,
        browser_args=browser_args,
        session_dir=session_dir,
    ) as browser:
        page = await browser.get("about:blank")
        if capture_requests:
            await enable_request_capture(page)
        await configure_page_request_settings(
            page,
            user_agent=user_agent,
            headers=headers,
            accept_invalid_certs=accept_invalid_certs,
        )
        await page.get(url)
        await page.sleep(2)
        interactions = []
        if interaction_mode == "auto":
            interactions = await perform_basic_interactions(page, max_clicks=max_interactions)
            if interactions:
                await page.sleep(1)

        html = await page.get_content()
        requests = await collect_request_capture(page) if capture_requests else []
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
            "requests": requests,
            "interactions": interactions,
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
    forms: list[dict] | None = None,
    requests: list[dict] | None = None,
    interactions: list[str] | None = None,
    app_state: dict | None = None,
    contacts: dict | None = None,
    blocked_reason: str | None = None,
    technologies: dict | None = None,
    similarity_signature: str | None = None,
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
        app_state: Optional embedded hydration and structured payloads.
        contacts: Optional extracted contact and social details.
        blocked_reason: Optional detected block reason.
        technologies: Optional technology fingerprint payload.

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
    if similarity_signature is not None:
        result["similarity_signature"] = similarity_signature

    if "cache_revalidated" in page_data:
        result["cache_revalidated"] = page_data["cache_revalidated"]
    if "cache_not_modified" in page_data:
        result["cache_not_modified"] = page_data["cache_not_modified"]
    if "revalidation_status_code" in page_data:
        result["revalidation_status_code"] = page_data["revalidation_status_code"]

    if forms is not None:
        result["forms"] = forms
    if requests is not None:
        result["requests"] = requests
    if interactions is not None:
        result["interactions"] = interactions
    if app_state is not None:
        result["app_state"] = app_state
    if contacts is not None:
        result["contacts"] = contacts
    if blocked_reason is not None:
        result["blocked_reason"] = blocked_reason
    if technologies is not None:
        result["technologies"] = technologies

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
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    proxy_index: int = 0,
    full_resources: bool = False,
    include_forms: bool = False,
    include_form_fill_suggestions: bool = False,
    include_requests: bool = False,
    interaction_mode: Literal["none", "auto"] = "none",
    max_interactions: int = 3,
    session_dir: str | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    retry_status_codes: list[int] | None = None,
    include_app_state: bool = False,
    include_contacts: bool = False,
    hooks: dict | None = None,
    include_technologies: bool = False,
    technology_aggression: int = 1,
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
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        proxy_index: Round-robin proxy selection index.
        full_resources: Whether to include resource URLs in discovery.
        include_forms: Whether to extract forms.
        include_form_fill_suggestions: Whether to include form fill previews.
        include_requests: Whether to capture browser requests.
        interaction_mode: Interaction mode for simple page interactions.
        max_interactions: Maximum interactions to perform.
        session_dir: Optional persistent browser profile directory.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        retry_status_codes: Optional retryable status override.
        include_app_state: Whether to extract embedded hydration payloads.
        include_contacts: Whether to extract contact and social details.
        hooks: Optional lifecycle hook mapping.
        include_technologies: Whether to extract technology fingerprints.
        technology_aggression: Technology fingerprint aggression level.

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
    blocked_reason = None
    cached_entry = None
    revalidation_headers = None

    if cache:
        cached_entry = load_cache_entry(url=url, mode=mode, cache_dir=cache_dir)
        if cached_entry is not None and is_cache_entry_fresh(
            cached_entry["fetched_at"],
            cache_ttl_seconds=cache_ttl_seconds,
        ):
            page_data = dict(cached_entry["page_data"])
            page_data["cache_fetched_at"] = cached_entry["fetched_at"]
            source = page_data.get("source", source)
            fallback_used = page_data.get("fallback_used", False)
            cache_hit = True
        elif cached_entry is not None and cache_revalidate and mode != "browser":
            revalidation_headers = build_cache_revalidation_headers(cached_entry["page_data"])

    if page_data is None:
        await run_named_hook(
            hooks,
            "on_request_start",
            {
                "url": url,
                "mode": mode,
                "proxy_url": selected_proxy,
                "depth": depth,
            },
        )
        if mode == "browser":
            page_data = await request_browser_page(
                url,
                user_agent=user_agent,
                headers=headers,
                accept_invalid_certs=accept_invalid_certs,
                proxy_url=selected_proxy,
                session_dir=session_dir,
                capture_requests=include_requests,
                interaction_mode=interaction_mode,
                max_interactions=max_interactions,
            )
            source = "browser"
        else:
            try:
                request_headers = build_http_headers(user_agent=user_agent, headers=headers)
                per_request_headers = merge_http_headers(extra_headers=revalidation_headers)
                if session is None:
                    async with AsyncSession(
                        impersonate="chrome",
                        timeout=15,
                        headers=request_headers,
                    ) as owned_session:
                        page_data = await request_page_with_verify_override(
                            owned_session,
                            url,
                            headers=per_request_headers,
                            accept_invalid_certs=accept_invalid_certs,
                            proxy_url=selected_proxy,
                            max_retries=max_retries,
                            retry_backoff_ms=retry_backoff_ms,
                            retry_status_codes=retry_status_codes,
                        )
                else:
                    page_data = await request_page_with_verify_override(
                        session,
                        url,
                        headers=per_request_headers,
                        accept_invalid_certs=accept_invalid_certs,
                        proxy_url=selected_proxy,
                        max_retries=max_retries,
                        retry_backoff_ms=retry_backoff_ms,
                        retry_status_codes=retry_status_codes,
                    )

                if (
                    cached_entry is not None
                    and revalidation_headers
                    and page_data.get("status_code") == 304
                ):
                    page_data = merge_revalidated_page_data(
                        cached_entry["page_data"],
                        page_data,
                        fetched_at=cached_entry["fetched_at"],
                    )
                    cache_hit = True
                elif cached_entry is not None and revalidation_headers:
                    page_data["cache_revalidated"] = True
                    page_data["cache_not_modified"] = False
                    page_data["revalidation_status_code"] = page_data.get("status_code")
                    page_data["cache_fetched_at"] = cached_entry["fetched_at"]

                blocked_reason = detect_block_reason(
                    page_data.get("status_code"),
                    page_data.get("html", ""),
                    headers=page_data.get("headers"),
                )
                if blocked_reason and len(normalized_proxy_urls) > 1:
                    for proxy_attempt in range(1, len(normalized_proxy_urls)):
                        rotated_proxy = pick_proxy(normalized_proxy_urls, proxy_index + proxy_attempt)
                        if not rotated_proxy or rotated_proxy == selected_proxy:
                            continue
                        try:
                            if session is None:
                                async with AsyncSession(
                                    impersonate="chrome",
                                    timeout=15,
                                    headers=request_headers,
                                ) as rotated_session:
                                    rotated_data = await request_page_with_verify_override(
                                        rotated_session,
                                        url,
                                        headers=per_request_headers,
                                        accept_invalid_certs=accept_invalid_certs,
                                        proxy_url=rotated_proxy,
                                        max_retries=0,
                                        retry_backoff_ms=retry_backoff_ms,
                                        retry_status_codes=retry_status_codes,
                                    )
                            else:
                                rotated_data = await request_page_with_verify_override(
                                    session,
                                    url,
                                    headers=per_request_headers,
                                    accept_invalid_certs=accept_invalid_certs,
                                    proxy_url=rotated_proxy,
                                    max_retries=0,
                                    retry_backoff_ms=retry_backoff_ms,
                                    retry_status_codes=retry_status_codes,
                                )
                        except Exception:
                            continue
                        rotated_block_reason = detect_block_reason(
                            rotated_data.get("status_code"),
                            rotated_data.get("html", ""),
                            headers=rotated_data.get("headers"),
                        )
                        if rotated_block_reason is None:
                            page_data = rotated_data
                            page_data["proxy_rotated"] = True
                            page_data["proxy_url"] = rotated_proxy
                            blocked_reason = None
                            break
            except Exception:
                if mode != "auto":
                    raise
                page_data = await request_browser_page(
                    url,
                    user_agent=user_agent,
                    headers=headers,
                    accept_invalid_certs=accept_invalid_certs,
                    proxy_url=selected_proxy,
                    session_dir=session_dir,
                    capture_requests=include_requests,
                    interaction_mode=interaction_mode,
                    max_interactions=max_interactions,
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
                    session_dir=session_dir,
                    capture_requests=include_requests,
                    interaction_mode=interaction_mode,
                    max_interactions=max_interactions,
                )
                browser_data["status_code"] = page_data["status_code"]
                browser_data["ssl_fallback_used"] = page_data["ssl_fallback_used"]
                page_data = browser_data
                source = "browser"
                fallback_used = True
                blocked_reason = detect_block_reason(
                    page_data.get("status_code"),
                    page_data.get("html", ""),
                    headers=page_data.get("headers"),
                )

        page_data["source"] = source
        page_data["fallback_used"] = fallback_used
        page_data["blocked_reason"] = blocked_reason
        if cache:
            save_cached_page(url=url, mode=mode, page_data=page_data, cache_dir=cache_dir)
    else:
        blocked_reason = page_data.get("blocked_reason")

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
        similarity_text = render_page_content(page_data["html"], "text", only_main_content=True)
        similarity_value = compute_simhash(similarity_text)
        similarity_signature = format_simhash(similarity_value) if similarity_value is not None else None
        forms = (
            extract_forms(
                page_data["html"],
                page_data["final_url"],
                include_fill_suggestions=include_form_fill_suggestions,
            )
            if include_forms
            else None
        )
        app_state = extract_app_state(page_data["html"]) if include_app_state else None
        contacts = extract_contacts_from_html(page_data["html"], page_data["final_url"]) if include_contacts else None
        technologies = (
            fingerprint_page(
                page_data["final_url"],
                page_data["html"],
                headers=page_data.get("headers"),
                aggression=technology_aggression,
            )
            if include_technologies
            else None
        )
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
        similarity_signature = None
        forms = [] if include_forms else None
        app_state = None
        contacts = None
        technologies = None

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
        forms=forms,
        requests=page_data.get("requests") if include_requests else None,
        interactions=page_data.get("interactions") or None,
        app_state=app_state,
        contacts=contacts,
        blocked_reason=blocked_reason,
        technologies=technologies,
        similarity_signature=similarity_signature,
    )
    await run_named_hook(hooks, "on_request_end", result)
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
    cache_revalidate: bool = False,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    full_resources: bool = False,
    include_forms: bool = False,
    include_form_fill_suggestions: bool = False,
    include_requests: bool = False,
    interaction_mode: Literal["none", "auto"] = "none",
    max_interactions: int = 3,
    session_dir: str | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    retry_status_codes: list[int] | None = None,
    include_app_state: bool = False,
    include_contacts: bool = False,
    hooks: dict | None = None,
    include_technologies: bool = False,
    technology_aggression: int = 1,
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
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        full_resources: Whether to include resource URLs in discovery.
        include_forms: Whether to extract forms.
        include_form_fill_suggestions: Whether to include form fill previews.
        include_requests: Whether to capture browser requests.
        interaction_mode: Interaction mode for simple page interactions.
        max_interactions: Maximum interactions to perform.
        session_dir: Optional persistent browser profile directory.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        retry_status_codes: Optional retryable status override.
        include_app_state: Whether to extract embedded hydration payloads.
        include_contacts: Whether to extract contact and social details.
        hooks: Optional lifecycle hook mapping.
        include_technologies: Whether to extract technology fingerprints.
        technology_aggression: Technology fingerprint aggression level.

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
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        pattern_mode=pattern_mode,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        full_resources=full_resources,
        include_forms=include_forms,
        include_form_fill_suggestions=include_form_fill_suggestions,
        include_requests=include_requests,
        interaction_mode=interaction_mode,
        max_interactions=max_interactions,
        session_dir=session_dir,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        retry_status_codes=retry_status_codes,
        include_app_state=include_app_state,
        include_contacts=include_contacts,
        hooks=hooks,
        include_technologies=include_technologies,
        technology_aggression=technology_aggression,
    )
    return result


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
    only_main_content: bool = True,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    retry_status_codes: list[int] | None = None,
) -> str:
    """Fetch a URL and convert the page into markdown or plain text.

    Args:
        url: URL to fetch.
        output_format: Either ``markdown`` or ``text``.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        only_main_content: Whether to prefer main content.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        retry_status_codes: Optional retryable status override.

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
        cache_revalidate=cache_revalidate,
        user_agent=user_agent,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        retry_status_codes=retry_status_codes,
    )
    return render_page_content(page["html"], output_format, only_main_content=only_main_content)


async def scrape(
    url: str,
    formats: list[ScrapeFormat] | None = None,
    only_main_content: bool = True,
    query: str | None = None,
    mode: Literal["auto", "http", "browser"] = "auto",
    follow_pagination: bool = False,
    article_max_pages: int = 3,
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
    """Scrape a page into one or more content formats.

    Args:
        url: URL to scrape.
        formats: Requested scrape formats.
        only_main_content: Whether to prefer main content.
        query: Optional relevance query for fit markdown.
        mode: Fetch strategy.
        follow_pagination: Whether article extraction should follow likely next-page links.
        article_max_pages: Maximum article pages to merge when pagination is enabled.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Multi-format scrape payload.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=True,
        include_headers=True,
        include_app_state=bool(formats and "app_state" in formats),
        include_contacts=bool(formats and "contacts" in formats),
        include_technologies=bool(formats and "technologies" in formats),
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
    scrape_result = build_scrape_result(
        page,
        formats=formats,
        only_main_content=only_main_content,
        query=query,
    )
    if formats and "article" in formats and follow_pagination:
        article_result = await article(
            url=url,
            mode=mode,
            follow_pagination=True,
            max_pages=article_max_pages,
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
        scrape_result["article"] = article_result["article"]
    return scrape_result


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
    """Extract contact and social details from a page.

    Args:
        url: URL to inspect.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Contact extraction payload.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_contacts=True,
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
    return {
        "url": page["final_url"],
        "metadata": page.get("metadata", {}),
        "contacts": page.get("contacts", {}),
    }


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
    """Fingerprint technologies on one page or a small site slice.

    Args:
        url: Starting URL.
        mode: Fetch mode.
        max_pages: Maximum pages to fingerprint.
        max_depth: Maximum crawl depth when scanning multiple pages.
        allow_subdomains: Whether subdomains are in scope for multi-page scans.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        aggression: Technology fingerprint aggression level.

    Returns:
        Technology fingerprint payload.
    """
    scan_candidates = [url]
    if "://" not in url:
        scan_candidates = [f"https://{url}", f"http://{url}"]

    if max_pages <= 1:
        results = []
        for candidate in scan_candidates:
            try:
                page = await fetch_page(
                    url=candidate,
                    mode=mode,
                    include_technologies=True,
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
                    technology_aggression=aggression,
                )
            except Exception as error:
                results.append(
                    {
                        "url": candidate,
                        "error": str(error),
                    }
                )
                continue
            results.append(
                {
                    "url": page["final_url"],
                    "title": page.get("title", ""),
                    "technologies": page.get("technologies", {}),
                }
            )
        return {
            "start_url": url,
            "pages_scanned": len([item for item in results if "error" not in item]),
            "results": results,
            "technologies": next((item.get("technologies", {}) for item in results if item.get("technologies")), {}),
        }

    crawl_result = await crawl(
        url=url,
        max_pages=max_pages,
        max_depth=max_depth,
        mode="browser" if mode == "browser" else "auto" if mode == "auto" else "fast",
        allow_subdomains=allow_subdomains,
        include_technologies=True,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_revalidate=cache_revalidate,
        user_agent=user_agent or "*",
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        technology_aggression=aggression,
    )
    results = [
        {
            "url": item.get("final_url") or item.get("url"),
            "title": item.get("title", ""),
            "technologies": item.get("technologies", {}),
        }
        for item in crawl_result.get("results", [])
        if "error" not in item and "blocked_by" not in item
    ]
    return {
        "start_url": url,
        "pages_scanned": len(results),
        "results": results,
        "crawl": crawl_result,
    }


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
    """Search page signals with an ad-hoc literal or regex match.

    Args:
        url: Page URL.
        text: Optional case-insensitive literal.
        regex: Optional regex pattern.
        search: Search context.
        mode: Fetch mode.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Grep result payload.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=True,
        include_headers=True,
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
    return grep_page(
        page["final_url"],
        page["html"],
        headers=page.get("headers"),
        text=text,
        regex=regex,
        search=search,
    )


async def batch_scrape(
    urls: list[str],
    formats: list[ScrapeFormat] | None = None,
    only_main_content: bool = True,
    query: str | None = None,
    mode: Literal["auto", "http", "browser"] = "auto",
    max_concurrency: int = 4,
    follow_pagination: bool = False,
    article_max_pages: int = 3,
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
    """Scrape multiple URLs with bounded concurrency.

    Args:
        urls: URL list to scrape.
        formats: Requested scrape formats.
        only_main_content: Whether to prefer main content.
        query: Optional relevance query for fit markdown.
        mode: Fetch strategy.
        max_concurrency: Maximum concurrent scrape tasks.
        follow_pagination: Whether article extraction should follow likely next-page links.
        article_max_pages: Maximum article pages to merge when pagination is enabled.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

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
                    query=query,
                    mode=mode,
                    follow_pagination=follow_pagination,
                    article_max_pages=article_max_pages,
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


async def query_page(
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
    """Extract query-relevant content from a page.

    Args:
        url: URL to query.
        query: Relevance query.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Query-focused page payload.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=True,
        include_app_state=True,
        include_contacts=True,
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
    result = build_scrape_result(
        page,
        formats=["fit_markdown", "metadata"],
        only_main_content=True,
        query=query,
    )

    app_state = page.get("app_state", {})
    result["contacts"] = page.get("contacts", {})
    result["app_state_summary"] = app_state.get("summary", {})

    app_state_text = render_app_state_text(app_state)
    if not app_state_text:
        result["app_state_fit_chunks"] = []
        result["app_state_fit_text"] = ""
        return result

    app_state_fit_chunks = rank_text_chunks(
        app_state_text,
        query,
        strategy="sliding",
        chunk_size=120,
        overlap=30,
        top_k=5,
    )
    result["app_state_fit_chunks"] = app_state_fit_chunks
    result["app_state_fit_text"] = "\n\n---\n\n".join(item["text"] for item in app_state_fit_chunks)
    return result


def merge_research_chunks(source_results: list[dict], top_k: int = 10) -> list[dict]:
    """Merge per-source query chunks into a ranked research result set.

    Args:
        source_results: Query results enriched with source metadata.
        top_k: Maximum number of merged chunks to return.

    Returns:
        Ranked research chunk payloads.
    """
    merged = []
    seen = set()

    for source in source_results:
        source_rank = source.get("source_rank", 0)
        rank_bonus = max(0.0, 1.0 - (source_rank * 0.1))

        for kind, chunks in (
            ("content", source.get("fit_chunks", [])),
            ("app_state", source.get("app_state_fit_chunks", [])),
        ):
            for chunk in chunks:
                text = chunk.get("text", "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                merged.append(
                    {
                        "url": source.get("url"),
                        "title": source.get("title") or source.get("metadata", {}).get("title", ""),
                        "kind": kind,
                        "score": round(float(chunk.get("score", 0.0)) + rank_bonus, 6),
                        "text": text,
                        "source_rank": source_rank,
                    }
                )

    merged.sort(key=lambda item: (item["score"], -item["source_rank"]), reverse=True)
    return merged[: max(1, top_k)]


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
    """Run a multi-source research workflow over search results.

    Args:
        query: Research query.
        max_results: Maximum search results per page.
        pages: Number of search result pages.
        research_limit: Number of top results to analyze deeply.
        max_concurrency: Maximum concurrent deep page analyses.
        provider: Search provider.
        searxng_url: Optional SearXNG base URL.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Search results plus ranked cross-source research chunks.
    """
    search_payload = await websearch(
        query=query,
        max_results=max_results,
        pages=pages,
        provider=provider,
        searxng_url=searxng_url,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        scrape_results=False,
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
    target_results = [item for item in search_payload.get("results", []) if item.get("link")][: max(1, research_limit)]
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def research_one(index: int, item: dict) -> dict:
        async with semaphore:
            try:
                query_result = await query_page(
                    item["link"],
                    query,
                    mode="auto",
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
                query_result["url"] = item["link"]
                query_result["title"] = item.get("title", "")
                query_result["description"] = item.get("description", "")
                query_result["source_rank"] = index
                return query_result
            except Exception as error:
                return {
                    "url": item.get("link"),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "source_rank": index,
                    "error": str(error),
                    "fit_chunks": [],
                    "app_state_fit_chunks": [],
                }

    source_results = await asyncio.gather(*(research_one(index, item) for index, item in enumerate(target_results)))
    merged_chunks = merge_research_chunks([item for item in source_results if "error" not in item], top_k=10)

    return {
        "query": query,
        "provider": search_payload.get("provider"),
        "providers": search_payload.get("providers"),
        "search_count": search_payload.get("count", 0),
        "research_limit": research_limit,
        "source_count": len(source_results),
        "sources": source_results,
        "merged_chunks": merged_chunks,
        "merged_text": "\n\n---\n\n".join(item["text"] for item in merged_chunks),
        "search": search_payload,
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
    cache_revalidate: bool = False,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    state_path: str | None = None,
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
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        state_path: Optional persisted crawl state file.

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
        cache_revalidate=cache_revalidate,
        headers=headers,
        accept_invalid_certs=accept_invalid_certs,
        proxy_url=proxy_url,
        proxy_urls=proxy_urls,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        state_path=state_path,
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
    """Extract structured data from a page using a selector-based schema.

    Args:
        url: URL to extract from.
        schema: CSS-based extraction schema.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Structured extraction payload.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=True,
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

    return {
        "url": page["final_url"],
        "metadata": page.get("metadata", {}),
        "schema": schema,
        "data": extract_structured_data(page["html"], page["final_url"], schema),
    }


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
    """Extract forms from a page.

    Args:
        url: URL to inspect.
        mode: Fetch strategy.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        include_fill_suggestions: Whether to include form fill previews.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Form extraction payload.
    """
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=False,
        include_forms=True,
        include_form_fill_suggestions=include_fill_suggestions,
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
    return {
        "url": page["final_url"],
        "metadata": page.get("metadata", {}),
        "forms": page.get("forms", []),
        "count": len(page.get("forms", [])),
    }


async def article(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    follow_pagination: bool = False,
    max_pages: int = 3,
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
    """Extract readable article content from a page.

    Args:
        url: URL to inspect.
        mode: Fetch strategy.
        follow_pagination: Whether to follow likely next-page links for split articles.
        max_pages: Maximum article pages to merge.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Readable article payload with cleaned content.
    """
    max_pages = max(1, max_pages)
    page = await fetch_page(
        url=url,
        mode=mode,
        include_html=True,
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
    def build_article_payload(page_result: dict) -> dict:
        payload = extract_article_content(page_result.get("html", ""))
        payload["metadata"] = extract_article_metadata(
            page_result.get("html", ""),
            article_text=payload.get("text", ""),
        )
        return payload

    article_payload = build_article_payload(page)
    page_entries = [
        {
            "url": page["final_url"],
            "title": article_payload["metadata"].get("title") or page.get("title", ""),
            "score": article_payload.get("score", 0.0),
            "excerpt": article_payload.get("excerpt", ""),
            "text_length": len(article_payload.get("text", "")),
            "metadata": article_payload["metadata"],
        }
    ]
    seen_urls = {page["final_url"]}
    seen_signatures = set()
    merged_texts = [article_payload.get("text", "")]
    merged_html_segments = [article_payload.get("html", "")]
    pagination_stop_reason = None
    base_title = article_payload["metadata"].get("title") or page.get("title", "")
    base_canonical_url = article_payload["metadata"].get("canonical_url") or page["final_url"]
    first_signature = compute_simhash(article_payload.get("text", ""))
    if first_signature is not None:
        seen_signatures.add(first_signature)

    current_page = page
    while follow_pagination and len(page_entries) < max_pages:
        candidates = discover_next_page_candidates(
            current_page.get("html", ""),
            current_page["final_url"],
            canonical_url=base_canonical_url,
        )
        candidates = [candidate for candidate in candidates if candidate["url"] not in seen_urls]
        if not candidates:
            pagination_stop_reason = "no_candidate"
            break

        next_candidate = candidates[0]
        next_page = await fetch_page(
            url=next_candidate["url"],
            mode=mode,
            include_html=True,
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
        next_payload = build_article_payload(next_page)
        next_text = next_payload.get("text", "")
        if len(next_text) < 60:
            pagination_stop_reason = "short_or_empty_page"
            break
        if not titles_look_related(base_title, next_payload["metadata"].get("title", "")):
            pagination_stop_reason = "different_article_title"
            break

        next_signature = compute_simhash(next_text)
        if next_signature is not None and next_signature in seen_signatures:
            pagination_stop_reason = "duplicate_page"
            break
        if any(next_text in existing_text or existing_text in next_text for existing_text in merged_texts if existing_text):
            pagination_stop_reason = "duplicate_page"
            break

        seen_urls.add(next_page["final_url"])
        if next_signature is not None:
            seen_signatures.add(next_signature)
        merged_texts.append(next_text)
        merged_html_segments.append(next_payload.get("html", ""))
        page_entries.append(
            {
                "url": next_page["final_url"],
                "title": next_payload["metadata"].get("title") or next_page.get("title", ""),
                "score": next_payload.get("score", 0.0),
                "excerpt": next_payload.get("excerpt", ""),
                "text_length": len(next_text),
                "pagination_score": next_candidate["score"],
                "metadata": next_payload["metadata"],
            }
        )
        current_page = next_page

    if follow_pagination and pagination_stop_reason is None and len(page_entries) >= max_pages:
        pagination_stop_reason = "max_pages"

    if len(page_entries) > 1:
        article_payload["text"] = "\n\n".join(text for text in merged_texts if text)
        article_payload["html"] = "\n<hr data-page-break=\"true\" />\n".join(
            segment for segment in merged_html_segments if segment
        )
        article_payload["metadata"]["reading_time_minutes"] = max(
            1,
            round(len(article_payload["text"].split()) / 220),
        )

    for page_entry in page_entries[1:]:
        page_metadata = page_entry["metadata"]
        if not article_payload["metadata"].get("date_modified") and page_metadata.get("date_modified"):
            article_payload["metadata"]["date_modified"] = page_metadata["date_modified"]
        if not article_payload["metadata"].get("image") and page_metadata.get("image"):
            article_payload["metadata"]["image"] = page_metadata["image"]
        if not article_payload["metadata"].get("section") and page_metadata.get("section"):
            article_payload["metadata"]["section"] = page_metadata["section"]
        article_payload["metadata"]["authors"] = list(
            dict.fromkeys(article_payload["metadata"].get("authors", []) + page_metadata.get("authors", []))
        )
        article_payload["metadata"]["keywords"] = list(
            dict.fromkeys(article_payload["metadata"].get("keywords", []) + page_metadata.get("keywords", []))
        )

    article_payload["metadata"]["author"] = (
        article_payload["metadata"]["authors"][0] if article_payload["metadata"].get("authors") else ""
    )
    article_payload["page_count"] = len(page_entries)
    article_payload["pages"] = page_entries
    article_payload["pagination_followed"] = len(page_entries) > 1
    article_payload["pagination_stop_reason"] = pagination_stop_reason
    return {
        "url": page["final_url"],
        "metadata": page.get("metadata", {}),
        "article": article_payload,
    }


async def feeds(
    url: str,
    mode: Literal["auto", "http", "browser"] = "auto",
    spider_depth: int = 0,
    spider_limit: int = 10,
    max_candidates: int = 20,
    max_feeds: int = 10,
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
    """Discover and validate RSS, Atom, RDF, or JSON feeds for a site.

    Args:
        url: Starting URL or homepage.
        mode: Fetch strategy for discovery pages.
        spider_depth: Internal page spider depth for more feed hints.
        spider_limit: Maximum internal pages to spider.
        max_candidates: Maximum feed candidates to validate.
        max_feeds: Maximum validated feeds to return.
        cache: Whether to use disk caching.
        cache_dir: Optional cache directory.
        cache_ttl_seconds: Optional cache TTL.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.

    Returns:
        Feed discovery payload with validated feed metadata.
    """
    queued_pages = deque([(url, 0)])
    queued_urls = {url}
    scanned_pages = []
    errors = []
    raw_candidates = []
    validated_feeds = []
    seen_feed_urls = set()

    async def load_feed_page(target_url: str) -> dict:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            return await fetch_page(
                url=target_url,
                mode=mode,
                include_html=True,
                include_headers=True,
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

    while queued_pages and len(scanned_pages) < max(1, spider_limit if spider_depth > 0 else 1):
        current_url, depth = queued_pages.popleft()
        queued_urls.discard(current_url)

        try:
            page = await load_feed_page(current_url)
        except Exception as error:
            errors.append({"url": current_url, "depth": depth, "error": str(error)})
            continue

        final_url = page.get("final_url") or current_url
        if final_url in {item["url"] for item in scanned_pages}:
            continue

        analysis = analyze_feed_document(
            page.get("html", ""),
            final_url,
            content_type=page.get("content_type", ""),
        )
        page_entry = {
            "url": final_url,
            "depth": depth,
            "title": page.get("title", ""),
            "candidate_count": 0,
            "is_feed": analysis.get("is_feed", False),
        }

        if analysis.get("is_feed"):
            validated_feeds.append(
                {
                    **analysis,
                    "sources": ["self"],
                    "score": 200,
                    "discovered_from": [final_url],
                }
            )
            seen_feed_urls.add(final_url)
            scanned_pages.append(page_entry)
            continue

        page_candidates = discover_feed_candidates(page.get("html", ""), final_url)
        for candidate in page_candidates:
            candidate["discovered_from"] = final_url
        raw_candidates.extend(page_candidates)
        page_entry["candidate_count"] = len(page_candidates)
        scanned_pages.append(page_entry)

        if depth >= spider_depth:
            continue

        for spider_url in discover_feed_spider_links(
            page.get("html", ""),
            final_url,
            limit=max(1, spider_limit),
        ):
            if spider_url in queued_urls:
                continue
            queued_urls.add(spider_url)
            queued_pages.append((spider_url, depth + 1))

    merged_candidates = merge_feed_candidates(raw_candidates, max_candidates=max_candidates)

    for candidate in merged_candidates:
        candidate_url = candidate.get("url")
        if not candidate_url or candidate_url in seen_feed_urls:
            continue
        try:
            page = await load_feed_page(candidate_url)
        except Exception as error:
            errors.append({"url": candidate_url, "error": str(error)})
            continue

        analysis = analyze_feed_document(
            page.get("html", ""),
            page.get("final_url") or candidate_url,
            content_type=page.get("content_type", ""),
        )
        if not analysis.get("is_feed"):
            continue

        validated_feed_url = analysis["url"]
        if validated_feed_url in seen_feed_urls:
            continue

        seen_feed_urls.add(validated_feed_url)
        validated_feeds.append({**candidate, **analysis})
        if len(validated_feeds) >= max(1, max_feeds):
            break

    return {
        "start_url": url,
        "mode": mode,
        "spider_depth": spider_depth,
        "spider_limit": spider_limit,
        "max_candidates": max_candidates,
        "max_feeds": max_feeds,
        "scanned_pages": scanned_pages,
        "page_count": len(scanned_pages),
        "candidate_count": len(merged_candidates),
        "feeds": validated_feeds,
        "feed_count": len(validated_feeds),
        "errors": errors,
    }


async def crawl_one_page(
    session: AsyncSession,
    url: str,
    depth: int,
    mode: Literal["fast", "auto", "browser"],
    allow_subdomains: bool = False,
    allowed_domains: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_headers: bool = False,
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
    proxy_index: int = 0,
    full_resources: bool = False,
    include_requests: bool = False,
    interaction_mode: Literal["none", "auto"] = "none",
    max_interactions: int = 3,
    session_dir: str | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    retry_status_codes: list[int] | None = None,
    hooks: dict | None = None,
    include_technologies: bool = False,
    technology_aggression: int = 1,
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
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        proxy_index: Round-robin proxy selection index.
        full_resources: Whether to include resource URLs in discovery.
        include_requests: Whether to capture browser requests.
        interaction_mode: Interaction mode for simple page interactions.
        max_interactions: Maximum interactions to perform.
        session_dir: Optional persistent browser profile directory.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        retry_status_codes: Optional retryable status override.
        hooks: Optional lifecycle hook mapping.
        include_technologies: Whether to extract technology fingerprints.
        technology_aggression: Technology fingerprint aggression level.

    Returns:
        Tuple containing the result payload and discovered links.
    """
    try:
        return await _fetch_page(
            url=url,
            mode="http" if mode == "fast" else ("browser" if mode == "browser" else "auto"),
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
            cache_revalidate=cache_revalidate,
            user_agent=user_agent,
            headers=headers,
            accept_invalid_certs=accept_invalid_certs,
            pattern_mode=pattern_mode,
            proxy_url=proxy_url,
            proxy_urls=proxy_urls,
            proxy_index=proxy_index,
            full_resources=full_resources,
            include_requests=include_requests,
            interaction_mode=interaction_mode,
            max_interactions=max_interactions,
            session_dir=session_dir,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
            retry_status_codes=retry_status_codes,
            hooks=hooks,
            include_technologies=include_technologies,
            technology_aggression=technology_aggression,
        )
    except Exception as error:
        await run_named_hook(
            hooks,
            "on_error",
            {
                "url": url,
                "depth": depth,
                "error": str(error),
            },
        )
        return {"url": url, "depth": depth, "error": str(error)}, []


async def crawl(
    url: str,
    max_pages: int = 10,
    mode: Literal["fast", "auto", "browser"] = "auto",
    crawl_strategy: Literal["bfs", "best_first"] = "bfs",
    crawl_query: str | None = None,
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
    cache_revalidate: bool = False,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
    allowed_domains: list[str] | None = None,
    pattern_mode: Literal["auto", "substring", "regex", "glob"] = "auto",
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
    full_resources: bool = False,
    dedupe_by_signature: bool = False,
    dedupe_by_similarity: bool = False,
    similarity_threshold: int = 3,
    delay_ms: int = 0,
    path_delays: dict[str, int] | None = None,
    include_requests: bool = False,
    interaction_mode: Literal["none", "auto"] = "none",
    max_interactions: int = 3,
    session_dir: str | None = None,
    max_retries: int = 2,
    retry_backoff_ms: int = 500,
    retry_status_codes: list[int] | None = None,
    auto_throttle: bool = False,
    minimum_delay_ms: int = 0,
    maximum_delay_ms: int = 5000,
    state_path: str | None = None,
    autoscale_concurrency: bool = False,
    min_concurrency: int = 1,
    cpu_target_percent: float = 75.0,
    memory_target_percent: float = 80.0,
    hooks: dict | None = None,
    include_technologies: bool = False,
    technology_aggression: int = 1,
) -> dict:
    """Crawl a site using a browser-assisted or HTTP-only strategy.

    Args:
        url: Starting URL to crawl.
        max_pages: Maximum pages to crawl.
        mode: Crawl strategy, either ``fast``, ``auto``, or ``browser``.
        crawl_strategy: Frontier strategy.
        crawl_query: Optional relevance query for best-first crawling.
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
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.
        headers: Optional extra headers for HTTP and browser fetches.
        accept_invalid_certs: Whether to ignore certificate errors.
        allowed_domains: Additional explicitly allowed domains.
        pattern_mode: Pattern matching mode.
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL pool.
        full_resources: Whether to include resource URLs in crawl discovery.
        dedupe_by_signature: Whether to stop expanding duplicate-content pages.
        dedupe_by_similarity: Whether to stop expanding near-duplicate-content pages.
        similarity_threshold: Maximum simhash distance for near-duplicate detection.
        delay_ms: Default crawl delay in milliseconds.
        path_delays: Optional per-path delay mapping in milliseconds.
        include_requests: Whether to capture browser requests.
        interaction_mode: Interaction mode for simple page interactions.
        max_interactions: Maximum interactions to perform.
        session_dir: Optional persistent browser profile directory.
        max_retries: Maximum retry attempts after the initial request.
        retry_backoff_ms: Base retry backoff in milliseconds.
        retry_status_codes: Optional retryable status override.
        auto_throttle: Whether to adapt delay from observed timings.
        minimum_delay_ms: Lower bound for adaptive delay.
        maximum_delay_ms: Upper bound for adaptive delay.
        state_path: Optional persisted crawl state file for autosave and resume.
        autoscale_concurrency: Whether to adapt concurrency from system load.
        min_concurrency: Lower bound for autoscaled concurrency.
        cpu_target_percent: Preferred CPU ceiling for autoscaling.
        memory_target_percent: Preferred memory ceiling for autoscaling.
        hooks: Optional lifecycle hook mapping.
        include_technologies: Whether to extract technology fingerprints for each page.
        technology_aggression: Technology fingerprint aggression level for each page.

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
    to_visit = [] if crawl_strategy == "best_first" else deque()
    results = []
    seen_signatures = {}
    similarity_fingerprints = {}
    similarity_bucket_index = {}
    max_concurrency = max(1, max_concurrency)
    min_concurrency = max(1, min(min_concurrency, max_concurrency))
    robots_info = {
        "robots_url": None,
        "parser": None,
        "crawl_delay": None,
        "sitemaps": [],
        "status_code": None,
    }
    sitemap_seeds = []
    allowed_domain_set = normalize_allowed_domains(allowed_domains)
    resumed_from_state = False
    loaded_state = load_crawl_state(state_path)
    current_concurrency = max_concurrency if not autoscale_concurrency else min_concurrency
    autoscale_snapshots = []

    if loaded_state:
        resumed_from_state = True
        start_url = loaded_state.get("start_url", start_url)
        url = loaded_state.get("input_url", url)
        visited = set(loaded_state.get("visited", []))
        results = loaded_state.get("results", [])
        seen_signatures = loaded_state.get("seen_signatures", {})
        normalized_budget = loaded_state.get("budget_remaining", normalized_budget)
        sitemap_seeds = loaded_state.get("sitemap_seeds", [])
        current_concurrency = int(loaded_state.get("current_concurrency", current_concurrency))
        autoscale_snapshots = loaded_state.get("autoscale_snapshots", [])
        for item in loaded_state.get("frontier", []):
            current_url = item.get("url")
            current_depth = item.get("depth", 0)
            if not current_url:
                continue
            frontier_push(to_visit, current_url, current_depth, strategy=crawl_strategy, query=crawl_query)
        queued = {item.get("url") for item in loaded_state.get("frontier", []) if item.get("url")}

    for item in results:
        if item.get("is_near_duplicate"):
            continue
        similarity_signature = item.get("similarity_signature")
        similarity_value = parse_simhash(similarity_signature)
        representative_url = item.get("final_url") or item.get("url")
        if representative_url and similarity_value is not None:
            similarity_fingerprints[representative_url] = similarity_value
            add_simhash_to_index(
                representative_url,
                similarity_value,
                similarity_bucket_index,
                max_distance=similarity_threshold,
            )

    def persist_state(completed: bool = False) -> None:
        """Persist the current crawl state when a state path is configured."""
        save_crawl_state(
            state_path,
            {
                "version": 1,
                "completed": completed,
                "input_url": url,
                "start_url": start_url,
                "mode": mode,
                "crawl_strategy": crawl_strategy,
                "crawl_query": crawl_query,
                "max_pages": max_pages,
                "max_depth": max_depth,
                "allow_subdomains": allow_subdomains,
                "allowed_domains": allowed_domains or [],
                "respect_robots_txt": respect_robots_txt,
                "state_path": state_path,
                "frontier": serialize_frontier(to_visit, crawl_strategy),
                "visited": sorted(visited),
                "results": results,
                "seen_signatures": seen_signatures,
                "budget_remaining": normalized_budget,
                "sitemap_seeds": sitemap_seeds,
                "pages_crawled": len(results),
                "current_concurrency": current_concurrency,
                "autoscale_snapshots": autoscale_snapshots,
            },
        )

    request_headers = build_http_headers(user_agent=user_agent, headers=headers)
    await run_named_hook(
        hooks,
        "on_crawl_start",
        {
            "url": url,
            "start_url": start_url,
            "mode": mode,
            "crawl_strategy": crawl_strategy,
            "max_pages": max_pages,
        },
    )
    async with AsyncSession(impersonate="chrome", timeout=15, headers=request_headers) as session:
        if not resumed_from_state and consume_crawl_budget(start_url, normalized_budget):
            queued.add(start_url)
            frontier_push(to_visit, start_url, 0, strategy=crawl_strategy, query=crawl_query)

        if respect_robots_txt or seed_sitemap or sitemap_url:
            robots_info = await load_robots_rules(session, start_url, user_agent=user_agent)

        if not resumed_from_state and (seed_sitemap or sitemap_url):
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
                    await run_named_hook(
                        hooks,
                        "on_enqueue",
                        {
                            "url": normalized_seed,
                            "depth": 0,
                            "reason": "sitemap",
                        },
                    )
                    frontier_push(to_visit, normalized_seed, 0, strategy=crawl_strategy, query=crawl_query)

        persist_state(completed=False)

        while to_visit and len(visited) < max_pages:
            remaining_slots = max_pages - len(visited)
            batch_concurrency = current_concurrency if autoscale_concurrency else max_concurrency
            batch_size = min(batch_concurrency, remaining_slots)
            batch = []

            while to_visit and len(batch) < batch_size:
                current_url, current_depth = frontier_pop(to_visit, strategy=crawl_strategy)
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
                        cache_revalidate=cache_revalidate,
                        user_agent=user_agent,
                        headers=headers,
                        accept_invalid_certs=accept_invalid_certs,
                        pattern_mode=pattern_mode,
                        proxy_url=proxy_url,
                        proxy_urls=normalized_proxy_urls,
                        proxy_index=len(results) + batch_index,
                        full_resources=full_resources,
                        include_requests=include_requests,
                        interaction_mode=interaction_mode,
                        max_interactions=max_interactions,
                        session_dir=session_dir,
                        max_retries=max_retries,
                        retry_backoff_ms=retry_backoff_ms,
                        retry_status_codes=retry_status_codes,
                        hooks=hooks,
                        include_technologies=include_technologies,
                        technology_aggression=technology_aggression,
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

                similarity_signature = result.get("similarity_signature")
                similarity_value = parse_simhash(similarity_signature)
                representative_url = result.get("final_url") or result.get("url")
                if similarity_value is not None and representative_url and not result.get("is_duplicate"):
                    similarity_match = find_simhash_match(
                        similarity_value,
                        similarity_fingerprints,
                        similarity_bucket_index,
                        max_distance=similarity_threshold,
                    )
                    if similarity_match and similarity_match[0] != representative_url:
                        result["is_near_duplicate"] = True
                        result["near_duplicate_of"] = similarity_match[0]
                        result["similarity_distance"] = similarity_match[1]
                    else:
                        similarity_fingerprints[representative_url] = similarity_value
                        add_simhash_to_index(
                            representative_url,
                            similarity_value,
                            similarity_bucket_index,
                            max_distance=similarity_threshold,
                        )

                results.append(result)
                await run_named_hook(hooks, "on_result", result)
                if (dedupe_by_signature and result.get("is_duplicate")) or (
                    dedupe_by_similarity and result.get("is_near_duplicate")
                ):
                    continue
                next_depth = result.get("depth", 0) + 1
                if next_depth > max_depth:
                    continue
                for link in links:
                    normalized_link = strip_fragment(link)
                    if normalized_link not in visited and normalized_link not in queued:
                        if consume_crawl_budget(normalized_link, normalized_budget):
                            queued.add(normalized_link)
                            await run_named_hook(
                                hooks,
                                "on_enqueue",
                                {
                                    "url": normalized_link,
                                    "depth": next_depth,
                                    "reason": "page_link",
                                    "source_url": result.get("final_url", result.get("url")),
                                },
                            )
                            frontier_push(
                                to_visit,
                                normalized_link,
                                next_depth,
                                strategy=crawl_strategy,
                                query=crawl_query,
                            )

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
                if auto_throttle:
                    effective_delay_ms = max(
                        effective_delay_ms,
                        compute_auto_throttle_delay_ms(
                            [result for result, _ in page_results],
                            minimum_delay_ms=minimum_delay_ms,
                            maximum_delay_ms=maximum_delay_ms,
                        ),
                    )
                if effective_delay_ms > 0:
                    await asyncio.sleep(effective_delay_ms / 1000)

                if autoscale_concurrency:
                    load_snapshot = sample_system_load()
                    next_concurrency, decision = choose_autoscaled_concurrency(
                        current_concurrency=current_concurrency,
                        min_concurrency=min_concurrency,
                        max_concurrency=max_concurrency,
                        cpu_percent=load_snapshot["cpu_percent"],
                        memory_percent=load_snapshot["memory_percent"],
                        cpu_target_percent=cpu_target_percent,
                        memory_target_percent=memory_target_percent,
                    )
                    autoscale_snapshots.append(
                        {
                            "pages_crawled": len(results),
                            "batch_size": batch_size,
                            "cpu_percent": load_snapshot["cpu_percent"],
                            "memory_percent": load_snapshot["memory_percent"],
                            "decision": decision,
                            "next_concurrency": next_concurrency,
                        }
                    )
                    current_concurrency = next_concurrency

                persist_state(completed=False)

    persist_state(completed=True)

    crawl_result = {
        "start_url": url,
        "mode": mode,
        "crawl_strategy": crawl_strategy,
        "crawl_query": crawl_query,
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
        "cache_revalidate": cache_revalidate,
        "pattern_mode": pattern_mode,
        "proxy_urls": normalized_proxy_urls,
        "full_resources": full_resources,
        "dedupe_by_signature": dedupe_by_signature,
        "dedupe_by_similarity": dedupe_by_similarity,
        "similarity_threshold": similarity_threshold,
        "delay_ms": delay_ms,
        "path_delays": normalized_delay_map,
        "include_requests": include_requests,
        "interaction_mode": interaction_mode,
        "max_retries": max_retries,
        "retry_backoff_ms": retry_backoff_ms,
        "retry_status_codes": retry_status_codes or default_retry_status_codes(),
        "auto_throttle": auto_throttle,
        "state_path": state_path,
        "resumed_from_state": resumed_from_state,
        "autoscale_concurrency": autoscale_concurrency,
        "min_concurrency": min_concurrency,
        "current_concurrency": current_concurrency,
        "cpu_target_percent": cpu_target_percent,
        "memory_target_percent": memory_target_percent,
        "autoscale_snapshots": autoscale_snapshots,
        "include_technologies": include_technologies,
        "technology_aggression": technology_aggression,
        "pages_crawled": len(results),
        "duplicate_count": sum(1 for item in results if item.get("is_duplicate")),
        "near_duplicate_count": sum(1 for item in results if item.get("is_near_duplicate")),
        "results": results,
    }
    await run_named_hook(hooks, "on_crawl_end", crawl_result)
    return crawl_result


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

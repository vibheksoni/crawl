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
from .google import (
    extract_ai_overview,
    extract_organic_results,
    extract_people_also_ask,
    extract_video_results,
)
from .page import extract_cookies, parse_page_meta, render_page_content, strip_fragment


async def websearch(query: str, max_results: int = 10, pages: int = 1) -> dict:
    """Search Google and return parsed results using semantic heuristics.

    Args:
        query: Search query string.
        max_results: Maximum results per page.
        pages: Number of pages to scrape.

    Returns:
        Search results with links, titles, descriptions, and metadata.
    """
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
        "query": query,
        "pages_scraped": min(current_page, pages),
        "ai_overview": ai_overview,
        "results": all_results,
        "videos": all_videos,
        "people_also_ask": all_paa,
        "count": len(all_results),
    }


async def fetch(url: str, output_format: Literal["markdown", "text"] = "markdown") -> str:
    """Fetch a URL and convert the page into markdown or plain text.

    Args:
        url: URL to fetch.
        output_format: Either ``markdown`` or ``text``.

    Returns:
        Rendered page content.
    """
    async with browser_session(headless=False) as browser:
        page = await browser.get(url)
        await page.sleep(2)

        html = await page.get_content()
        return render_page_content(html, output_format)


async def request_page(session: AsyncSession, url: str) -> str:
    """Fetch a page over HTTP with an SSL-verification fallback.

    Args:
        session: Async HTTP session.
        url: URL to fetch.

    Returns:
        Response body text.
    """
    try:
        response = await session.get(url)
    except Exception as error:
        if "SSL certificate problem" not in str(error):
            raise
        response = await session.get(url, verify=False)
    return response.text


async def crawl_one_page(session: AsyncSession, url: str, base_domain: str) -> tuple[dict, list[str]]:
    """Fetch and parse a single crawled page.

    Args:
        session: Async HTTP session.
        url: Page URL to fetch.
        base_domain: Domain used to filter same-site links.

    Returns:
        Tuple containing the result payload and discovered links.
    """
    try:
        html = await request_page(session, url)
        meta = parse_page_meta(html, url, base_domain)
        return (
            {
                "url": url,
                "title": meta["title"],
                "description": meta["description"],
                "links_found": len(meta["links"]),
            },
            meta["links"],
        )
    except Exception as error:
        return {"url": url, "error": str(error)}, []


async def crawl(
    url: str,
    max_pages: int = 10,
    mode: Literal["fast", "auto"] = "auto",
    max_concurrency: int = 4,
) -> dict:
    """Crawl a site using a browser-assisted or HTTP-only strategy.

    Args:
        url: Starting URL to crawl.
        max_pages: Maximum pages to crawl.
        mode: Crawl strategy, either ``fast`` or ``auto``.
        max_concurrency: Maximum parallel HTTP requests.

    Returns:
        Crawled URL metadata and crawl statistics.
    """
    start_url = strip_fragment(url)
    base_domain = urlparse(url).netloc
    visited = set()
    queued = {start_url}
    to_visit = deque([start_url])
    results = []
    cookies = {}
    max_concurrency = max(1, max_concurrency)

    if mode == "auto":
        async with browser_session(headless=False) as browser:
            page = await browser.get(start_url)
            await page.sleep(2)

            html = await page.get_content()
            cookies = await extract_cookies(browser)

        meta = parse_page_meta(html, start_url, base_domain)
        visited.add(start_url)
        results.append(
            {
                "url": start_url,
                "title": meta["title"],
                "description": meta["description"],
                "links_found": len(meta["links"]),
            }
        )
        to_visit.clear()
        queued.clear()
        for link in meta["links"]:
            if link not in visited and link not in queued:
                queued.add(link)
                to_visit.append(link)

    async with AsyncSession(cookies=cookies, impersonate="chrome", timeout=15) as session:
        while to_visit and len(visited) < max_pages:
            remaining_slots = max_pages - len(visited)
            batch_size = min(max_concurrency, remaining_slots)
            batch = []

            while to_visit and len(batch) < batch_size:
                current_url = to_visit.popleft()
                queued.discard(current_url)
                if current_url in visited:
                    continue
                visited.add(current_url)
                batch.append(current_url)

            if not batch:
                continue

            page_results = await asyncio.gather(
                *(crawl_one_page(session, current_url, base_domain) for current_url in batch)
            )

            for result, links in page_results:
                results.append(result)
                for link in links:
                    if link not in visited and link not in queued:
                        queued.add(link)
                        to_visit.append(link)

    return {
        "start_url": url,
        "mode": mode,
        "max_concurrency": max_concurrency,
        "pages_crawled": len(results),
        "cookies_extracted": len(cookies),
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

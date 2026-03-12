"""SearXNG search provider helpers."""

import json
import os
from urllib.parse import urlencode

from curl_cffi.requests import AsyncSession

DEFAULT_SEARXNG_URL = "http://127.0.0.1:8888"


def resolve_searxng_url(searxng_url: str | None = None) -> str:
    """Resolve the SearXNG base URL from an argument, env var, or local default.

    Args:
        searxng_url: Optional explicit SearXNG base URL.

    Returns:
        Normalized base URL without a trailing slash.
    """
    candidate = searxng_url or os.getenv("SEARXNG_URL") or DEFAULT_SEARXNG_URL
    return candidate.rstrip("/")


async def request_searxng_json(session: AsyncSession, url: str) -> dict:
    """Fetch a JSON response from SearXNG with an SSL fallback.

    Args:
        session: Async HTTP session.
        url: Fully-qualified request URL.

    Returns:
        Decoded JSON response.
    """
    try:
        response = await session.get(url)
    except Exception as error:
        if "SSL certificate problem" not in str(error):
            raise
        response = await session.get(url, verify=False)
    return json.loads(response.text)


def normalize_searxng_result(item: dict, page: int) -> dict:
    """Map a SearXNG result into the project's common search result shape.

    Args:
        item: Raw SearXNG result item.
        page: Page number the result came from.

    Returns:
        Normalized result payload.
    """
    parsed_url = item.get("parsed_url") or []
    displayed_url = ""
    if len(parsed_url) >= 2:
        displayed_url = f"{parsed_url[0]}://{parsed_url[1]}"

    result = {
        "type": item.get("category", "organic"),
        "title": item.get("title", ""),
        "link": item.get("url", ""),
        "displayed_url": displayed_url,
        "description": item.get("content", ""),
        "page": page,
    }

    if item.get("publishedDate"):
        result["published_date"] = item["publishedDate"]
    if item.get("score") is not None:
        result["score"] = item["score"]
    if item.get("engines"):
        result["engines"] = item["engines"]
    if item.get("engine"):
        result["engine"] = item["engine"]

    return result


async def request_searxng_json_with_proxy(
    session: AsyncSession,
    url: str,
    proxy_url: str | None = None,
) -> dict:
    """Fetch a JSON response from SearXNG with optional proxy support.

    Args:
        session: Async HTTP session.
        url: Fully-qualified request URL.
        proxy_url: Optional proxy URL.

    Returns:
        Decoded JSON response.
    """
    try:
        response = await session.get(url, proxy=proxy_url)
    except Exception as error:
        if "SSL certificate problem" not in str(error):
            raise
        response = await session.get(url, verify=False, proxy=proxy_url)
    return json.loads(response.text)


async def search_searxng(
    query: str,
    max_results: int = 10,
    pages: int = 1,
    searxng_url: str | None = None,
    proxy_url: str | None = None,
) -> dict:
    """Search SearXNG and return results mapped into the project's search schema.

    Args:
        query: Search query string.
        max_results: Maximum results per page.
        pages: Number of pages to fetch.
        searxng_url: Optional SearXNG base URL.
        proxy_url: Optional proxy URL.

    Returns:
        Search results with normalized metadata.
    """
    base_url = resolve_searxng_url(searxng_url)
    search_endpoint = f"{base_url}/search"
    pages_scraped = 0
    results = []
    videos = []
    seen_general_urls = set()
    seen_video_urls = set()
    suggestions = []
    corrections = []
    answers = []
    infoboxes = []
    unresponsive_engines = []

    async with AsyncSession(timeout=20, impersonate="chrome") as session:
        for page in range(1, pages + 1):
            params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "pageno": page,
            }
            payload = await request_searxng_json_with_proxy(
                session,
                f"{search_endpoint}?{urlencode(params)}",
                proxy_url=proxy_url,
            )
            pages_scraped = page

            for item in payload.get("results", []):
                normalized = normalize_searxng_result(item, page)
                if not normalized["link"] or normalized["link"] in seen_general_urls:
                    continue
                seen_general_urls.add(normalized["link"])
                results.append(normalized)
                if len(results) >= max_results * pages:
                    break

            if page == 1:
                suggestions = payload.get("suggestions", [])
                corrections = payload.get("corrections", [])
                answers = payload.get("answers", [])
                infoboxes = payload.get("infoboxes", [])
                unresponsive_engines = payload.get("unresponsive_engines", [])

                video_params = {
                    "q": query,
                    "format": "json",
                    "categories": "videos",
                    "pageno": 1,
                }
                video_payload = await request_searxng_json_with_proxy(
                    session,
                    f"{search_endpoint}?{urlencode(video_params)}",
                    proxy_url=proxy_url,
                )
                for item in video_payload.get("results", []):
                    normalized = normalize_searxng_result(item, 1)
                    if not normalized["link"] or normalized["link"] in seen_video_urls:
                        continue
                    seen_video_urls.add(normalized["link"])
                    videos.append(normalized)
                    if len(videos) >= max_results:
                        break

    return {
        "provider": "searxng",
        "provider_url": base_url,
        "query": query,
        "pages_scraped": pages_scraped,
        "ai_overview": "",
        "results": results[: max_results * pages],
        "videos": videos,
        "people_also_ask": [],
        "answers": answers,
        "infoboxes": infoboxes,
        "suggestions": suggestions,
        "corrections": corrections,
        "unresponsive_engines": unresponsive_engines,
        "count": min(len(results), max_results * pages),
    }

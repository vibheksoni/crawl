"""Site discovery MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from crawl.sdk import crawl as sdk_crawl
from crawl.sdk import feeds as sdk_feeds
from crawl.sdk import map_site as sdk_map_site
from crawl.sdk import tech as sdk_tech

from ..config import DEFAULT_BROWSER_HEADLESS, read_only_annotations
from ..helpers import build_cache_kwargs, build_page_kwargs
from ..models import SiteStrategy


def register_site_tools(mcp: FastMCP) -> None:
    """Register site-level discovery tools on the MCP server.

    Args:
        mcp: Target MCP server.
    """

    @mcp.tool(
        name="discover_site",
        description=(
            "Map a site, run a bounded crawl, discover feeds, or fingerprint technologies across a site slice. "
            "Use this when the answer spans multiple pages or you need site-level discovery instead of one-page inspection. "
            "Prefer strategy='map' for URL discovery, strategy='crawl' for bounded traversal, strategy='feeds' for feed discovery, "
            "and strategy='technologies' for site-level technology aggregation."
        ),
        tags={"site"},
        annotations=read_only_annotations("Discover a site with a bounded strategy"),
        timeout=300,
    )
    async def discover_site(
        url: str,
        strategy: SiteStrategy = "map",
        query: str | None = None,
        max_pages: int = 15,
        max_depth: int = 1,
        browser: bool = False,
        respect_robots_txt: bool = True,
        headless: bool = DEFAULT_BROWSER_HEADLESS,
    ) -> dict:
        """Discover a site with one bounded strategy.

        Args:
            url: Start URL.
            strategy: Discovery strategy to run.
            query: Optional relevance query.
            max_pages: Page or result limit.
            max_depth: Maximum traversal depth where applicable.
            browser: Whether the strategy should prefer browser-backed execution.
            respect_robots_txt: Whether site traversal should respect robots.txt.
            headless: Whether browser launches should be headless.

        Returns:
            Site discovery payload.
        """
        if strategy == "map":
            payload = await sdk_map_site(
                url=url,
                search=query,
                limit=max_pages,
                mode="auto" if browser else "fast",
                respect_robots_txt=respect_robots_txt,
                headless=headless,
                **build_cache_kwargs(),
            )
        elif strategy == "crawl":
            payload = await sdk_crawl(
                url=url,
                max_pages=max_pages,
                max_depth=max_depth,
                mode="browser" if browser else "fast",
                crawl_strategy="best_first" if query else "bfs",
                crawl_query=query,
                respect_robots_txt=respect_robots_txt,
                auto_throttle=True,
                headless=headless,
                **build_cache_kwargs(),
            )
        elif strategy == "feeds":
            payload = await sdk_feeds(
                url=url,
                mode="browser" if browser else "auto",
                spider_depth=max_depth,
                spider_limit=max_pages,
                max_feeds=max_pages,
                headless=headless,
                **build_cache_kwargs(),
            )
        else:
            payload = await sdk_tech(
                url=url,
                max_pages=max_pages,
                max_depth=max_depth,
                **build_page_kwargs("browser" if browser else "http", headless=headless),
            )

        result = dict(payload)
        result["strategy"] = strategy
        result["browser"] = browser
        if query:
            result["requested_query"] = query
        return result

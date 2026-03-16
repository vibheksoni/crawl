"""Search-oriented MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from crawl.sdk import research as sdk_research
from crawl.sdk import websearch as sdk_websearch

from ..config import read_only_annotations
from ..helpers import build_cache_kwargs
from ..models import SearchDepth, SearchProvider


def register_search_tools(mcp: FastMCP) -> None:
    """Register search-oriented tools on the MCP server.

    Args:
        mcp: Target MCP server.
    """

    @mcp.tool(
        name="search_web",
        description=(
            "Search the web for candidate URLs or run a deeper multi-source research pass over top results. "
            "Use this first for open-web tasks when you do not already know the target page. "
            "Use depth='quick' for a compact search result set and candidate URLs. "
            "Use depth='research' when you want the server to read top sources and return merged research chunks."
        ),
        tags={"search"},
        annotations=read_only_annotations("Search the web or run focused research"),
        timeout=180,
    )
    async def search_web(
        query: str,
        depth: SearchDepth = "quick",
        max_results: int = 8,
        pages: int = 1,
        provider: SearchProvider = "auto",
        searxng_url: str | None = None,
        include_page_context: bool = False,
        research_limit: int = 5,
        max_concurrency: int = 4,
    ) -> dict:
        """Search the web for URLs or run a deeper research pass.

        Args:
            query: Search or research query.
            depth: ``quick`` for a SERP-like result set, ``research`` for multi-source synthesis.
            max_results: Maximum results per page.
            pages: Number of result pages to fetch.
            provider: Search provider selection.
            searxng_url: Optional SearXNG base URL.
            include_page_context: Whether quick search should enrich top results with page context.
            research_limit: Maximum results to read in research mode.
            max_concurrency: Maximum concurrent fetches in research mode.

            Returns:
                Search or research payload.
        """
        if depth == "research":
            payload = await sdk_research(
                query=query,
                max_results=max_results,
                pages=pages,
                research_limit=research_limit,
                max_concurrency=max_concurrency,
                provider=provider,
                searxng_url=searxng_url,
                **build_cache_kwargs(),
            )
            return {
                "query": query,
                "depth": depth,
                "provider": payload["search"]["provider"],
                "search_count": payload["search_count"],
                "source_count": payload["source_count"],
                "sources": payload["sources"],
                "merged_chunks": payload["merged_chunks"],
                "merged_text": payload["merged_text"],
                "search": payload["search"],
            }

        scrape_limit = min(max_results * pages, max(1, research_limit))
        payload = await sdk_websearch(
            query=query,
            max_results=max_results,
            pages=pages,
            provider=provider,
            searxng_url=searxng_url,
            scrape_results=include_page_context,
            scrape_limit=scrape_limit,
            scrape_formats=["metadata", "markdown"] if include_page_context else None,
            only_main_content=True,
            **build_cache_kwargs(),
        )
        return {
            "query": query,
            "depth": depth,
            "provider": payload.get("provider"),
            "count": payload.get("count", 0),
            "results": payload.get("results", []),
            "videos": payload.get("videos", []),
            "people_also_ask": payload.get("people_also_ask", []),
            "ai_overview": payload.get("ai_overview", ""),
        }

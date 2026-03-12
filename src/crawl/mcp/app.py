"""FastMCP application wrapper around the crawl SDK."""

from typing import Literal

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from crawl.sdk import crawl as sdk_crawl
from crawl.sdk import fetch as sdk_fetch
from crawl.sdk import screenshot as sdk_screenshot
from crawl.sdk import websearch as sdk_websearch

mcp = FastMCP("crawl-mcp")


@mcp.tool()
async def websearch(query: str, max_results: int = 10, pages: int = 1) -> dict:
    """Run the SDK web search through the MCP transport.

    Args:
        query: Search query string.
        max_results: Maximum results per page.
        pages: Number of pages to scrape.

    Returns:
        Search results with links, titles, descriptions, and metadata.
    """
    return await sdk_websearch(query=query, max_results=max_results, pages=pages)


@mcp.tool()
async def fetch(url: str, output_format: Literal["markdown", "text"] = "markdown") -> str:
    """Run the SDK fetch operation through the MCP transport.

    Args:
        url: URL to fetch.
        output_format: Either ``markdown`` or ``text``.

    Returns:
        Rendered page content.
    """
    return await sdk_fetch(url=url, output_format=output_format)


@mcp.tool()
async def crawl(url: str, max_pages: int = 10, mode: Literal["fast", "auto"] = "auto") -> dict:
    """Run the SDK site crawler through the MCP transport.

    Args:
        url: Starting URL to crawl.
        max_pages: Maximum pages to crawl.
        mode: Crawl strategy, either ``fast`` or ``auto``.

    Returns:
        Crawled URL metadata and crawl statistics.
    """
    return await sdk_crawl(url=url, max_pages=max_pages, mode=mode)


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

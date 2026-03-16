"""FastMCP application bootstrap for the crawl MCP server."""

from __future__ import annotations

from fastmcp import FastMCP

from .config import SERVER_INSTRUCTIONS, SERVER_NAME
from .prompts import register_prompts
from .resources import register_resources
from .tools import (
    register_capture_tools,
    register_extract_tools,
    register_page_tools,
    register_search_tools,
    register_site_tools,
)


def build_server() -> FastMCP:
    """Build the crawl MCP server.

    Returns:
        Configured FastMCP server.
    """
    server = FastMCP(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        strict_input_validation=True,
        list_page_size=50,
    )
    register_resources(server)
    register_prompts(server)
    register_search_tools(server)
    register_page_tools(server)
    register_site_tools(server)
    register_extract_tools(server)
    register_capture_tools(server)
    return server


mcp = build_server()


def run() -> None:
    """Run the FastMCP server."""
    mcp.run()

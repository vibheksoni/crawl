"""Tool registration helpers for the crawl MCP server."""

from .capture import register_capture_tools
from .extract import register_extract_tools
from .page import register_page_tools
from .search import register_search_tools
from .site import register_site_tools

__all__ = [
    "register_capture_tools",
    "register_extract_tools",
    "register_page_tools",
    "register_search_tools",
    "register_site_tools",
]

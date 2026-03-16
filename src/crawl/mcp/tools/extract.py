"""Structured extraction MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from crawl.sdk import extract as sdk_extract

from ..config import read_only_annotations
from ..helpers import build_page_kwargs
from ..models import PageMode


def register_extract_tools(mcp: FastMCP) -> None:
    """Register structured extraction tools on the MCP server.

    Args:
        mcp: Target MCP server.
    """

    @mcp.tool(
        name="extract_structured",
        description=(
            "Extract structured data from a page with a focused CSS-based schema. "
            "Use this when you already know the selectors and fields you want. "
            "If you still need to understand the page shape, use inspect_url first."
        ),
        tags={"extract"},
        annotations=read_only_annotations("Extract structured data with a schema"),
        timeout=180,
    )
    async def extract_structured(
        url: str,
        schema: dict,
        mode: PageMode = "auto",
    ) -> dict:
        """Extract structured data from one page.

        Args:
            url: Page URL to extract from.
            schema: CSS-based extraction schema.
            mode: Fetch mode.

        Returns:
            Structured extraction payload.
        """
        return await sdk_extract(
            url=url,
            schema=schema,
            **build_page_kwargs(mode),
        )

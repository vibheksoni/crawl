"""Screenshot capture MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from crawl.sdk import screenshot as sdk_screenshot

from ..config import DEFAULT_BROWSER_CONSENT_MODE, DEFAULT_BROWSER_HEADLESS, read_only_annotations


def register_capture_tools(mcp: FastMCP) -> None:
    """Register capture tools on the MCP server.

    Args:
        mcp: Target MCP server.
    """

    @mcp.tool(
        name="capture_screenshot",
        description=(
            "Capture a screenshot of one page for visual verification. "
            "Use this sparingly when layout, consent handling, or rendered state needs a visual check."
        ),
        tags={"capture"},
        annotations=read_only_annotations("Capture a page screenshot"),
        timeout=180,
    )
    async def capture_screenshot(
        url: str,
        full_page: bool = True,
        width: int = -1,
        height: int = -1,
        headless: bool = DEFAULT_BROWSER_HEADLESS,
    ) -> Image:
        """Capture a screenshot of one page.

        Args:
            url: Page URL to capture.
            full_page: Whether to capture the full page.
            width: Optional viewport width.
            height: Optional viewport height.
            headless: Whether the browser should launch headlessly.

        Returns:
            Screenshot image payload.
        """
        image_bytes = await sdk_screenshot(
            url=url,
            width=width,
            height=height,
            full_page=full_page,
            consent_mode=DEFAULT_BROWSER_CONSENT_MODE,
            headless=headless,
        )
        return Image(data=image_bytes)

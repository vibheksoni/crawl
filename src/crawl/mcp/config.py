"""Shared configuration for the crawl MCP server."""

from __future__ import annotations

from textwrap import dedent

from mcp.types import ToolAnnotations

SERVER_NAME = "crawl-mcp"
SERVER_INSTRUCTIONS = dedent(
    """
    crawl-mcp is an agent-optimized web research server built on top of the crawl SDK.
    Prefer the smallest tool that can solve the task:
    - use search_web to find candidate pages or run deeper multi-source research
    - use inspect_url to read and analyze one page
    - use discover_site to map, crawl, discover feeds, or fingerprint a site slice
    - use extract_structured when you already know the extraction schema you want
    - use capture_screenshot only when a visual snapshot is necessary

    Read crawl://guide/overview and crawl://guide/workflows when you need tool-selection help.
    Avoid broad crawls when search_web or inspect_url is sufficient.
    """
).strip()

DEFAULT_CACHE_ENABLED = True
DEFAULT_CACHE_TTL_SECONDS = 900
DEFAULT_CACHE_REVALIDATE = True
DEFAULT_BROWSER_CONSENT_MODE = "auto"
DEFAULT_BROWSER_RESOURCE_MODE = "safe"
DEFAULT_BROWSER_HEADLESS = False
DEFAULT_ONLY_MAIN_CONTENT = True

OVERVIEW_GUIDE = dedent(
    """
    crawl-mcp exposes a compact workflow-oriented interface over the crawl SDK.

    Tool summary:
    - search_web: find URLs or run a deeper research pass over top results
    - inspect_url: inspect one page and return only the requested sections
    - discover_site: map a site, run a bounded crawl, discover feeds, or aggregate technologies
    - extract_structured: run schema-driven extraction when you know the fields you want
    - capture_screenshot: capture a visual snapshot of one page

    The MCP layer intentionally hides most low-level SDK knobs so agents see a smaller, more reliable tool surface.
    """
).strip()

WORKFLOW_GUIDE = dedent(
    """
    Recommended workflows:

    1. Unknown web task:
       - call search_web with depth=quick
       - inspect one or more promising URLs with inspect_url
       - only use discover_site if you need broader site coverage

    2. Deep answer synthesis:
       - call search_web with depth=research
       - inspect a source URL only when you need more detail than the research payload returned

    3. Site exploration:
       - start with discover_site strategy=map
       - switch to strategy=crawl only when you need many pages or structured crawl statistics
       - use strategy=feeds or strategy=technologies for those specialized site-level tasks

    4. Structured extraction:
       - use inspect_url first if you need to understand the page shape
       - then call extract_structured with a focused schema

    5. Visual verification:
       - call capture_screenshot after inspect_url when layout or consent handling needs confirmation
    """
).strip()

EXTRACT_SCHEMA_GUIDE = dedent(
    """
    extract_structured expects a schema dictionary with a CSS-based extraction plan.

    Common fields:
    - baseSelector: CSS selector that defines the record container
    - multiple: true to return multiple records, false for one record
    - fields: list of field definitions

    Common field shapes:
    - {"name": "title", "selector": "h2", "type": "text"}
    - {"name": "url", "selector": "a", "type": "attribute", "attribute": "href", "absolute": true}

    Keep schemas focused. Start with a small set of fields, validate the output, then add more selectors.
    """
).strip()

TOOL_GUIDES = {
    "search_web": dedent(
        """
        search_web is the entrypoint for open-web discovery.

        Use depth=quick when you want search results and candidate URLs.
        Use depth=research when you want the server to read and merge the top results into a tighter research payload.
        """
    ).strip(),
    "inspect_url": dedent(
        """
        inspect_url is the default single-page reading tool.

        Request only the sections you need through the view list.
        Add the query argument when you want relevance-ranked excerpts for a specific question.
        """
    ).strip(),
    "discover_site": dedent(
        """
        discover_site is for multi-page or site-level work.

        Use strategy=map for URL discovery, strategy=crawl for bounded page traversal,
        strategy=feeds for feed discovery, and strategy=technologies for site-level fingerprinting.
        """
    ).strip(),
    "extract_structured": dedent(
        """
        extract_structured is for schema-driven extraction.

        Use it when you already know the selectors and field structure you want.
        If you do not know the page shape yet, start with inspect_url.
        """
    ).strip(),
    "capture_screenshot": dedent(
        """
        capture_screenshot returns a screenshot image for one page.

        Use it sparingly for visual confirmation, consent verification, or layout debugging.
        """
    ).strip(),
}


def read_only_annotations(title: str, *, idempotent: bool = True) -> ToolAnnotations:
    """Build read-only tool annotations for agent-facing MCP tools.

    Args:
        title: Human-readable tool title.
        idempotent: Whether the tool should be marked idempotent.

    Returns:
        Tool annotation payload.
    """
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=idempotent,
        openWorldHint=True,
    )

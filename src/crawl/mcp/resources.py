"""Guide resources for the crawl MCP server."""

from __future__ import annotations

import json

from fastmcp import FastMCP

from crawl.sdk import get_technology_definition, search_technology_definitions

from .config import EXTRACT_SCHEMA_GUIDE, OVERVIEW_GUIDE, TOOL_GUIDES, WORKFLOW_GUIDE


def register_resources(mcp: FastMCP) -> None:
    """Register guide resources on the MCP server.

    Args:
        mcp: Target MCP server.
    """

    @mcp.resource(
        "crawl://guide/overview",
        title="crawl MCP overview",
        description="Overview of the compact crawl MCP tool surface and when each MCP tool should be used.",
        tags={"guide"},
    )
    def guide_overview() -> str:
        """Return the MCP overview guide."""
        return OVERVIEW_GUIDE

    @mcp.resource(
        "crawl://guide/workflows",
        title="crawl MCP workflows",
        description="Recommended tool-selection workflows for research, inspection, extraction, and site discovery tasks.",
        tags={"guide"},
    )
    def guide_workflows() -> str:
        """Return the workflow guide."""
        return WORKFLOW_GUIDE

    @mcp.resource(
        "crawl://guide/extract-schema",
        title="extract schema guide",
        description="How to write focused CSS extraction schemas for extract_structured.",
        tags={"guide"},
    )
    def guide_extract_schema() -> str:
        """Return schema-writing guidance for structured extraction."""
        return EXTRACT_SCHEMA_GUIDE

    @mcp.resource(
        "crawl://guide/tool/{tool_name}",
        title="per-tool guide",
        description="Detailed guidance for one crawl MCP tool.",
        tags={"guide"},
    )
    def guide_tool(tool_name: str) -> str:
        """Return tool-specific guidance.

        Args:
            tool_name: Tool name to describe.

        Returns:
            Tool-specific guide text.
        """
        key = str(tool_name).strip()
        if key not in TOOL_GUIDES:
            available = ", ".join(sorted(TOOL_GUIDES))
            raise ValueError(f"Unknown tool '{tool_name}'. Available tools: {available}")
        return TOOL_GUIDES[key]

    @mcp.resource(
        "crawl://catalog/technology-search/{query}",
        title="technology catalog search",
        description="Search bundled technology definitions without exposing extra lookup tools.",
        mime_type="application/json",
        tags={"guide", "catalog"},
    )
    def technology_search(query: str) -> str:
        """Return technology definition matches.

        Args:
            query: Technology search query.

        Returns:
            JSON search payload.
        """
        results = search_technology_definitions(query, limit=25)
        return json.dumps(
            {
                "query": query,
                "count": len(results),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.resource(
        "crawl://catalog/technology/{name}",
        title="technology catalog entry",
        description="Read one bundled technology definition by exact name.",
        mime_type="application/json",
        tags={"guide", "catalog"},
    )
    def technology_definition(name: str) -> str:
        """Return one technology definition.

        Args:
            name: Exact technology name.

        Returns:
            JSON definition payload.
        """
        definition = get_technology_definition(name)
        if definition is None:
            raise ValueError(f"Unknown technology '{name}'")
        return json.dumps(definition, indent=2, ensure_ascii=False)

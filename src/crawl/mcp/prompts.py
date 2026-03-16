"""Workflow prompts for the crawl MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.prompts import PromptResult


def register_prompts(mcp: FastMCP) -> None:
    """Register workflow prompts on the MCP server.

    Args:
        mcp: Target MCP server.
    """

    @mcp.prompt(
        name="research_workflow",
        title="research workflow",
        description="Prompt guidance for answering an open-web research question with the compact crawl MCP tools.",
        tags={"workflow", "research"},
    )
    def research_workflow(topic: str) -> PromptResult:
        """Return a research workflow prompt.

        Args:
            topic: Research question or task.

        Returns:
            Prompt payload.
        """
        return PromptResult(
            f"""Research the topic: {topic}

Suggested tool sequence:
- start with `search_web` using depth=`research` for a compact multi-source brief
- if you need more detail from one source, call `inspect_url`
- if you already know the site and need broader coverage, use `discover_site`
- use `capture_screenshot` only when visual confirmation matters

Keep each request focused and prefer the smallest tool that can answer the question.
"""
        )

    @mcp.prompt(
        name="extraction_workflow",
        title="extraction workflow",
        description="Prompt guidance for structured extraction and focused page analysis with the compact crawl MCP tools.",
        tags={"workflow", "extract"},
    )
    def extraction_workflow(goal: str) -> PromptResult:
        """Return a structured extraction workflow prompt.

        Args:
            goal: Extraction goal.

        Returns:
            Prompt payload.
        """
        return PromptResult(
            f"""Extract data for: {goal}

Suggested tool sequence:
- inspect the page first with `inspect_url` if you need to understand page structure
- use `extract_structured` once you know the schema you want
- if the task is article, forms, contacts, technologies, or site feeds, prefer `inspect_url` or `discover_site` instead of a generic crawl

Keep schemas and requested sections narrow so the response stays high-signal.
"""
        )

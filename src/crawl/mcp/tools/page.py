"""Single-page inspection MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from crawl.sdk import fetch_page as sdk_fetch_page
from crawl.sdk import forms as sdk_forms
from crawl.sdk import query_page as sdk_query_page
from crawl.sdk import scrape as sdk_scrape

from ..config import DEFAULT_BROWSER_HEADLESS, DEFAULT_ONLY_MAIN_CONTENT, read_only_annotations
from ..helpers import (
    build_page_kwargs,
    extract_browser_details,
    needs_fetch_page,
    normalize_page_mode,
    normalize_inspect_views,
    scrape_formats_for_views,
)


def _set_if_missing(target: dict, key: str, value) -> None:
    """Set a result field only when the value is meaningful and absent.

    Args:
        target: Result dictionary.
        key: Result key.
        value: Candidate value.
    """
    if value in (None, "", [], {}):
        return
    if key not in target:
        target[key] = value


def register_page_tools(mcp: FastMCP) -> None:
    """Register single-page inspection tools on the MCP server.

    Args:
        mcp: Target MCP server.
    """

    @mcp.tool(
        name="inspect_url",
        description=(
            "Inspect one page and return only the requested sections such as content, metadata, links, forms, contacts, technologies, "
            "browser diagnostics, or query-ranked excerpts. Use this as the default one-page tool before escalating to broader site discovery. "
            "Keep the requested view list narrow so the response stays high-signal. "
            "Supported modes: auto, http, browser. Supported views: content, metadata, links, html, headers, app_state, article, contacts, forms, technologies, api_payloads, requests. "
            "You may pass one view as a string or multiple views as a list."
        ),
        tags={"page"},
        annotations=read_only_annotations("Inspect one page with focused outputs"),
        timeout=240,
    )
    async def inspect_url(
        url: str,
        view: str | list[str] | None = None,
        mode: str = "auto",
        query: str | None = None,
        only_main_content: bool = DEFAULT_ONLY_MAIN_CONTENT,
        follow_pagination: bool = False,
        headless: bool = DEFAULT_BROWSER_HEADLESS,
    ) -> dict:
        """Inspect one page with a focused response shape.

        Args:
            url: Page URL to inspect.
            view: Requested output sections.
            mode: Fetch mode.
            query: Optional relevance question for query-focused extraction.
            only_main_content: Whether content extraction should prefer main content.
            follow_pagination: Whether article extraction should follow likely next-page links.
            headless: Whether browser launches should be headless.

        Returns:
            Focused inspection payload.
        """
        mode = normalize_page_mode(mode)
        views = normalize_inspect_views(view)
        page_kwargs = build_page_kwargs(mode, headless=headless)
        result: dict[str, object] = {
            "url": url,
            "mode": mode,
            "views": views,
        }

        scrape_formats = scrape_formats_for_views(views)
        if "requests" in views and "api_payloads" in views:
            scrape_formats = [fmt for fmt in scrape_formats if fmt != "api_payloads"]

        if scrape_formats:
            scrape_result = await sdk_scrape(
                url=url,
                formats=scrape_formats,
                only_main_content=only_main_content,
                follow_pagination=follow_pagination,
                article_max_pages=3,
                **page_kwargs,
            )
            _set_if_missing(result, "final_url", scrape_result.get("url"))
            if "metadata" in views:
                _set_if_missing(result, "metadata", scrape_result.get("metadata"))
            if "content" in views:
                result["content"] = scrape_result.get("markdown", "")
            for key in ("app_state", "article", "contacts", "technologies", "api_payloads"):
                if key in views and key in scrape_result:
                    result[key] = scrape_result[key]

        if needs_fetch_page(views) or ("api_payloads" in views and "api_payloads" not in result):
            fetch_result = await sdk_fetch_page(
                url=url,
                include_html="html" in views,
                include_headers="headers" in views,
                include_requests="requests" in views,
                include_api_payloads="api_payloads" in views and "api_payloads" not in result,
                **page_kwargs,
            )
            _set_if_missing(result, "final_url", fetch_result.get("final_url"))
            if "metadata" in views:
                _set_if_missing(result, "metadata", fetch_result.get("metadata"))
            if "html" in views:
                result["html"] = fetch_result.get("html", "")
            if "headers" in views:
                result["headers"] = fetch_result.get("headers", {})
            if "links" in views:
                result["links"] = {
                    "page_links": fetch_result.get("page_links", []),
                    "resources": fetch_result.get("resources", []),
                    "link_count": fetch_result.get("page_links_found", 0),
                    "resource_count": fetch_result.get("resources_found", 0),
                }
            if "requests" in views:
                result["requests"] = fetch_result.get("requests", [])
            if "api_payloads" in views and "api_payloads" not in result:
                result["api_payloads"] = fetch_result.get("api_payloads", [])
            browser_details = extract_browser_details(fetch_result)
            if browser_details is not None:
                result["browser"] = browser_details

        if query:
            query_result = await sdk_query_page(
                url=url,
                query=query,
                **page_kwargs,
            )
            _set_if_missing(result, "final_url", query_result.get("url"))
            if "metadata" in views:
                _set_if_missing(result, "metadata", query_result.get("metadata"))
            result["query_result"] = {
                "question": query,
                "fit_text": query_result.get("fit_markdown", ""),
                "fit_chunks": query_result.get("fit_chunks", []),
            }

        if "forms" in views:
            forms_result = await sdk_forms(
                url=url,
                include_fill_suggestions=True,
                **page_kwargs,
            )
            _set_if_missing(result, "final_url", forms_result.get("url"))
            if "metadata" in views:
                _set_if_missing(result, "metadata", forms_result.get("metadata"))
            result["forms"] = forms_result.get("forms", [])

        return result

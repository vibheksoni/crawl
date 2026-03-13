"""Scrape format helpers."""

from typing import Literal

from .chunking import rank_text_chunks
from .page import extract_links_from_html, render_clean_html, render_page_content

ScrapeFormat = Literal["markdown", "text", "html", "links", "metadata", "fit_markdown", "app_state", "contacts"]


def build_scrape_result(
    page_result: dict,
    formats: list[ScrapeFormat] | None = None,
    only_main_content: bool = True,
    query: str | None = None,
) -> dict:
    """Build a multi-format scrape payload from a structured page result.

    Args:
        page_result: Structured page result from ``fetch_page``.
        formats: Requested output formats.
        only_main_content: Whether to prefer main content.
        query: Optional query for relevant chunk extraction.

    Returns:
        Scrape payload with the requested formats.
    """
    requested_formats = formats or ["markdown"]
    html = page_result.get("html", "")
    result = {
        "url": page_result["final_url"],
        "metadata": page_result.get("metadata", {}),
        "source": page_result.get("source"),
        "cache_hit": page_result.get("cache_hit", False),
    }

    if "markdown" in requested_formats:
        result["markdown"] = render_page_content(
            html,
            output_format="markdown",
            only_main_content=only_main_content,
        )
    if "text" in requested_formats:
        result["text"] = render_page_content(
            html,
            output_format="text",
            only_main_content=only_main_content,
        )
    if "html" in requested_formats:
        result["html"] = render_clean_html(html, only_main_content=only_main_content)
    if "links" in requested_formats:
        result["links"] = extract_links_from_html(
            html,
            page_result["final_url"],
            only_main_content=only_main_content,
        )
    if "metadata" in requested_formats:
        result["metadata"] = page_result.get("metadata", {})
    if "app_state" in requested_formats:
        result["app_state"] = page_result.get("app_state", {})
    if "contacts" in requested_formats:
        result["contacts"] = page_result.get("contacts", {})
    if "fit_markdown" in requested_formats:
        markdown = render_page_content(
            html,
            output_format="markdown",
            only_main_content=only_main_content,
        )
        ranked = rank_text_chunks(markdown, query or "", strategy="sliding", chunk_size=120, overlap=30, top_k=5)
        result["fit_markdown"] = "\n\n---\n\n".join(item["text"] for item in ranked)
        result["fit_chunks"] = ranked

    return result

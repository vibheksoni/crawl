"""Shared MCP-facing choice types and constants."""

from typing import Literal

SearchDepth = Literal["quick", "research"]
SearchProvider = Literal["auto", "google", "searxng", "hybrid"]
PageMode = Literal["auto", "http", "browser"]
InspectView = Literal[
    "content",
    "metadata",
    "links",
    "html",
    "headers",
    "app_state",
    "article",
    "contacts",
    "forms",
    "technologies",
    "api_payloads",
    "requests",
]
SiteStrategy = Literal["map", "crawl", "feeds", "technologies"]

INSPECT_DEFAULT_VIEWS = ("content", "metadata")
SCRAPE_FORMAT_BY_VIEW = {
    "content": "markdown",
    "metadata": "metadata",
    "app_state": "app_state",
    "article": "article",
    "contacts": "contacts",
    "technologies": "technologies",
    "api_payloads": "api_payloads",
}
FETCH_PAGE_VIEWS = {"links", "html", "headers", "requests"}

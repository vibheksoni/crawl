# SDK Guide

## Public Surface

The SDK is exported from `src/crawl/sdk/__init__.py`.

Async entrypoints:

- `websearch`
- `research`
- `fetch`
- `fetch_page`
- `scrape`
- `batch_scrape`
- `query_page`
- `map_site`
- `crawl`
- `extract`
- `forms`
- `article`
- `feeds`
- `contacts`
- `tech`
- `tech_grep`
- `screenshot`

Support utilities:

- `normalize_url`
- `get_url_dedupe_key`
- `get_canonical_dedupe_key`
- `benchmark_fast_crawl`
- `append_dataset_rows`
- `load_dataset_rows`
- `export_dataset`
- `fingerprint_page`
- `search_technology_definitions`
- `get_technology_definition`
- `update_technology_definitions`
- `build_plugin_signature_file`
- `compute_simhash`
- `simhash_distance`
- `extract_article_content`
- `extract_article_metadata`

## Import And Setup

```python
import asyncio

from crawl.sdk import fetch_page, scrape, websearch
```

## Shared SDK Concepts

### Fetch Modes

Most page-oriented functions accept:

- `mode="auto"`: start with HTTP and use browser fallback when needed
- `mode="http"`: force HTTP-only behavior
- `mode="browser"`: force browser rendering

### Search Providers

Search-capable functions accept:

- `provider="google"`
- `provider="searxng"`
- `provider="auto"`
- `provider="hybrid"`

Use `searxng_url` or `SEARXNG_URL` for local or remote SearXNG.

### Shared Network Controls

Many functions support:

- `user_agent`
- `headers`
- `accept_invalid_certs`
- `proxy_url`
- `proxy_urls`
- `max_retries`
- `retry_backoff_ms`

### Shared Cache Controls

Many functions support:

- `cache`
- `cache_dir`
- `cache_ttl_seconds`
- `cache_revalidate`

The cache is SQLite-backed.

### Shared Browser Controls

Browser-capable functions commonly support:

- `resource_mode`
- `blocked_resource_types`
- `blocked_url_patterns`
- `bypass_service_worker`
- `consent_mode`
- `max_consent_actions`
- `headless`

Some browser-heavy paths also support:

- `include_requests`
- `include_api_payloads`
- `max_api_payloads`
- `max_api_payload_bytes`
- `interaction_mode`
- `max_interactions`
- `session_dir`

## Function Groups

### Search And Research

`websearch(...)`

- returns normalized search results
- can optionally attach scraped result content

`research(...)`

- searches first
- reads a bounded set of top results
- returns merged ranked chunks across sources

### One-Page Reading

`fetch(...)`

- returns markdown or plain text

`fetch_page(...)`

- returns structured page details
- can include headers, HTML, links, resources, forms, app state, contacts, technologies, browser requests, and API payloads

`scrape(...)`

- returns one or more content formats from one page

`batch_scrape(...)`

- runs `scrape` over many URLs with bounded concurrency

`query_page(...)`

- extracts query-relevant chunks from a page

### Site Discovery

`map_site(...)`

- discovers URLs inside a site scope
- can rank them against a search phrase

`crawl(...)`

- bounded site traversal
- supports BFS or best-first crawling
- supports robots, sitemap seeding, budgets, delays, autoscaling, dedupe, browser capture, and persisted crawl state

### Structured And Specialized Analysis

`extract(...)`

- runs CSS selector-based extraction with a schema

`forms(...)`

- extracts forms and optional fill previews

`article(...)`

- extracts readable article content
- can follow multi-page pagination

`feeds(...)`

- discovers and validates RSS, Atom, RDF, and JSON Feed endpoints

`contacts(...)`

- extracts emails, phone numbers, and social links

`tech(...)`

- fingerprints technologies from one page or a small site slice

`tech_grep(...)`

- searches page signals using literal text or regex

### Visual Capture

`screenshot(...)`

- returns JPEG bytes
- supports `headless`
- removes temporary PNG capture files after conversion

## Browser Features

### Consent Handling

Browser-capable paths can automatically handle consent banners and overlay gates through:

- `consent_mode="auto" | "reject" | "accept" | "close" | "none"`
- `max_consent_actions`

### Resource Blocking

Presets:

- `none`
- `safe`
- `aggressive`

Extra controls:

- `blocked_resource_types`
- `blocked_url_patterns`

### Headless Control

Browser-capable SDK functions now accept `headless: bool = False`.

This applies to:

- browser fetches
- browser fallbacks triggered by `mode="auto"`
- browser-based crawling
- screenshot capture
- search-related browser scraping paths

## Persistence Helpers

Datasets:

- `append_dataset_rows`
- `load_dataset_rows`
- `export_dataset`

Crawl state:

- `crawl(..., state_path="...")`

Cache:

- SQLite-backed page cache under `.crawl_cache` by default

## Example

```python
import asyncio

from crawl.sdk import fetch_page, scrape, websearch


async def main() -> None:
    search_payload = await websearch(
        "python async browser automation",
        provider="auto",
        max_results=5,
        pages=1,
    )

    page_payload = await fetch_page(
        "https://example.com",
        mode="browser",
        include_html=True,
        include_headers=True,
        headless=True,
        cache=True,
    )

    scrape_payload = await scrape(
        "https://www.python.org",
        formats=["markdown", "metadata", "app_state"],
        mode="auto",
        cache=True,
    )

    print(search_payload["count"])
    print(page_payload["final_url"])
    print(scrape_payload["metadata"]["title"])


asyncio.run(main())
```

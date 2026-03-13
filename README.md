<p align="center">
  <img src="assets/crawl.png" alt="crawl" width="320">
</p>

<h1 align="center">crawl</h1>

<p align="center">
  Async web search, fetch, crawl, and screenshot tooling with three integration layers.
</p>

<p align="center">
  <code>sdk</code> reusable Python functions for embedding in other services
  <br>
  <code>mcp</code> FastMCP wrapper for agent workflows
  <br>
  <code>cli</code> raw command-line interface for direct usage
</p>

<p align="center">
  Stealth-first by design:
  <code>curl_cffi</code> for HTTP fetching
  <br>
  <code>nodriver</code> for browser automation and lower-detection page interaction
  <br>
  No <code>requests</code>-based runtime path for crawling or scraping
</p>

## Structure

```text
src/crawl/
  sdk/   # reusable search, fetch, crawl, screenshot logic
  mcp/   # FastMCP wrapper around the SDK
  cli/   # argparse-based CLI wrapper around the SDK
```

## Install

```powershell
python -m pip install -e .
```

Or install the pinned runtime dependencies directly:

```powershell
python -m pip install -r requirements.txt
```

## SDK Usage

```python
import asyncio

from crawl.sdk import batch_scrape, crawl, extract, fetch, fetch_page, forms, map_site, query_page, scrape, websearch


async def main() -> None:
    search_results = await websearch("python async browser automation", max_results=5, pages=1)
    searxng_results = await websearch(
        "python async browser automation",
        max_results=5,
        pages=1,
        provider="searxng",
        searxng_url="http://127.0.0.1:8888",
    )
    hybrid_results = await websearch(
        "python async browser automation",
        max_results=5,
        pages=1,
        provider="hybrid",
        searxng_url="http://127.0.0.1:8888",
        scrape_results=True,
        scrape_limit=2,
        scrape_formats=["markdown"],
    )
    scrape_result = await scrape(
        "https://www.python.org",
        formats=["markdown", "links", "metadata", "app_state"],
        cache=True,
    )
    batch_result = await batch_scrape(
        ["https://example.com", "https://www.python.org"],
        formats=["markdown", "metadata"],
        max_concurrency=2,
        cache=True,
    )
    extracted = await extract(
        "https://www.python.org/events/python-events/",
        schema={
            "baseSelector": "li, article",
            "multiple": True,
            "fields": [
                {"name": "title", "selector": "a", "type": "text"},
                {"name": "url", "selector": "a", "type": "attribute", "attribute": "href", "absolute": True},
            ],
        },
        cache=True,
    )
    page_query = await query_page(
        "https://www.python.org",
        "data science",
        cache=True,
    )
    form_data = await forms(
        "https://httpbin.org/forms/post",
        include_fill_suggestions=True,
        cache=True,
    )
    page = await fetch_page(
        "https://httpbin.org/headers",
        mode="http",
        include_headers=True,
        include_html=True,
        include_app_state=True,
        pattern_mode="glob",
        full_resources=True,
        user_agent="crawl-sdk-demo/1.0",
        headers={"X-Demo": "yes"},
        cache=True,
    )
    browser_page = await fetch_page(
        "https://www.python.org",
        mode="browser",
        include_requests=True,
        interaction_mode="auto",
        max_interactions=1,
        session_dir="./browser-session",
    )
    page_text = await fetch(
        "https://example.com",
        output_format="text",
        mode="auto",
        cache=True,
    )
    crawl_results = await crawl(
        "https://www.python.org",
        max_pages=5,
        max_depth=1,
        allowed_domains=["docs.python.org"],
        budget={"*": 5, "/3/tutorial/": 3},
        delay_ms=500,
        path_delays={"/3/tutorial/": 1000},
        respect_robots_txt=True,
        seed_sitemap=True,
        full_resources=True,
        dedupe_by_signature=True,
        cache=True,
    )
    map_result = await map_site(
        "https://docs.python.org/3/tutorial/",
        search="interpreter",
        limit=5,
        include_patterns=["tutorial"],
    )
    print(search_results["count"])
    print(searxng_results["count"])
    print(hybrid_results["count"])
    print(scrape_result["url"])
    print(batch_result["completed"])
    print(extracted["data"][0]["title"])
    print(page_query["fit_chunks"][0]["score"])
    print(form_data["count"])
    print(page["cache_hit"])
    print(page["signature"])
    print(len(browser_page["requests"]))
    print(page_text[:200])
    print(crawl_results["pages_crawled"])
    print(map_result["urls"][0]["url"])


asyncio.run(main())
```

## CLI Usage

Run from the repo root:

```powershell
python cli.py websearch "python async browser automation" --max-results 5 --pages 1
python cli.py websearch "python async browser automation" --provider searxng --searxng-url http://127.0.0.1:8888 --max-results 5 --pages 2
python cli.py websearch "python async browser automation" --provider auto --searxng-url http://127.0.0.1:8888 --max-results 5 --pages 1
python cli.py websearch "python async browser automation" --provider hybrid --searxng-url http://127.0.0.1:8888 --scrape-results --scrape-limit 2 --scrape-format markdown --max-results 5 --pages 1
python cli.py scrape https://www.python.org --format markdown --format links --format metadata --format app_state --cache
python cli.py batch-scrape https://example.com https://www.python.org --format markdown --format metadata --max-concurrency 2 --cache
python cli.py map https://docs.python.org/3/tutorial/ --search interpreter --limit 5 --include-pattern tutorial
python cli.py extract https://www.python.org/events/python-events/ --schema-file _ignore\\extract-schema.json --cache
python cli.py forms https://httpbin.org/forms/post --fill-preview --cache
python cli.py query https://www.python.org "data science" --cache
python cli.py fetch https://example.com --format text --mode auto --cache --cache-dir .crawl_cache
python cli.py fetch-page https://example.com --mode http --max-retries 3 --retry-backoff-ms 250 --include-app-state
python cli.py fetch-page https://httpbin.org/headers --mode http --include-html --include-headers --full-resources --pattern-mode glob --user-agent crawl-cli-demo/1.0 --header "X-Demo: yes" --cache
python cli.py fetch-page https://www.python.org --mode browser --include-requests --interaction-mode auto --max-interactions 1 --session-dir .\\browser-session
python cli.py crawl https://www.python.org --mode browser --max-pages 5 --crawl-strategy best_first --crawl-query docs --allow-domain docs.python.org --budget "*=5" --budget "/3/tutorial/=3" --delay-ms 500 --path-delay "/3/tutorial/=1000" --auto-throttle --minimum-delay-ms 200 --maximum-delay-ms 1000 --seed-sitemap --full-resources --dedupe-by-signature --include-requests --interaction-mode auto --session-dir .\\browser-session --respect-robots-txt --cache
python cli.py map https://docs.python.org/3/tutorial/ --search interpreter --output-template "{{url}} | {{title}}"
python cli.py batch-scrape https://example.com https://www.python.org --format metadata --jsonl --field url --field metadata.title --store-field url
python cli.py screenshot https://example.com --output example.jpg
python cli.py benchmark https://example.com --max-pages 12 --samples 3 --concurrency 1 2 4 8
```

After installation, you can also use:

```powershell
crawl-cli --help
```

If `--provider searxng` is used without `--searxng-url`, the code will look for `SEARXNG_URL` and then fall back to `http://127.0.0.1:8888`.

`scrape`, `batch-scrape`, `fetch`, `fetch-page`, `crawl`, `map`, `extract`, `forms`, `query`, and `websearch` support request controls such as repeated `--proxy-url` flags, `--user-agent`, repeated `--header` flags, `--accept-invalid-certs`, retry/backoff controls, adaptive throttling, and SQLite-backed caching via `--cache`, `--cache-dir`, and `--cache-ttl`. The HTTP runtime path uses `curl_cffi`, and browser-mode flows use `nodriver`.

Persistent browser state is opt-in only. If you pass `session_dir` in the SDK or `--session-dir` in the CLI, browser cookies and profile state are reused. If you omit it, browser sessions remain ephemeral.

## MCP Usage

Run from the repo root:

```powershell
python server.py
```

After installation, you can also use:

```powershell
crawl-mcp
```

## Current Capabilities

- `websearch`: supports Google browser scraping, SearXNG, automatic provider fallback, hybrid merged search, optional proxy routing, and optional scraped content attachment for top results
- `scrape`: returns one or more content formats from a single page, including markdown, text, cleaned HTML, links, metadata, and embedded app-state payloads
- `batch_scrape`: scrapes multiple URLs concurrently with one normalized result envelope
- `map_site`: discovers URLs within a site and can rank them by relevance to a search phrase
- `extract`: performs selector-based structured extraction using reusable schemas
- `forms`: extracts forms and can generate safe fill previews
- `query_page`: returns query-relevant chunks and fit markdown from a page
- `fetch_page`: returns structured page details including metadata, discovered page links, discovered resources, content signatures, timing, bytes transferred, optional headers, optional raw HTML, optional embedded app-state extraction, request controls, cache hits, and optional browser-side request capture / lightweight interaction results
- `fetch`: loads a page and returns markdown or plain-text content using `auto`, `http`, or `browser` mode with optional SQLite caching and retry/backoff controls
- `crawl`: supports depth limits, include/exclude URL filters, explicit pattern modes, optional subdomain crawling, extra allowed domains, budgets, per-path delays, optional robots.txt enforcement, sitemap seeding, HTML sitemap discovery, configurable HTTP concurrency, `bfs` or `best_first` traversal, full resource discovery, duplicate-content suppression by signature, browser request capture, lightweight interaction, opt-in session persistence, retry/backoff handling, adaptive throttling, and SQLite caching
- `screenshot`: captures a page and returns JPEG bytes from the SDK while the CLI writes them to disk
- `benchmark`: measures the HTTP-only crawler across multiple concurrency settings

Embedded app-state extraction currently targets JSON-LD blocks, classic hydration containers such as `__NEXT_DATA__` and `__NUXT_DATA__`, streaming Next.js `self.__next_f.push(...)` chunks, and common state assignments such as Redux-, Apollo-, Remix-, and Nuxt-style globals.

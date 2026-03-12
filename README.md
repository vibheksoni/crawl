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

from crawl.sdk import crawl, fetch, fetch_page, websearch


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
    )
    page = await fetch_page(
        "https://httpbin.org/headers",
        mode="http",
        include_headers=True,
        include_html=True,
        pattern_mode="glob",
        full_resources=True,
        user_agent="crawl-sdk-demo/1.0",
        headers={"X-Demo": "yes"},
        cache=True,
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
    print(search_results["count"])
    print(searxng_results["count"])
    print(hybrid_results["count"])
    print(page["cache_hit"])
    print(page["signature"])
    print(page_text[:200])
    print(crawl_results["pages_crawled"])


asyncio.run(main())
```

## CLI Usage

Run from the repo root:

```powershell
python cli.py websearch "python async browser automation" --max-results 5 --pages 1
python cli.py websearch "python async browser automation" --provider searxng --searxng-url http://127.0.0.1:8888 --max-results 5 --pages 2
python cli.py websearch "python async browser automation" --provider auto --searxng-url http://127.0.0.1:8888 --max-results 5 --pages 1
python cli.py websearch "python async browser automation" --provider hybrid --searxng-url http://127.0.0.1:8888 --proxy-url http://127.0.0.1:8080 --max-results 5 --pages 1
python cli.py fetch https://example.com --format text --mode auto --cache --cache-dir .crawl_cache
python cli.py fetch-page https://httpbin.org/headers --mode http --include-html --include-headers --full-resources --pattern-mode glob --user-agent crawl-cli-demo/1.0 --header "X-Demo: yes" --cache
python cli.py crawl https://www.python.org --max-pages 5 --max-depth 1 --allow-domain docs.python.org --budget "*=5" --budget "/3/tutorial/=3" --delay-ms 500 --path-delay "/3/tutorial/=1000" --seed-sitemap --full-resources --dedupe-by-signature --respect-robots-txt --cache
python cli.py screenshot https://example.com --output example.jpg
python cli.py benchmark https://example.com --max-pages 12 --samples 3 --concurrency 1 2 4 8
```

After installation, you can also use:

```powershell
crawl-cli --help
```

If `--provider searxng` is used without `--searxng-url`, the code will look for `SEARXNG_URL` and then fall back to `http://127.0.0.1:8888`.

`fetch`, `fetch-page`, `crawl`, and `websearch` also support request controls such as repeated `--proxy-url` flags, `--user-agent`, repeated `--header` flags, `--accept-invalid-certs`, and SQLite-backed caching via `--cache`, `--cache-dir`, and `--cache-ttl`.

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

- `websearch`: supports Google browser scraping, SearXNG, automatic provider fallback, hybrid merged search, and optional proxy routing
- `fetch_page`: returns structured page details including metadata, discovered page links, discovered resources, content signatures, timing, bytes transferred, optional headers, optional raw HTML, request controls, and cache hits
- `fetch`: loads a page and returns markdown or plain-text content using `auto`, `http`, or `browser` mode with optional SQLite caching
- `crawl`: supports depth limits, include/exclude URL filters, explicit pattern modes, optional subdomain crawling, extra allowed domains, budgets, per-path delays, optional robots.txt enforcement, sitemap seeding, HTML sitemap discovery, configurable HTTP concurrency, full resource discovery, duplicate-content suppression by signature, and SQLite caching
- `screenshot`: captures a page and returns JPEG bytes from the SDK while the CLI writes them to disk
- `benchmark`: measures the HTTP-only crawler across multiple concurrency settings

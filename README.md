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

from crawl.sdk import batch_scrape, contacts, crawl, extract, fetch, fetch_page, feeds, forms, map_site, query_page, research, scrape, tech, websearch


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
    research_result = await research(
        "python async browser automation",
        max_results=5,
        pages=1,
        research_limit=3,
        cache=True,
    )
    form_data = await forms(
        "https://httpbin.org/forms/post",
        include_fill_suggestions=True,
        cache=True,
    )
    feed_data = await feeds(
        "https://www.python.org/blogs/",
        spider_depth=1,
        cache=True,
    )
    contact_data = await contacts(
        "https://www.python.org",
        cache=True,
    )
    tech_data = await tech(
        "https://nextjs.org",
        mode="http",
        aggression=1,
        cache=True,
    )
    page = await fetch_page(
        "https://httpbin.org/headers",
        mode="http",
        include_headers=True,
        include_html=True,
        include_app_state=True,
        include_contacts=True,
        include_technologies=True,
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
    print(contact_data["contacts"]["social_count"])
    print(tech_data["technologies"]["technologies"][0]["name"])
    print(research_result["merged_chunks"][0]["url"])
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
python cli.py websearch "python async browser automation" --provider hybrid --searxng-url http://127.0.0.1:8888 --scrape-results --scrape-limit 2 --scrape-format markdown --max-results 5 --pages 1 --max-retries 2 --retry-backoff-ms 250
python cli.py scrape https://www.python.org --format markdown --format links --format metadata --format app_state --max-retries 3 --retry-backoff-ms 250 --cache
python cli.py batch-scrape https://example.com https://www.python.org --format markdown --format metadata --max-concurrency 2 --cache
python cli.py map https://docs.python.org/3/tutorial/ --search interpreter --limit 5 --include-pattern tutorial --max-retries 2 --retry-backoff-ms 250
python cli.py extract https://www.python.org/events/python-events/ --schema-file _ignore\\extract-schema.json --cache
python cli.py forms https://httpbin.org/forms/post --fill-preview --cache
python cli.py feeds https://www.python.org/blogs/ --mode http --spider-depth 1 --max-feeds 5 --cache
python cli.py contacts https://www.python.org --cache
python cli.py tech https://nextjs.org --mode http --aggression 1
python cli.py tech-grep https://nextjs.org --text next.js --search headers[x-powered-by]
python cli.py tech-list --search next --limit 10
python cli.py tech-info Next.js
python cli.py tech-update
python cli.py tech-import C:\\path\\to\\plugin-dir --output-file .\\plugin-signatures.json
python cli.py query https://www.python.org "data science" --cache
python cli.py research "python async browser automation" --provider auto --max-results 5 --pages 1 --research-limit 3 --cache
python cli.py fetch https://example.com --format text --mode auto --cache --cache-dir .crawl_cache
python cli.py fetch-page https://example.com --mode http --max-retries 3 --retry-backoff-ms 250 --include-app-state --include-contacts --include-technologies --technology-aggression 1
python cli.py fetch-page https://httpbin.org/headers --mode http --include-html --include-headers --full-resources --pattern-mode glob --user-agent crawl-cli-demo/1.0 --header "X-Demo: yes" --cache
python cli.py fetch-page https://example.com --mode http --cache --cache-ttl 0 --cache-revalidate --include-headers
python cli.py fetch-page https://www.python.org --mode browser --include-requests --interaction-mode auto --max-interactions 1 --session-dir .\\browser-session
python cli.py crawl https://docs.python.org/3/tutorial/ --mode fast --max-pages 25 --max-depth 2 --state-path .\\crawl-state.json
python cli.py crawl https://docs.python.org/3/tutorial/ --mode fast --max-pages 25 --max-depth 2 --max-concurrency 6 --autoscale-concurrency --min-concurrency 2 --cpu-target-percent 75 --memory-target-percent 80 --include-technologies --technology-aggression 1
python cli.py crawl https://example.com/docs --mode fast --max-pages 25 --dedupe-by-similarity --similarity-threshold 3
python cli.py crawl https://www.python.org --mode browser --max-pages 5 --crawl-strategy best_first --crawl-query docs --allow-domain docs.python.org --budget "*=5" --budget "/3/tutorial/=3" --delay-ms 500 --path-delay "/3/tutorial/=1000" --auto-throttle --minimum-delay-ms 200 --maximum-delay-ms 1000 --seed-sitemap --full-resources --dedupe-by-signature --include-requests --interaction-mode auto --session-dir .\\browser-session --respect-robots-txt --cache
python cli.py map https://docs.python.org/3/tutorial/ --search interpreter --output-template "{{url}} | {{title}}"
python cli.py map https://docs.python.org/3/tutorial/ --search interpreter --output-template "{{total}}"
python cli.py batch-scrape https://example.com https://www.python.org --format metadata --jsonl --field url --field metadata.title --store-field url
python cli.py crawl https://docs.python.org/3/tutorial/ --mode fast --max-pages 2 --dataset-dir .\\storage\\datasets --dataset-name crawl-results
python cli.py dataset-export crawl-results --dataset-dir .\\storage\\datasets --format csv
python cli.py screenshot https://example.com --output example.jpg
python cli.py benchmark https://example.com --max-pages 12 --samples 3 --concurrency 1 2 4 8
python cli.py benchmark https://example.com/docs --max-pages 20 --samples 3 --concurrency 2 4 8 --dedupe-by-similarity --similarity-threshold 3
```

After installation, you can also use:

```powershell
crawl-cli --help
```

If `--provider searxng` is used without `--searxng-url`, the code will look for `SEARXNG_URL` and then fall back to `http://127.0.0.1:8888`.

`scrape`, `batch-scrape`, `fetch`, `fetch-page`, `crawl`, `map`, `extract`, `forms`, `contacts`, `tech`, `query`, `research`, and `websearch` support request controls such as repeated `--proxy-url` flags, `--user-agent`, repeated `--header` flags, `--accept-invalid-certs`, retry/backoff controls, adaptive throttling, blocked-response detection, opportunistic proxy rotation when a proxy pool is supplied, and SQLite-backed caching via `--cache`, `--cache-dir`, `--cache-ttl`, and `--cache-revalidate`. The HTTP runtime path uses `curl_cffi`, and browser-mode flows use `nodriver`.

If you enable `cache_revalidate=True` in the SDK or `--cache-revalidate` in the CLI/MCP layer, stale cached HTTP entries will reuse stored `ETag` and `Last-Modified` validators. A `304 Not Modified` response keeps the cached body, updates response metadata, and marks the result with `cache_revalidated`, `cache_not_modified`, and `revalidation_status_code`.

Most CLI commands can also append normalized row outputs into a local dataset with `--dataset-dir` and `--dataset-name`, then export those persisted rows later with `dataset-export` as JSON, JSONL, or CSV.

Feed discovery can validate RSS, Atom, RDF, and JSON Feed endpoints from autodiscovery links, feed-like anchors, common feed paths, and a small scored internal spider pass. The result payload includes detected format, title, description, entry counts, and sample entry URLs for each validated feed.

Persistent browser state is opt-in only. If you pass `session_dir` in the SDK or `--session-dir` in the CLI, browser cookies and profile state are reused. If you omit it, browser sessions remain ephemeral.

Crawl queue persistence is also opt-in. If you pass `state_path` in the SDK or `--state-path` in the CLI, the crawler will autosave frontier, visited URLs, budget state, signatures, and accumulated results after each batch and resume from the saved state on the next run.

Autoscaled concurrency is available for long-running HTTP crawls. If you pass `autoscale_concurrency=True` in the SDK or `--autoscale-concurrency` in the CLI, the crawler will adapt batch concurrency between `min_concurrency` and `max_concurrency` based on sampled CPU and memory pressure and include autoscale snapshots in the result payload.

Near-duplicate suppression is available for long-running crawls. If you pass `dedupe_by_similarity=True` in the SDK or `--dedupe-by-similarity` in the CLI/MCP layer, the crawler will compute a main-content simhash for each HTML page, mark near-duplicates with `is_near_duplicate`, `near_duplicate_of`, and `similarity_distance`, and stop expanding them when the distance is within `similarity_threshold`.

SDK users can also pass lightweight lifecycle hooks into `fetch_page()` and `crawl()` using a `hooks` mapping. Supported crawl hook names are `on_crawl_start`, `on_enqueue`, `on_result`, `on_error`, and `on_crawl_end`. Fetch hooks support `on_request_start` and `on_request_end`.

Technology fingerprinting supports lightweight aggression levels inspired by classic web scanners. Level `1` uses cheap passive contexts such as headers, cookies, meta tags, and URLs. Level `2` adds script source matching. Level `3` enables full HTML body pattern matching. The bundled definitions file can be refreshed with `tech-update`.

If the `tech` command receives a bare hostname instead of a full URL, it will try both `https://` and `http://` variants automatically. `tech-grep` provides ad-hoc text or regex matching against contexts such as `body`, `all`, `url`, `headers`, `headers[name]`, `meta[name]`, and `script`.

The bundled plugin-signature cache can also be rebuilt locally with `tech-import` if you want to regenerate the declarative fingerprint corpus from one or more local plugin directories.

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
- `scrape`: returns one or more content formats from a single page, including markdown, text, cleaned HTML, links, metadata, embedded app-state payloads, and contact/social enrichment
- `batch_scrape`: scrapes multiple URLs concurrently with one normalized result envelope
- `map_site`: discovers URLs within a site and can rank them by relevance to a search phrase
- `extract`: performs selector-based structured extraction using reusable schemas
- `forms`: extracts forms and can generate safe fill previews
- `feeds`: discovers and validates RSS, Atom, RDF, and JSON Feed endpoints from a page or small internal site slice
- `contacts`: extracts emails, phone numbers, and grouped social links from a page
- `tech`: fingerprints technologies, versions, categories, implied stacks, and generic page signals from a page or small site slice
- `tech_grep`: performs ad-hoc literal or regex matching across page signal contexts for scanner-style custom checks
- `query_page`: returns query-relevant chunks and fit markdown from a page, plus app-state-derived relevance matches when embedded payloads contain useful text
- `research`: searches the web, deeply analyzes the top result pages, and returns merged ranked chunks across sources for agent-style research workflows
- `fetch_page`: returns structured page details including metadata, discovered page links, discovered resources, content signatures, timing, bytes transferred, optional headers, optional raw HTML, optional embedded app-state extraction, optional contact/social extraction, optional technology fingerprinting, detected block reasons, request controls, cache hits, and optional browser-side request capture / lightweight interaction results
- `fetch`: loads a page and returns markdown or plain-text content using `auto`, `http`, or `browser` mode with optional SQLite caching and retry/backoff controls
- `crawl`: supports depth limits, include/exclude URL filters, explicit pattern modes, optional subdomain crawling, extra allowed domains, budgets, per-path delays, optional robots.txt enforcement, sitemap seeding, HTML sitemap discovery, configurable HTTP concurrency, `bfs` or `best_first` traversal, full resource discovery, duplicate-content suppression by exact signature or near-duplicate similarity, browser request capture, lightweight interaction, opt-in session persistence, retry/backoff handling, adaptive throttling, and SQLite caching
- `crawl`: supports opt-in persistent crawl state files for autosave and resume across runs
- `crawl`: supports opt-in autoscaled concurrency based on sampled CPU and memory pressure
- `dataset_export`: exports persisted local datasets as JSON, JSONL, or CSV with union-key CSV support
- `screenshot`: captures a page and returns JPEG bytes from the SDK while the CLI writes them to disk
- `benchmark`: measures the HTTP-only crawler across multiple concurrency settings, with optional near-duplicate suppression and stale-cache revalidation

Embedded app-state extraction currently targets JSON-LD blocks, classic hydration containers such as `__NEXT_DATA__` and `__NUXT_DATA__`, streaming Next.js `self.__next_f.push(...)` chunks, and common state assignments such as Redux-, Apollo-, Remix-, and Nuxt-style globals.

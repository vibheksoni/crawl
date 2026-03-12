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

from crawl.sdk import fetch, websearch


async def main() -> None:
    search_results = await websearch("python async browser automation", max_results=5, pages=1)
    searxng_results = await websearch(
        "python async browser automation",
        max_results=5,
        pages=1,
        provider="searxng",
        searxng_url="http://127.0.0.1:8888",
    )
    page_text = await fetch("https://example.com", output_format="text")
    print(search_results["count"])
    print(searxng_results["count"])
    print(page_text[:200])


asyncio.run(main())
```

## CLI Usage

Run from the repo root:

```powershell
python cli.py websearch "python async browser automation" --max-results 5 --pages 1
python cli.py websearch "python async browser automation" --provider searxng --searxng-url http://127.0.0.1:8888 --max-results 5 --pages 2
python cli.py fetch https://example.com --format text
python cli.py crawl https://example.com --max-pages 3 --mode fast --max-concurrency 4
python cli.py screenshot https://example.com --output example.jpg
python cli.py benchmark https://example.com --max-pages 12 --samples 3 --concurrency 1 2 4 8
```

After installation, you can also use:

```powershell
crawl-cli --help
```

If `--provider searxng` is used without `--searxng-url`, the code will look for `SEARXNG_URL` and then fall back to `http://127.0.0.1:8888`.

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

- `websearch`: supports Google browser scraping by default and optional SearXNG JSON search via `provider="searxng"` or `--provider searxng`
- `fetch`: loads a page and returns markdown or plain-text content
- `crawl`: walks a site with a browser-assisted or HTTP-only strategy and configurable HTTP concurrency
- `screenshot`: captures a page and returns JPEG bytes from the SDK while the CLI writes them to disk
- `benchmark`: measures the HTTP-only crawler across multiple concurrency settings

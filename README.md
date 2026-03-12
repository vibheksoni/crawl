# crawl

Async web search, fetch, crawl, and screenshot tooling with three integration layers:

- `sdk`: reusable Python functions for embedding in other services
- `mcp`: FastMCP wrapper for agent workflows
- `cli`: raw command-line interface for direct usage

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
    page_text = await fetch("https://example.com", output_format="text")
    print(search_results["count"])
    print(page_text[:200])


asyncio.run(main())
```

## CLI Usage

Run from the repo root:

```powershell
python cli.py websearch "python async browser automation" --max-results 5 --pages 1
python cli.py fetch https://example.com --format text
python cli.py crawl https://example.com --max-pages 3 --mode fast
python cli.py screenshot https://example.com --output example.jpg
```

After installation, you can also use:

```powershell
crawl-cli --help
```

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

- `websearch`: opens Google in a browser session and extracts organic results, videos, People Also Ask items, and AI Overview text
- `fetch`: loads a page and returns markdown or plain-text content
- `crawl`: walks a site with a browser-assisted or HTTP-only strategy
- `screenshot`: captures a page and returns a compressed JPEG image

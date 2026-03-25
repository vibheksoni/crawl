<p align="center">
  <img src="assets/crawl.png" alt="crawl" width="320">
</p>

<h1 align="center">crawl</h1>

<p align="center">
  Async web search, fetch, crawl, extraction, and screenshot tooling with SDK, CLI, and MCP entrypoints.
</p>

<p align="center">
  <code>curl_cffi</code> for HTTP
  <br>
  <code>nodriver</code> for browser automation
  <br>
  <code>FastMCP</code> for the compact agent-facing MCP layer
</p>

## What It Is

`crawl` is organized into three layers:

- `sdk`: the full Python capability surface
- `cli`: direct command-line access to the SDK
- `mcp`: a smaller workflow-oriented server for AI agents

The SDK is the source of truth. The CLI wraps most of it. The MCP layer intentionally exposes fewer tools so agents do not get flooded with schemas.

## Install

Editable install:

```powershell
python -m pip install -e .
```

Pinned dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Entry Points

Repo-root entrypoints:

```powershell
python cli.py --help
python server.py
```

Installed scripts:

```powershell
crawl-cli --help
crawl-mcp
```

## Documentation

- [Overview](./docs/overview.md)
- [SDK Guide](./docs/sdk.md)
- [CLI Guide](./docs/cli.md)
- [MCP Guide](./docs/mcp.md)
- [Feature Notes](./docs/feature-notes.md)

## Highlights

- Search providers: `google`, `searxng`, `auto`, `hybrid`
- Browser-capable SDK and MCP paths support `headless`
- Consent handling and resource blocking are built into browser workflows
- Structured extraction, article extraction, forms, feeds, contacts, and technology fingerprinting are all in the SDK
- The MCP server exposes a compact tool surface:
  - `search_web`
  - `inspect_url`
  - `discover_site`
  - `extract_structured`
  - `capture_screenshot`

## Quick Examples

SDK:

```python
import asyncio

from crawl.sdk import fetch_page, websearch


async def main() -> None:
    search_payload = await websearch("python async browser automation", provider="auto")
    page_payload = await fetch_page("https://example.com", mode="browser", headless=True)
    print(search_payload["count"])
    print(page_payload["final_url"])


asyncio.run(main())
```

CLI:

```powershell
python cli.py websearch "python async browser automation" --provider auto --max-results 5 --pages 1
python cli.py fetch-page https://example.com --mode browser --include-html
```

MCP:

- run `python server.py`
- connect your MCP client to the stdio server
- use the compact workflow tools documented in [docs/mcp.md](./docs/mcp.md)

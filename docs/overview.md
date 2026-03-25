# crawl Overview

`crawl` is an async web research and extraction project with three entrypoints built on the same core SDK:

- `sdk`: reusable Python functions for application code and other services
- `cli`: direct command-line access to the SDK
- `mcp`: a compact FastMCP server designed for AI agents

The project is intentionally split this way:

- the SDK exposes the full capability set
- the CLI exposes most of the SDK surface with command flags
- the MCP server exposes a much smaller workflow-oriented interface so agents do not get flooded with tools

## Install

Editable install:

```powershell
python -m pip install -e .
```

Pinned dependency install:

```powershell
python -m pip install -r requirements.txt
```

## Project Layout

```text
src/crawl/
  sdk/   reusable search, fetch, crawl, screenshot, and parsing logic
  cli/   argparse-based wrapper around the SDK
  mcp/   FastMCP server built on top of the SDK
```

Important entrypoints:

- `crawl-cli` from `pyproject.toml`
- `crawl-mcp` from `pyproject.toml`
- `python cli.py ...` from the repo root
- `python server.py` from the repo root

## Core Capability Areas

Search and discovery:

- web search with Google, SearXNG, automatic fallback, or hybrid merge
- research workflow over top search results
- site mapping and bounded crawling
- feed discovery

Page inspection and extraction:

- plain text or markdown fetch
- structured page fetch with metadata, headers, links, resources, and browser capture
- multi-format scrape output
- selector-based structured extraction
- query-focused chunk ranking

Page analysis:

- article extraction with optional pagination following
- forms and fill-preview extraction
- contacts and social extraction
- technology fingerprinting and ad-hoc tech grep

Browser-assisted workflows:

- consent banner handling
- resource blocking
- browser request capture
- browser API payload capture
- screenshot capture
- optional browser session persistence
- explicit `headless` control in SDK and MCP browser-capable paths

Persistence and utilities:

- SQLite page cache
- persisted crawl state
- dataset append and export helpers
- URL normalization and dedupe keys
- benchmark helpers

## Shared Runtime Choices

HTTP runtime:

- uses `curl_cffi`
- no `requests` runtime path

Browser runtime:

- uses `nodriver`
- browser launch can be `headless=True` or `False`
- persistent profiles are opt-in through `session_dir`

Search provider selection:

- `google`
- `searxng`
- `auto`
- `hybrid`

## Documentation Map

- [SDK Guide](./sdk.md)
- [CLI Guide](./cli.md)
- [MCP Guide](./mcp.md)
- [Feature Notes](./feature-notes.md)

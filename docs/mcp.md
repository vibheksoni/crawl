# MCP Guide

## What The MCP Server Exposes

The MCP layer is intentionally compact. It does not mirror the full SDK surface.

Tools:

- `search_web`
- `inspect_url`
- `discover_site`
- `extract_structured`
- `capture_screenshot`

Resources:

- `crawl://guide/overview`
- `crawl://guide/workflows`
- `crawl://guide/extract-schema`

Resource templates:

- `crawl://guide/tool/{tool_name}`
- `crawl://catalog/technology-search/{query}`
- `crawl://catalog/technology/{name}`

Prompts:

- `research_workflow`
- `extraction_workflow`

## Why The MCP Surface Is Smaller

The MCP server is designed for agents, not for direct one-to-one SDK exposure.

That means:

- fewer tools to choose from
- broader, workflow-oriented tools
- guidance moved into resources and prompts instead of more tools
- read-only hints and descriptive tool metadata to help tool selection

## Running The MCP Server

From the repo root:

```powershell
python server.py
```

Installed script:

```powershell
crawl-mcp
```

Common stdio configuration:

```json
{
  "mcpServers": {
    "crawl": {
      "command": "C:\\Users\\win\\Desktop\\crawl\\venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\win\\Desktop\\crawl\\server.py"
      ],
      "env": {
        "SEARXNG_URL": "http://127.0.0.1:8888"
      }
    }
  }
}
```

## Tool Reference

### `search_web`

Use this first for open-web discovery.

Good for:

- finding candidate URLs
- running bounded multi-source research

Important inputs:

- `query`
- `depth="quick" | "research"`
- `provider="auto" | "google" | "searxng" | "hybrid"`
- `searxng_url`
- `include_page_context`
- `headless`

### `inspect_url`

Default one-page tool.

Good for:

- readable content
- metadata
- links
- headers
- app state
- article extraction
- contacts
- forms
- technologies
- browser requests and API payloads
- query-ranked excerpts

Important inputs:

- `url`
- `view`
- `mode="auto" | "http" | "browser"`
- `query`
- `only_main_content`
- `follow_pagination`
- `headless`

Important note:

- `mode` controls fetch strategy, not output format
- if you want raw HTML, include `html` in the `view`

Supported views:

- `content`
- `metadata`
- `links`
- `html`
- `headers`
- `app_state`
- `article`
- `contacts`
- `forms`
- `technologies`
- `api_payloads`
- `requests`

You can pass:

- one view as a string
- multiple views as a list

### `discover_site`

Site-level discovery tool.

Good for:

- mapping a site
- bounded crawling
- feed discovery
- site-level technology aggregation

Important inputs:

- `url`
- `strategy="map" | "crawl" | "feeds" | "technologies"`
- `query`
- `max_pages`
- `max_depth`
- `browser`
- `respect_robots_txt`
- `headless`

### `extract_structured`

Focused structured extraction tool.

Good for:

- extracting known fields from a known page shape

Important inputs:

- `url`
- `schema`
- `mode`
- `headless`

Schema style:

- CSS selector based
- not a generic JSON output schema

Use the extract schema guide resource when needed.

### `capture_screenshot`

Visual verification tool.

Good for:

- checking rendered state
- verifying consent handling
- confirming layout

Important inputs:

- `url`
- `full_page`
- `width`
- `height`
- `headless`

## Resources And Prompts

### Guide Resources

Use guide resources when an agent needs instructions without spending more tool schema budget.

Examples:

- overview of the MCP surface
- workflow guidance
- extract schema guidance

### Technology Catalog Templates

These replace extra lookup tools.

Use:

- `crawl://catalog/technology-search/{query}`
- `crawl://catalog/technology/{name}`

### Workflow Prompts

Use:

- `research_workflow`
- `extraction_workflow`

These give a recommended tool sequence for common agent tasks.

## MCP Defaults

Default MCP behavior is defined in `src/crawl/mcp/config.py`.

Current defaults:

- cache enabled
- cache TTL `900`
- cache revalidation enabled
- browser consent mode `auto`
- browser resource mode `safe`
- browser headless `false`

Agents can still override relevant fields per call.

## Validation Notes

The current MCP server has been validated for:

- tool discovery
- resource discovery
- prompt discovery
- stdio client calls
- browser-capable calls with explicit `headless=True`

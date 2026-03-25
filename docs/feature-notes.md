# Feature Notes

## Browser Runtime

The browser runtime is built on `nodriver`.

Key behaviors:

- optional headless launch control
- optional persistent browser profile through `session_dir`
- consent handling
- resource blocking
- request capture
- API payload capture
- screenshot capture

## Consent Handling

Browser-capable paths can automatically:

- detect common consent banners
- click reject, accept, or close actions
- handle some iframe-hosted consent prompts
- remove stubborn overlay gates

Relevant controls:

- `consent_mode`
- `max_consent_actions`

## Resource Blocking

Resource blocking can reduce browser noise and speed up some page loads.

Presets:

- `none`
- `safe`
- `aggressive`

Additional controls:

- `blocked_resource_types`
- `blocked_url_patterns`
- `bypass_service_worker`

## Cookies

The project supports:

- HTTP cookie seeding
- browser cookie seeding
- cookie export in supported result paths

Persistent browser sessions are opt-in only.

## Headless

The SDK and MCP support `headless`.

Current state:

- SDK: supported across browser-capable public APIs
- MCP: supported across browser-capable tools with default `false`
- CLI: not currently exposed as a flag

## Caching

The cache is SQLite-backed.

Key behaviors:

- keyed by URL and mode
- optional TTL
- optional stale-cache revalidation using response headers

Default cache location:

- `.crawl_cache/cache.sqlite3`

## Crawl State

Longer crawls can persist and resume state through `state_path`.

Stored state includes:

- frontier
- visited URLs
- current results
- budget state
- autoscale snapshots

## Datasets

Datasets are JSONL-backed.

Helpers:

- append rows
- reload rows
- export as JSON
- export as JSONL
- export as CSV

Default dataset directory:

- `storage/datasets`

## Technology Fingerprinting

Technology detection combines:

- bundled technology definitions
- imported plugin signatures
- passive header, cookie, meta, URL, and script checks
- optional stronger HTML-body matching through aggression levels

Technology helper paths:

- `tech`
- `tech_grep`
- `tech-list`
- `tech-info`
- `tech-update`
- `tech-import`

## Search Providers

Available search modes:

- `google`
- `searxng`
- `auto`
- `hybrid`

`auto` prefers SearXNG first and falls back to Google.

## Runtime Libraries

HTTP:

- `curl_cffi`

Browser:

- `nodriver`

Other notable runtime dependencies:

- `beautifulsoup4`
- `fastmcp`
- `pillow`
- `psutil`

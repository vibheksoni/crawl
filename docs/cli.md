# CLI Guide

## Entry Points

From the repo root:

```powershell
python cli.py --help
```

Installed script:

```powershell
crawl-cli --help
```

## Command Groups

Search and research:

- `websearch`
- `research`

Page reading and extraction:

- `fetch`
- `fetch-page`
- `scrape`
- `batch-scrape`
- `query`
- `extract`
- `forms`
- `article`
- `feeds`
- `contacts`

Site traversal:

- `map`
- `crawl`
- `benchmark`

Technology and utilities:

- `tech`
- `tech-grep`
- `tech-list`
- `tech-info`
- `tech-update`
- `tech-import`
- `normalize-url`
- `dataset-export`
- `screenshot`

## Common CLI Patterns

### Search

```powershell
python cli.py websearch "python async browser automation" --provider auto --max-results 5 --pages 1
python cli.py research "python async browser automation" --provider searxng --searxng-url http://127.0.0.1:8888 --research-limit 3
```

### Single Page Reading

```powershell
python cli.py fetch https://example.com --format text --mode auto
python cli.py scrape https://www.python.org --format markdown --format metadata --mode auto
python cli.py fetch-page https://example.com --mode http --include-html --include-headers
python cli.py query https://www.python.org "asyncio"
```

### Structured Extraction

```powershell
python cli.py extract https://www.python.org/events/python-events/ --schema-file .\schema.json
python cli.py forms https://httpbin.org/forms/post --fill-preview
python cli.py article https://blog.python.org/2026/03/the-python-insider-blog-has-moved/ --follow-pagination --max-pages 3
python cli.py feeds https://www.python.org/blogs/ --spider-depth 1 --max-feeds 5
python cli.py contacts https://www.python.org
```

### Site Discovery

```powershell
python cli.py map https://docs.python.org/3/tutorial/ --search interpreter --limit 5
python cli.py crawl https://docs.python.org/3/tutorial/ --mode fast --max-pages 25 --max-depth 2
python cli.py benchmark https://docs.python.org/3/tutorial/ --max-pages 12 --samples 3 --concurrency 1 2 4
```

### Technology Utilities

```powershell
python cli.py tech https://nextjs.org --mode http --aggression 1
python cli.py tech-grep https://nextjs.org --text next.js --search headers[x-powered-by]
python cli.py tech-list --search next --limit 10
python cli.py tech-info Next.js
python cli.py tech-update
python cli.py tech-import C:\path\to\plugins --output-file .\plugin-signatures.json
```

### Persistence And Export

```powershell
python cli.py crawl https://docs.python.org/3/tutorial/ --state-path .\crawl-state.json
python cli.py crawl https://docs.python.org/3/tutorial/ --dataset-dir .\storage\datasets --dataset-name crawl-results
python cli.py dataset-export crawl-results --dataset-dir .\storage\datasets --format csv
python cli.py normalize-url "https://example.com/article?utm_source=demo&a=1#frag"
python cli.py screenshot https://example.com --output .\example.jpg
```

## Shared Option Families

### Network Options

Many commands support:

- `--user-agent`
- `--header`
- `--accept-invalid-certs`
- `--proxy-url`
- `--max-retries`
- `--retry-backoff-ms`

### Cache Options

Many commands support:

- `--cache`
- `--cache-dir`
- `--cache-ttl`
- `--cache-revalidate`

### Browser Controls

Many browser-capable commands support:

- `--consent-mode`
- `--max-consent-actions`
- `--resource-mode`
- `--block-resource-type`
- `--block-url-pattern`
- `--bypass-service-worker`
- `--cookie`
- `--cookie-file`

Some structured browser commands also support:

- `--interaction-mode`
- `--max-interactions`
- `--session-dir`
- `--include-requests`
- `--include-api-payloads`

Current note:

- the SDK and MCP support `headless`
- the CLI does not currently expose a `--headless` flag

## Output Controls

Shared output helpers exist on many commands:

- `--jsonl`
- `--field`
- `--output-template`
- `--output-file`
- `--store-field`
- `--store-dir`
- `--dataset-dir`
- `--dataset-name`

These are useful for:

- selecting a small subset of fields
- rendering custom lines
- storing extracted values to disk
- persisting result rows to datasets

## Notes

- `websearch` defaults to `provider=auto`
- `tech-import --output-file` writes the generated signature JSON file
- `fetch-page` is the most detailed CLI command for page-level inspection
- `crawl` is the broadest traversal command and exposes the most tuning knobs

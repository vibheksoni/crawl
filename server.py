"""Repository root entrypoint for the MCP server."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from crawl import batch_scrape, crawl, extract, fetch, fetch_page, forms, map_site, query_page, scrape, screenshot, websearch
from crawl.mcp import mcp, run

__all__ = ["batch_scrape", "crawl", "extract", "fetch", "fetch_page", "forms", "map_site", "mcp", "query_page", "run", "scrape", "screenshot", "websearch"]


if __name__ == "__main__":
    run()

"""Repository root entrypoint for the MCP server."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from crawl.mcp import mcp, run

__all__ = ["mcp", "run"]


if __name__ == "__main__":
    run()

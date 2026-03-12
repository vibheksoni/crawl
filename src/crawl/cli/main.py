"""Command-line interface for the crawl SDK."""

import argparse
import asyncio
import json
from pathlib import Path

from crawl.sdk import crawl, fetch, screenshot, websearch


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description="Run crawl tools directly from the CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("websearch", help="Run the websearch command.")
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument("--max-results", type=int, default=10, dest="max_results")
    search_parser.add_argument("--pages", type=int, default=1)

    fetch_parser = subparsers.add_parser("fetch", help="Run the fetch command.")
    fetch_parser.add_argument("url", help="Page URL.")
    fetch_parser.add_argument("--format", choices=["markdown", "text"], default="markdown", dest="output_format")

    crawl_parser = subparsers.add_parser("crawl", help="Run the crawl command.")
    crawl_parser.add_argument("url", help="Start URL.")
    crawl_parser.add_argument("--max-pages", type=int, default=10, dest="max_pages")
    crawl_parser.add_argument("--mode", choices=["fast", "auto"], default="auto")

    screenshot_parser = subparsers.add_parser("screenshot", help="Run the screenshot command.")
    screenshot_parser.add_argument("url", help="Page URL.")
    screenshot_parser.add_argument("--width", type=int, default=-1)
    screenshot_parser.add_argument("--height", type=int, default=-1)
    screenshot_parser.add_argument("--no-full-page", action="store_true", dest="no_full_page")
    screenshot_parser.add_argument("--output", default="screenshot.jpg", help="Output image path.")

    return parser


async def run_command(args: argparse.Namespace):
    """Dispatch a parsed CLI command to the corresponding SDK function.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Command result object or string.
    """
    if args.command == "websearch":
        return await websearch(args.query, max_results=args.max_results, pages=args.pages)

    if args.command == "fetch":
        return await fetch(args.url, output_format=args.output_format)

    if args.command == "crawl":
        return await crawl(args.url, max_pages=args.max_pages, mode=args.mode)

    if args.command == "screenshot":
        return await screenshot(
            args.url,
            width=args.width,
            height=args.height,
            full_page=not args.no_full_page,
        )

    raise ValueError(f"Unsupported command: {args.command}")


def main() -> int:
    """Run the CLI entrypoint.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = asyncio.run(run_command(args))
    except Exception as error:
        print(json.dumps({"error": str(error)}, indent=2, ensure_ascii=False))
        return 1

    if args.command == "screenshot":
        output_path = Path(args.output)
        output_path.write_bytes(result)
        print(str(output_path.resolve()))
        return 0

    if isinstance(result, str):
        print(result)
        return 0

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

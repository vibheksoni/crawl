"""Command-line interface for the crawl SDK."""

import argparse
import asyncio
import json
import re
from pathlib import Path

from crawl.cli.output import normalize_output_rows, render_template, render_template_details, select_fields, store_selected_fields
from crawl.sdk import batch_scrape, benchmark_fast_crawl, contacts, crawl, extract, fetch, fetch_page, forms, map_site, query_page, scrape, screenshot, websearch


def parse_budget_entries(entries: list[str] | None) -> dict[str, int] | None:
    """Parse CLI budget entries into a budget mapping.

    Args:
        entries: Budget entries in ``pattern=limit`` form.

    Returns:
        Budget mapping or ``None``.
    """
    if not entries:
        return None

    budget = {}
    for entry in entries:
        key, separator, value = entry.partition("=")
        if not separator:
            raise ValueError(f"Invalid budget entry: {entry}")
        budget[key.strip()] = int(value.strip())
    return budget


def parse_header_entries(entries: list[str] | None) -> dict[str, str] | None:
    """Parse CLI header entries into a header mapping.

    Args:
        entries: Header entries in ``Key: Value`` or ``key=value`` form.

    Returns:
        Header mapping or ``None``.
    """
    if not entries:
        return None

    headers = {}
    for entry in entries:
        if ":" in entry:
            key, value = entry.split(":", 1)
        else:
            key, separator, value = entry.partition("=")
            if not separator:
                raise ValueError(f"Invalid header entry: {entry}")
        headers[key.strip()] = value.strip()
    return headers


def load_json_file(path: str) -> dict:
    """Load a JSON file from disk.

    Args:
        path: JSON file path.

    Returns:
        Parsed JSON object.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def add_common_output_options(parser: argparse.ArgumentParser) -> None:
    """Add shared output formatting options to a CLI parser.

    Args:
        parser: Target subparser.
    """
    parser.add_argument("--jsonl", action="store_true", dest="jsonl")
    parser.add_argument("--field", action="append", dest="output_fields")
    parser.add_argument("--output-template", dest="output_template")
    parser.add_argument("--output-file", dest="output_file")
    parser.add_argument("--store-field", action="append", dest="store_fields")
    parser.add_argument("--store-dir", dest="store_dir")


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
    search_parser.add_argument("--provider", choices=["google", "searxng", "auto", "hybrid"], default="google")
    search_parser.add_argument("--searxng-url", dest="searxng_url")
    search_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    search_parser.add_argument("--scrape-results", action="store_true", dest="scrape_results")
    search_parser.add_argument("--scrape-limit", type=int, default=3, dest="scrape_limit")
    search_parser.add_argument(
        "--scrape-format",
        choices=["markdown", "text", "html", "links", "metadata", "app_state", "contacts"],
        action="append",
        dest="scrape_formats",
    )
    search_parser.add_argument("--only-main-content", action="store_true", dest="only_main_content")
    search_parser.add_argument("--include-full-page", action="store_false", dest="only_main_content")
    search_parser.set_defaults(only_main_content=True)
    search_parser.add_argument("--cache", action="store_true", dest="cache")
    search_parser.add_argument("--cache-dir", dest="cache_dir")
    search_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    search_parser.add_argument("--user-agent", dest="user_agent")
    search_parser.add_argument("--header", action="append", dest="header_entries")
    search_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    search_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    search_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(search_parser)

    fetch_parser = subparsers.add_parser("fetch", help="Run the fetch command.")
    fetch_parser.add_argument("url", help="Page URL.")
    fetch_parser.add_argument("--format", choices=["markdown", "text"], default="markdown", dest="output_format")
    fetch_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    fetch_parser.add_argument("--cache", action="store_true", dest="cache")
    fetch_parser.add_argument("--cache-dir", dest="cache_dir")
    fetch_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    fetch_parser.add_argument("--user-agent", dest="user_agent")
    fetch_parser.add_argument("--header", action="append", dest="header_entries")
    fetch_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    fetch_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    fetch_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    fetch_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(fetch_parser)

    scrape_parser = subparsers.add_parser("scrape", help="Run the multi-format scrape command.")
    scrape_parser.add_argument("url", help="Page URL.")
    scrape_parser.add_argument(
        "--format",
        choices=["markdown", "text", "html", "links", "metadata", "fit_markdown", "app_state", "contacts"],
        action="append",
        dest="formats",
    )
    scrape_parser.add_argument("--only-main-content", action="store_true", dest="only_main_content")
    scrape_parser.add_argument("--include-full-page", action="store_false", dest="only_main_content")
    scrape_parser.set_defaults(only_main_content=True)
    scrape_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    scrape_parser.add_argument("--cache", action="store_true", dest="cache")
    scrape_parser.add_argument("--cache-dir", dest="cache_dir")
    scrape_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    scrape_parser.add_argument("--user-agent", dest="user_agent")
    scrape_parser.add_argument("--header", action="append", dest="header_entries")
    scrape_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    scrape_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    scrape_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    scrape_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(scrape_parser)

    batch_scrape_parser = subparsers.add_parser("batch-scrape", help="Run the multi-URL scrape command.")
    batch_scrape_parser.add_argument("urls", nargs="+", help="URL list.")
    batch_scrape_parser.add_argument(
        "--format",
        choices=["markdown", "text", "html", "links", "metadata", "fit_markdown", "app_state", "contacts"],
        action="append",
        dest="formats",
    )
    batch_scrape_parser.add_argument("--only-main-content", action="store_true", dest="only_main_content")
    batch_scrape_parser.add_argument("--include-full-page", action="store_false", dest="only_main_content")
    batch_scrape_parser.set_defaults(only_main_content=True)
    batch_scrape_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    batch_scrape_parser.add_argument("--max-concurrency", type=int, default=4, dest="max_concurrency")
    batch_scrape_parser.add_argument("--cache", action="store_true", dest="cache")
    batch_scrape_parser.add_argument("--cache-dir", dest="cache_dir")
    batch_scrape_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    batch_scrape_parser.add_argument("--user-agent", dest="user_agent")
    batch_scrape_parser.add_argument("--header", action="append", dest="header_entries")
    batch_scrape_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    batch_scrape_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    batch_scrape_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    batch_scrape_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(batch_scrape_parser)

    map_parser = subparsers.add_parser("map", help="Discover URLs within a site.")
    map_parser.add_argument("url", help="Start URL.")
    map_parser.add_argument("--search", dest="search")
    map_parser.add_argument("--limit", type=int, default=100)
    map_parser.add_argument("--mode", choices=["fast", "auto"], default="fast")
    map_parser.add_argument("--allow-subdomains", action="store_true", dest="allow_subdomains")
    map_parser.add_argument("--allow-domain", action="append", dest="allowed_domains")
    map_parser.add_argument("--include-pattern", action="append", dest="include_patterns")
    map_parser.add_argument("--exclude-pattern", action="append", dest="exclude_patterns")
    map_parser.add_argument("--pattern-mode", choices=["auto", "substring", "regex", "glob"], default="auto")
    map_parser.add_argument("--respect-robots-txt", action="store_true", dest="respect_robots_txt")
    map_parser.add_argument("--sitemap-url", dest="sitemap_url")
    map_parser.add_argument("--seed-sitemap", action="store_true", dest="seed_sitemap")
    map_parser.add_argument("--user-agent", default="*", dest="user_agent")
    map_parser.add_argument("--cache", action="store_true", dest="cache")
    map_parser.add_argument("--cache-dir", dest="cache_dir")
    map_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    map_parser.add_argument("--header", action="append", dest="header_entries")
    map_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    map_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    map_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    map_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    map_parser.add_argument("--state-path", dest="state_path")
    add_common_output_options(map_parser)

    extract_parser = subparsers.add_parser("extract", help="Run selector-based structured extraction.")
    extract_parser.add_argument("url", help="Page URL.")
    extract_parser.add_argument("--schema-file", required=True, dest="schema_file")
    extract_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    extract_parser.add_argument("--cache", action="store_true", dest="cache")
    extract_parser.add_argument("--cache-dir", dest="cache_dir")
    extract_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    extract_parser.add_argument("--user-agent", dest="user_agent")
    extract_parser.add_argument("--header", action="append", dest="header_entries")
    extract_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    extract_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    extract_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    extract_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(extract_parser)

    forms_parser = subparsers.add_parser("forms", help="Extract forms from a page.")
    forms_parser.add_argument("url", help="Page URL.")
    forms_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    forms_parser.add_argument("--cache", action="store_true", dest="cache")
    forms_parser.add_argument("--cache-dir", dest="cache_dir")
    forms_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    forms_parser.add_argument("--user-agent", dest="user_agent")
    forms_parser.add_argument("--header", action="append", dest="header_entries")
    forms_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    forms_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    forms_parser.add_argument("--fill-preview", action="store_true", dest="include_fill_suggestions")
    forms_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    forms_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(forms_parser)

    contacts_parser = subparsers.add_parser("contacts", help="Extract contact details and social links from a page.")
    contacts_parser.add_argument("url", help="Page URL.")
    contacts_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    contacts_parser.add_argument("--cache", action="store_true", dest="cache")
    contacts_parser.add_argument("--cache-dir", dest="cache_dir")
    contacts_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    contacts_parser.add_argument("--user-agent", dest="user_agent")
    contacts_parser.add_argument("--header", action="append", dest="header_entries")
    contacts_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    contacts_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    contacts_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    contacts_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(contacts_parser)

    query_parser = subparsers.add_parser("query", help="Extract query-relevant content from a page.")
    query_parser.add_argument("url", help="Page URL.")
    query_parser.add_argument("query", help="Relevance query.")
    query_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    query_parser.add_argument("--cache", action="store_true", dest="cache")
    query_parser.add_argument("--cache-dir", dest="cache_dir")
    query_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    query_parser.add_argument("--user-agent", dest="user_agent")
    query_parser.add_argument("--header", action="append", dest="header_entries")
    query_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    query_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    query_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    query_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    add_common_output_options(query_parser)

    fetch_page_parser = subparsers.add_parser("fetch-page", help="Run the structured page fetch command.")
    fetch_page_parser.add_argument("url", help="Page URL.")
    fetch_page_parser.add_argument("--mode", choices=["auto", "http", "browser"], default="auto")
    fetch_page_parser.add_argument("--allow-subdomains", action="store_true", dest="allow_subdomains")
    fetch_page_parser.add_argument("--allow-domain", action="append", dest="allowed_domains")
    fetch_page_parser.add_argument("--include-pattern", action="append", dest="include_patterns")
    fetch_page_parser.add_argument("--exclude-pattern", action="append", dest="exclude_patterns")
    fetch_page_parser.add_argument("--pattern-mode", choices=["auto", "substring", "regex", "glob"], default="auto")
    fetch_page_parser.add_argument("--full-resources", action="store_true", dest="full_resources")
    fetch_page_parser.add_argument("--include-requests", action="store_true", dest="include_requests")
    fetch_page_parser.add_argument("--interaction-mode", choices=["none", "auto"], default="none")
    fetch_page_parser.add_argument("--max-interactions", type=int, default=3, dest="max_interactions")
    fetch_page_parser.add_argument("--session-dir", dest="session_dir")
    fetch_page_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    fetch_page_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    fetch_page_parser.add_argument("--include-headers", action="store_true", dest="include_headers")
    fetch_page_parser.add_argument("--include-html", action="store_true", dest="include_html")
    fetch_page_parser.add_argument("--include-app-state", action="store_true", dest="include_app_state")
    fetch_page_parser.add_argument("--include-contacts", action="store_true", dest="include_contacts")
    fetch_page_parser.add_argument("--cache", action="store_true", dest="cache")
    fetch_page_parser.add_argument("--cache-dir", dest="cache_dir")
    fetch_page_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    fetch_page_parser.add_argument("--user-agent", dest="user_agent")
    fetch_page_parser.add_argument("--header", action="append", dest="header_entries")
    fetch_page_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    fetch_page_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    add_common_output_options(fetch_page_parser)

    crawl_parser = subparsers.add_parser("crawl", help="Run the crawl command.")
    crawl_parser.add_argument("url", help="Start URL.")
    crawl_parser.add_argument("--max-pages", type=int, default=10, dest="max_pages")
    crawl_parser.add_argument("--mode", choices=["fast", "auto", "browser"], default="auto")
    crawl_parser.add_argument("--crawl-strategy", choices=["bfs", "best_first"], default="bfs")
    crawl_parser.add_argument("--crawl-query", dest="crawl_query")
    crawl_parser.add_argument("--max-concurrency", type=int, default=4, dest="max_concurrency")
    crawl_parser.add_argument("--max-depth", type=int, default=2, dest="max_depth")
    crawl_parser.add_argument("--allow-subdomains", action="store_true", dest="allow_subdomains")
    crawl_parser.add_argument("--allow-domain", action="append", dest="allowed_domains")
    crawl_parser.add_argument("--include-pattern", action="append", dest="include_patterns")
    crawl_parser.add_argument("--exclude-pattern", action="append", dest="exclude_patterns")
    crawl_parser.add_argument("--pattern-mode", choices=["auto", "substring", "regex", "glob"], default="auto")
    crawl_parser.add_argument("--full-resources", action="store_true", dest="full_resources")
    crawl_parser.add_argument("--dedupe-by-signature", action="store_true", dest="dedupe_by_signature")
    crawl_parser.add_argument("--include-requests", action="store_true", dest="include_requests")
    crawl_parser.add_argument("--interaction-mode", choices=["none", "auto"], default="none")
    crawl_parser.add_argument("--max-interactions", type=int, default=3, dest="max_interactions")
    crawl_parser.add_argument("--session-dir", dest="session_dir")
    crawl_parser.add_argument("--max-retries", type=int, default=2, dest="max_retries")
    crawl_parser.add_argument("--retry-backoff-ms", type=int, default=500, dest="retry_backoff_ms")
    crawl_parser.add_argument("--auto-throttle", action="store_true", dest="auto_throttle")
    crawl_parser.add_argument("--minimum-delay-ms", type=int, default=0, dest="minimum_delay_ms")
    crawl_parser.add_argument("--maximum-delay-ms", type=int, default=5000, dest="maximum_delay_ms")
    crawl_parser.add_argument("--include-headers", action="store_true", dest="include_headers")
    crawl_parser.add_argument("--respect-robots-txt", action="store_true", dest="respect_robots_txt")
    crawl_parser.add_argument("--sitemap-url", dest="sitemap_url")
    crawl_parser.add_argument("--seed-sitemap", action="store_true", dest="seed_sitemap")
    crawl_parser.add_argument("--user-agent", default="*", dest="user_agent")
    crawl_parser.add_argument("--budget", action="append", dest="budget_entries")
    crawl_parser.add_argument("--delay-ms", type=int, default=0, dest="delay_ms")
    crawl_parser.add_argument("--path-delay", action="append", dest="path_delay_entries")
    crawl_parser.add_argument("--cache", action="store_true", dest="cache")
    crawl_parser.add_argument("--cache-dir", dest="cache_dir")
    crawl_parser.add_argument("--cache-ttl", type=int, dest="cache_ttl_seconds")
    crawl_parser.add_argument("--state-path", dest="state_path")
    crawl_parser.add_argument("--header", action="append", dest="header_entries")
    crawl_parser.add_argument("--accept-invalid-certs", action="store_true", dest="accept_invalid_certs")
    crawl_parser.add_argument("--proxy-url", action="append", dest="proxy_urls")
    add_common_output_options(crawl_parser)

    screenshot_parser = subparsers.add_parser("screenshot", help="Run the screenshot command.")
    screenshot_parser.add_argument("url", help="Page URL.")
    screenshot_parser.add_argument("--width", type=int, default=-1)
    screenshot_parser.add_argument("--height", type=int, default=-1)
    screenshot_parser.add_argument("--no-full-page", action="store_true", dest="no_full_page")
    screenshot_parser.add_argument("--output", default="screenshot.jpg", help="Output image path.")

    benchmark_parser = subparsers.add_parser("benchmark", help="Benchmark the HTTP-only crawler.")
    benchmark_parser.add_argument("url", help="Start URL.")
    benchmark_parser.add_argument("--max-pages", type=int, default=10, dest="max_pages")
    benchmark_parser.add_argument("--samples", type=int, default=3)
    benchmark_parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[1, 2, 4],
        dest="concurrency_levels",
    )

    return parser


async def run_command(args: argparse.Namespace):
    """Dispatch a parsed CLI command to the corresponding SDK function.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Command result object or string.
    """
    if args.command == "websearch":
        provider = args.provider
        if args.searxng_url and provider == "google":
            provider = "searxng"
        return await websearch(
            args.query,
            max_results=args.max_results,
            pages=args.pages,
            provider=provider,
            searxng_url=args.searxng_url,
            proxy_urls=args.proxy_urls,
            scrape_results=args.scrape_results,
            scrape_limit=args.scrape_limit,
            scrape_formats=args.scrape_formats,
            only_main_content=args.only_main_content,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "fetch":
        return await fetch(
            args.url,
            output_format=args.output_format,
            mode=args.mode,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
            state_path=args.state_path,
        )

    if args.command == "scrape":
        return await scrape(
            args.url,
            formats=args.formats,
            only_main_content=args.only_main_content,
            mode=args.mode,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "query":
        return await query_page(
            args.url,
            args.query,
            mode=args.mode,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "batch-scrape":
        return await batch_scrape(
            args.urls,
            formats=args.formats,
            only_main_content=args.only_main_content,
            mode=args.mode,
            max_concurrency=args.max_concurrency,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "map":
        return await map_site(
            args.url,
            search=args.search,
            limit=args.limit,
            mode=args.mode,
            allow_subdomains=args.allow_subdomains,
            allowed_domains=args.allowed_domains,
            include_patterns=args.include_patterns,
            exclude_patterns=args.exclude_patterns,
            pattern_mode=args.pattern_mode,
            respect_robots_txt=args.respect_robots_txt,
            sitemap_url=args.sitemap_url,
            seed_sitemap=args.seed_sitemap,
            user_agent=args.user_agent,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "extract":
        return await extract(
            args.url,
            schema=load_json_file(args.schema_file),
            mode=args.mode,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "forms":
        return await forms(
            args.url,
            mode=args.mode,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            include_fill_suggestions=args.include_fill_suggestions,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "contacts":
        return await contacts(
            args.url,
            mode=args.mode,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
        )

    if args.command == "fetch-page":
        return await fetch_page(
            args.url,
            mode=args.mode,
            allow_subdomains=args.allow_subdomains,
            allowed_domains=args.allowed_domains,
            include_patterns=args.include_patterns,
            exclude_patterns=args.exclude_patterns,
            pattern_mode=args.pattern_mode,
            full_resources=args.full_resources,
            include_requests=args.include_requests,
            interaction_mode=args.interaction_mode,
            max_interactions=args.max_interactions,
            session_dir=args.session_dir,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
            include_headers=args.include_headers,
            include_html=args.include_html,
            include_app_state=args.include_app_state,
            include_contacts=args.include_contacts,
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            user_agent=args.user_agent,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
        )

    if args.command == "crawl":
        return await crawl(
            args.url,
            max_pages=args.max_pages,
            mode=args.mode,
            crawl_strategy=args.crawl_strategy,
            crawl_query=args.crawl_query,
            max_concurrency=args.max_concurrency,
            max_depth=args.max_depth,
            allow_subdomains=args.allow_subdomains,
            allowed_domains=args.allowed_domains,
            include_patterns=args.include_patterns,
            exclude_patterns=args.exclude_patterns,
            pattern_mode=args.pattern_mode,
            full_resources=args.full_resources,
            dedupe_by_signature=args.dedupe_by_signature,
            include_requests=args.include_requests,
            interaction_mode=args.interaction_mode,
            max_interactions=args.max_interactions,
            session_dir=args.session_dir,
            max_retries=args.max_retries,
            retry_backoff_ms=args.retry_backoff_ms,
            auto_throttle=args.auto_throttle,
            minimum_delay_ms=args.minimum_delay_ms,
            maximum_delay_ms=args.maximum_delay_ms,
            include_headers=args.include_headers,
            respect_robots_txt=args.respect_robots_txt,
            sitemap_url=args.sitemap_url,
            seed_sitemap=args.seed_sitemap,
            user_agent=args.user_agent,
            budget=parse_budget_entries(args.budget_entries),
            delay_ms=args.delay_ms,
            path_delays=parse_budget_entries(args.path_delay_entries),
            cache=args.cache,
            cache_dir=args.cache_dir,
            cache_ttl_seconds=args.cache_ttl_seconds,
            state_path=args.state_path,
            headers=parse_header_entries(args.header_entries),
            accept_invalid_certs=args.accept_invalid_certs,
            proxy_urls=args.proxy_urls,
        )

    if args.command == "screenshot":
        return await screenshot(
            args.url,
            width=args.width,
            height=args.height,
            full_page=not args.no_full_page,
        )

    if args.command == "benchmark":
        return await benchmark_fast_crawl(
            args.url,
            max_pages=args.max_pages,
            concurrency_levels=args.concurrency_levels,
            samples=args.samples,
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
        output_text = result
        if args.output_file:
            Path(args.output_file).write_text(output_text, encoding="utf-8")
        print(output_text)
        return 0

    if args.store_fields:
        store_selected_fields(result, args.store_fields, store_dir=args.store_dir)

    if args.output_template:
        template_fields = len(re.findall(r"\{\{\s*([^}]+?)\s*\}\}", args.output_template))
        if isinstance(result, dict):
            rendered_result, resolved_fields = render_template_details(result, args.output_template)
        else:
            rendered_result, resolved_fields = "", 0

        if template_fields > 0 and resolved_fields == template_fields:
            rendered = rendered_result
        else:
            rows = normalize_output_rows(result)
            rendered_rows = []
            for row in rows:
                rendered_row, row_resolved_fields = render_template_details(row, args.output_template)
                if row_resolved_fields > 0:
                    rendered_rows.append(rendered_row)
            rendered = "\n".join(rendered_rows)
        if args.output_file:
            Path(args.output_file).write_text(rendered, encoding="utf-8")
        print(rendered)
        return 0

    if args.output_fields:
        rows = normalize_output_rows(result)
        selected_rows = [select_fields(row, args.output_fields) for row in rows]
        output_data = selected_rows if len(selected_rows) != 1 else selected_rows[0]
    else:
        output_data = result

    if args.jsonl:
        rows = normalize_output_rows(output_data if isinstance(output_data, dict) else {"data": output_data})
        rendered = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    else:
        rendered = json.dumps(output_data, indent=2, ensure_ascii=False)

    if args.output_file:
        Path(args.output_file).write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

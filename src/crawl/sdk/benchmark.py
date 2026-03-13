"""Benchmark helpers for non-browser crawl paths."""

import statistics
import time

from .api import crawl


async def benchmark_fast_crawl(
    url: str,
    max_pages: int = 10,
    concurrency_levels: list[int] | None = None,
    samples: int = 3,
    dedupe_by_similarity: bool = False,
    similarity_threshold: int = 3,
    cache_revalidate: bool = False,
) -> dict:
    """Benchmark the HTTP-only crawler at multiple concurrency levels.

    Args:
        url: Starting URL to crawl.
        max_pages: Maximum pages to crawl per run.
        concurrency_levels: Concurrency levels to compare.
        samples: Number of benchmark samples per setting.
        dedupe_by_similarity: Whether to suppress near-duplicate page expansion.
        similarity_threshold: Maximum simhash distance for near-duplicate detection.
        cache_revalidate: Whether stale cache entries should be conditionally revalidated.

    Returns:
        Benchmark summary with per-setting timing statistics.
    """
    levels = concurrency_levels or [1, 2, 4]
    levels = [max(1, level) for level in levels]
    samples = max(1, samples)
    results = []

    for concurrency in levels:
        durations = []
        page_counts = []
        error_counts = []
        near_duplicate_counts = []

        for _ in range(samples):
            started_at = time.perf_counter()
            crawl_result = await crawl(
                url=url,
                max_pages=max_pages,
                mode="fast",
                max_concurrency=concurrency,
                dedupe_by_similarity=dedupe_by_similarity,
                similarity_threshold=similarity_threshold,
                cache_revalidate=cache_revalidate,
            )
            duration = time.perf_counter() - started_at

            durations.append(duration)
            page_counts.append(crawl_result["pages_crawled"])
            error_counts.append(sum(1 for item in crawl_result["results"] if "error" in item))
            near_duplicate_counts.append(crawl_result.get("near_duplicate_count", 0))

        results.append(
            {
                "max_concurrency": concurrency,
                "samples": samples,
                "avg_seconds": round(statistics.fmean(durations), 4),
                "min_seconds": round(min(durations), 4),
                "max_seconds": round(max(durations), 4),
                "median_seconds": round(statistics.median(durations), 4),
                "avg_pages_crawled": round(statistics.fmean(page_counts), 2),
                "avg_errors": round(statistics.fmean(error_counts), 2),
                "avg_near_duplicates": round(statistics.fmean(near_duplicate_counts), 2),
            }
        )

    return {
        "url": url,
        "max_pages": max_pages,
        "samples": samples,
        "dedupe_by_similarity": dedupe_by_similarity,
        "similarity_threshold": similarity_threshold,
        "cache_revalidate": cache_revalidate,
        "results": results,
    }

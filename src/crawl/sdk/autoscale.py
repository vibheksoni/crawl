"""Autoscaled concurrency helpers."""

from __future__ import annotations

import psutil


def sample_system_load() -> dict[str, float]:
    """Sample current CPU and memory pressure.

    Returns:
        System load snapshot.
    """
    return {
        "cpu_percent": float(psutil.cpu_percent(interval=None)),
        "memory_percent": float(psutil.virtual_memory().percent),
    }


def choose_autoscaled_concurrency(
    current_concurrency: int,
    min_concurrency: int,
    max_concurrency: int,
    cpu_percent: float,
    memory_percent: float,
    cpu_target_percent: float = 75.0,
    memory_target_percent: float = 80.0,
) -> tuple[int, str]:
    """Choose the next crawl concurrency level from load samples.

    Args:
        current_concurrency: Current batch concurrency.
        min_concurrency: Lower concurrency bound.
        max_concurrency: Upper concurrency bound.
        cpu_percent: Observed CPU usage.
        memory_percent: Observed memory usage.
        cpu_target_percent: Preferred CPU ceiling.
        memory_target_percent: Preferred memory ceiling.

    Returns:
        Tuple of next concurrency and a short decision reason.
    """
    minimum = max(1, min_concurrency)
    maximum = max(minimum, max_concurrency)
    current = max(minimum, min(current_concurrency, maximum))

    overload = cpu_percent >= cpu_target_percent + 10 or memory_percent >= memory_target_percent + 10
    underloaded = cpu_percent <= max(5.0, cpu_target_percent - 20) and memory_percent <= max(10.0, memory_target_percent - 20)

    if overload and current > minimum:
        return current - 1, "decrease"
    if underloaded and current < maximum:
        return current + 1, "increase"
    return current, "keep"

"""Persistent crawl state helpers."""

import json
from pathlib import Path


def load_crawl_state(state_path: str | None) -> dict | None:
    """Load a persisted crawl state file when present.

    Args:
        state_path: Optional crawl state file path.

    Returns:
        Parsed crawl state payload or ``None``.
    """
    if not state_path:
        return None

    path = Path(state_path).resolve()
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def save_crawl_state(state_path: str | None, payload: dict) -> None:
    """Persist crawl state atomically.

    Args:
        state_path: Optional crawl state file path.
        payload: Crawl state payload to write.
    """
    if not state_path:
        return

    path = Path(state_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def serialize_frontier(frontier, strategy: str) -> list[dict]:
    """Serialize the current crawl frontier into a JSON-safe list.

    Args:
        frontier: Frontier container.
        strategy: Frontier strategy name.

    Returns:
        Serialized frontier records.
    """
    if strategy == "best_first":
        return [{"url": item[2], "depth": item[3]} for item in frontier]
    return [{"url": item[0], "depth": item[1]} for item in list(frontier)]

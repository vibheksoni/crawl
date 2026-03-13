"""Dataset persistence and export helpers."""

import csv
import json
from io import StringIO
from pathlib import Path


def resolve_dataset_dir(dataset_dir: str | None = None) -> Path:
    """Resolve the dataset root directory.

    Args:
        dataset_dir: Optional dataset root directory.

    Returns:
        Resolved dataset directory path.
    """
    return Path(dataset_dir or "storage/datasets").resolve()


def resolve_dataset_file(dataset_name: str = "default", dataset_dir: str | None = None) -> Path:
    """Resolve the JSONL file backing a dataset.

    Args:
        dataset_name: Dataset name.
        dataset_dir: Optional dataset root directory.

    Returns:
        Dataset JSONL file path.
    """
    root = resolve_dataset_dir(dataset_dir)
    dataset_path = root / dataset_name
    dataset_path.mkdir(parents=True, exist_ok=True)
    return dataset_path / "data.jsonl"


def append_dataset_rows(rows: list[dict], dataset_name: str = "default", dataset_dir: str | None = None) -> str:
    """Append rows to a local dataset JSONL file.

    Args:
        rows: Dataset row payloads.
        dataset_name: Dataset name.
        dataset_dir: Optional dataset root directory.

    Returns:
        Absolute dataset file path.
    """
    dataset_file = resolve_dataset_file(dataset_name=dataset_name, dataset_dir=dataset_dir)
    with dataset_file.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    return str(dataset_file)


def load_dataset_rows(dataset_name: str = "default", dataset_dir: str | None = None) -> list[dict]:
    """Load rows from a local dataset JSONL file.

    Args:
        dataset_name: Dataset name.
        dataset_dir: Optional dataset root directory.

    Returns:
        Loaded dataset rows.
    """
    dataset_file = resolve_dataset_file(dataset_name=dataset_name, dataset_dir=dataset_dir)
    if not dataset_file.exists():
        return []

    rows = []
    for line in dataset_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def flatten_row(row: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested row fields into dotted paths for CSV export.

    Args:
        row: Dataset row.
        prefix: Current field prefix.

    Returns:
        Flattened row mapping.
    """
    flattened = {}
    for key, value in row.items():
        field_name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(flatten_row(value, prefix=field_name))
            continue
        if isinstance(value, list):
            flattened[field_name] = json.dumps(value, ensure_ascii=False)
            continue
        flattened[field_name] = "" if value is None else str(value)
    return flattened


def export_dataset(
    dataset_name: str = "default",
    dataset_dir: str | None = None,
    output_format: str = "json",
    collect_all_keys: bool = True,
) -> str:
    """Export a local dataset into JSON, JSONL, or CSV text.

    Args:
        dataset_name: Dataset name.
        dataset_dir: Optional dataset root directory.
        output_format: ``json``, ``jsonl``, or ``csv``.
        collect_all_keys: Whether CSV export should union keys across all rows.

    Returns:
        Rendered dataset export text.
    """
    rows = load_dataset_rows(dataset_name=dataset_name, dataset_dir=dataset_dir)
    if output_format == "jsonl":
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if output_format == "json":
        return json.dumps(rows, indent=2, ensure_ascii=False)

    flattened_rows = [flatten_row(row) for row in rows]
    fieldnames: list[str] = []
    if collect_all_keys:
        seen = set()
        for row in flattened_rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
    elif flattened_rows:
        fieldnames = list(flattened_rows[0].keys())

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in flattened_rows:
        writer.writerow(row)
    return output.getvalue()

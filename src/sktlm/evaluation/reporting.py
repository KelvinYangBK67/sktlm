"""Machine-readable experiment result-table helpers."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


RESULT_COLUMNS = (
    "run_id",
    "script",
    "spacing",
    "tokenizer",
    "vocab_size",
    "seed",
    "train_segments",
    "test_segments",
    "token_count",
    "occupied_token_types",
    "unk_count",
    "unk_rate",
    "unknown_semantics",
    "bits_per_character",
    "bits_per_byte",
    "bits_per_canonical_unit",
    "dependent_vowel_start_rate",
    "virama_end_rate",
    "grapheme_split_rate",
    "suspect_sandhi_fragment_rate",
)


def normalized_result_row(metrics: dict[str, Any]) -> dict[str, Any]:
    """Project a metrics mapping into the stable paper-facing result schema."""
    return {column: metrics.get(column) for column in RESULT_COLUMNS}


def write_result_table(rows: list[dict[str, Any]], path: Path) -> None:
    """Write JSON or CSV based on suffix, preserving nullable fields."""
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [normalized_result_row(row) for row in rows]
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RESULT_COLUMNS))
        writer.writeheader()
        writer.writerows(normalized)


def collect_metrics(artifact_root: Path) -> list[dict[str, Any]]:
    """Collect metrics.json files from deterministic run directories."""
    rows: list[dict[str, Any]] = []
    for path in sorted(artifact_root.glob("*/metrics.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows

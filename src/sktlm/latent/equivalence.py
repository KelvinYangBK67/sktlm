"""Tolerance-aware scientific equivalence checks for latent run artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


JSON_FILES = ("iteration_metrics.json", "summary.json")
JSONL_FILES = ("analyses.jsonl", "boundary_posteriors.jsonl")
TSV_FILES = ("latent_lexicon.tsv", "rule_usage.tsv")


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _compare(
    left: Any,
    right: Any,
    *,
    path: str,
    mismatches: list[str],
    relative_tolerance: float,
    absolute_tolerance: float,
    limit: int,
) -> None:
    if len(mismatches) >= limit:
        return
    if isinstance(left, bool) or isinstance(right, bool):
        if left != right:
            mismatches.append(f"{path}: {left!r} != {right!r}")
        return
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if not math.isclose(
            float(left),
            float(right),
            rel_tol=relative_tolerance,
            abs_tol=absolute_tolerance,
        ):
            mismatches.append(f"{path}: {left!r} != {right!r}")
        return
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            mismatches.append(
                f"{path}: keys differ: {sorted(left)} != {sorted(right)}"
            )
            return
        for key in left:
            _compare(
                left[key],
                right[key],
                path=f"{path}.{key}",
                mismatches=mismatches,
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
                limit=limit,
            )
        return
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            mismatches.append(f"{path}: lengths differ: {len(left)} != {len(right)}")
            return
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            _compare(
                left_item,
                right_item,
                path=f"{path}[{index}]",
                mismatches=mismatches,
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
                limit=limit,
            )
        return
    if left != right:
        mismatches.append(f"{path}: {left!r} != {right!r}")


def _read_jsonl(path: Path) -> list[Any]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_tsv(path: Path) -> list[dict[str, str | float]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows: list[dict[str, str | float]] = []
        for row in csv.DictReader(handle, delimiter="\t"):
            converted: dict[str, str | float] = {}
            for key, value in row.items():
                number = _number(value)
                converted[key] = value if number is None else number
            rows.append(converted)
        return rows


def compare_runs(
    reference: Path,
    candidate: Path,
    *,
    relative_tolerance: float = 1e-10,
    absolute_tolerance: float = 1e-12,
    mismatch_limit: int = 100,
) -> dict[str, Any]:
    mismatches: list[str] = []
    for name in JSON_FILES:
        _compare(
            json.loads((reference / name).read_text(encoding="utf-8")),
            json.loads((candidate / name).read_text(encoding="utf-8")),
            path=name,
            mismatches=mismatches,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
            limit=mismatch_limit,
        )
    for name in JSONL_FILES:
        _compare(
            _read_jsonl(reference / name),
            _read_jsonl(candidate / name),
            path=name,
            mismatches=mismatches,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
            limit=mismatch_limit,
        )
    for name in TSV_FILES:
        _compare(
            _read_tsv(reference / name),
            _read_tsv(candidate / name),
            path=name,
            mismatches=mismatches,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
            limit=mismatch_limit,
        )
    return {
        "equivalent": not mismatches,
        "relative_tolerance": relative_tolerance,
        "absolute_tolerance": absolute_tolerance,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare exact latent scientific artifacts within tolerance."
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--relative-tolerance", type=float, default=1e-10)
    parser.add_argument("--absolute-tolerance", type=float, default=1e-12)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    result = compare_runs(
        args.reference,
        args.candidate,
        relative_tolerance=args.relative_tolerance,
        absolute_tolerance=args.absolute_tolerance,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="")
    print(payload, end="")
    if not result["equivalent"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

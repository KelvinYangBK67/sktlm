"""Compare canonical S1M2 artifacts under the accepted numeric contract."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CANONICAL_ARTIFACTS = (
    "iteration_metrics.json",
    "piece_inventory.tsv",
    "lexical_diagnostics.tsv",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "rule_usage.tsv",
    "summary.json",
)
ENGINEERING_ONLY_KEYS = frozenset({"lazy_span_traversals"})


@dataclass(slots=True)
class Comparison:
    numeric_values: int = 0
    max_absolute_difference: float = 0.0
    max_relative_difference: float = 0.0


def _maybe_float(value: str) -> str | float:
    try:
        return float(value)
    except ValueError:
        return value


def _load(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [
            [_maybe_float(value) for value in row]
            for row in csv.reader(handle, delimiter="\t")
        ]
    if not rows:
        raise ValueError(f"empty TSV artifact: {path}")
    keyed = {str(row[0]): row[1:] for row in rows[1:]}
    if len(keyed) != len(rows) - 1:
        raise ValueError(f"duplicate first-column identity in {path}")
    return {"header": rows[0], "rows": keyed}


def _compare(
    left: Any,
    right: Any,
    *,
    path: str,
    result: Comparison,
    rtol: float,
    atol: float,
) -> None:
    if isinstance(left, bool) or isinstance(right, bool):
        if left is not right:
            raise AssertionError(f"{path}: {left!r} != {right!r}")
        return
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        left_number = float(left)
        right_number = float(right)
        if not math.isclose(left_number, right_number, rel_tol=rtol, abs_tol=atol):
            raise AssertionError(
                f"{path}: {left_number!r} != {right_number!r} "
                f"under rtol={rtol}, atol={atol}"
            )
        result.numeric_values += 1
        absolute = abs(left_number - right_number)
        result.max_absolute_difference = max(
            result.max_absolute_difference,
            absolute,
        )
        scale = max(abs(left_number), abs(right_number))
        if scale:
            result.max_relative_difference = max(
                result.max_relative_difference,
                absolute / scale,
            )
        return
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            missing = sorted(set(left) ^ set(right))
            raise AssertionError(f"{path}: mapping keys differ: {missing}")
        for key in left:
            if key in ENGINEERING_ONLY_KEYS:
                continue
            _compare(
                left[key],
                right[key],
                path=f"{path}.{key}",
                result=result,
                rtol=rtol,
                atol=atol,
            )
        return
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            raise AssertionError(f"{path}: lengths {len(left)} != {len(right)}")
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            _compare(
                left_item,
                right_item,
                path=f"{path}[{index}]",
                result=result,
                rtol=rtol,
                atol=atol,
            )
        return
    if left != right:
        raise AssertionError(f"{path}: {left!r} != {right!r}")


def compare_artifacts(
    reference: Path,
    candidate: Path,
    *,
    rtol: float = 1e-10,
    atol: float = 1e-12,
) -> dict[str, Any]:
    result = Comparison()
    for name in CANONICAL_ARTIFACTS:
        _compare(
            _load(reference / name),
            _load(candidate / name),
            path=name,
            result=result,
            rtol=rtol,
            atol=atol,
        )
    return {
        "schema_version": "sktlm-s1m2-artifact-comparison/v1",
        "status": "PASS",
        "reference": reference.as_posix(),
        "candidate": candidate.as_posix(),
        "artifacts": list(CANONICAL_ARTIFACTS),
        "excluded_engineering_keys": sorted(ENGINEERING_ONLY_KEYS),
        "numeric_values": result.numeric_values,
        "max_absolute_difference": result.max_absolute_difference,
        "max_relative_difference": result.max_relative_difference,
        "rtol": rtol,
        "atol": atol,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--rtol", type=float, default=1e-10)
    parser.add_argument("--atol", type=float, default=1e-12)
    args = parser.parse_args()
    print(
        json.dumps(
            compare_artifacts(
                args.reference,
                args.candidate,
                rtol=args.rtol,
                atol=args.atol,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

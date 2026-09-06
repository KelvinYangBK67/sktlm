"""Compare canonical S1M2 artifacts under the accepted numeric contract."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from itertools import zip_longest
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
    return json.loads(path.read_text(encoding="utf-8"))


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


_MISSING = object()


def _compare_jsonl(
    left_path: Path,
    right_path: Path,
    *,
    name: str,
    result: Comparison,
    rtol: float,
    atol: float,
) -> None:
    with (
        left_path.open(encoding="utf-8") as left_handle,
        right_path.open(encoding="utf-8") as right_handle,
    ):
        for index, (left_line, right_line) in enumerate(
            zip_longest(left_handle, right_handle, fillvalue=_MISSING)
        ):
            if left_line is _MISSING or right_line is _MISSING:
                raise AssertionError(f"{name}: line counts differ at {index}")
            _compare(
                json.loads(left_line),
                json.loads(right_line),
                path=f"{name}[{index}]",
                result=result,
                rtol=rtol,
                atol=atol,
            )


def _parse_tsv_row(row: list[str]) -> list[str | float]:
    if not row:
        return []
    return [row[0], *(_maybe_float(value) for value in row[1:])]


def _compare_tsv(
    left_path: Path,
    right_path: Path,
    *,
    name: str,
    result: Comparison,
    rtol: float,
    atol: float,
) -> None:
    with (
        left_path.open(encoding="utf-8", newline="") as left_handle,
        right_path.open(encoding="utf-8", newline="") as right_handle,
    ):
        left_rows = csv.reader(left_handle, delimiter="\t")
        right_rows = csv.reader(right_handle, delimiter="\t")
        left_header = next(left_rows, None)
        right_header = next(right_rows, None)
        if left_header is None or right_header is None:
            raise ValueError(f"empty TSV artifact: {left_path} or {right_path}")
        _compare(
            left_header,
            right_header,
            path=f"{name}.header",
            result=result,
            rtol=rtol,
            atol=atol,
        )
        for index, (left_row, right_row) in enumerate(
            zip_longest(left_rows, right_rows, fillvalue=_MISSING),
            start=1,
        ):
            if left_row is _MISSING or right_row is _MISSING:
                raise AssertionError(f"{name}: row counts differ at {index}")
            if not left_row or not right_row:
                raise AssertionError(f"{name}: empty row at {index}")
            left_identity = left_row[0]
            _compare(
                _parse_tsv_row(left_row),
                _parse_tsv_row(right_row),
                path=f"{name}[{left_identity}]",
                result=result,
                rtol=rtol,
                atol=atol,
            )


def _compare_artifact(
    left_path: Path,
    right_path: Path,
    *,
    name: str,
    result: Comparison,
    rtol: float,
    atol: float,
) -> None:
    if left_path.suffix == ".jsonl":
        _compare_jsonl(
            left_path,
            right_path,
            name=name,
            result=result,
            rtol=rtol,
            atol=atol,
        )
        return
    if left_path.suffix == ".tsv":
        _compare_tsv(
            left_path,
            right_path,
            name=name,
            result=result,
            rtol=rtol,
            atol=atol,
        )
        return
    _compare(
        _load(left_path),
        _load(right_path),
        path=name,
        result=result,
        rtol=rtol,
        atol=atol,
    )


def compare_artifacts(
    reference: Path,
    candidate: Path,
    *,
    rtol: float = 1e-10,
    atol: float = 1e-12,
) -> dict[str, Any]:
    result = Comparison()
    for name in CANONICAL_ARTIFACTS:
        _compare_artifact(
            reference / name,
            candidate / name,
            name=name,
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

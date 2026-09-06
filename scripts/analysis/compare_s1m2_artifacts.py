"""Compare canonical S1M2 artifacts under the accepted numeric contract."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import tempfile
from contextlib import closing
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
TSV_NUMERIC_COLUMNS = frozenset(
    {
        "active",
        "active_parameter_count",
        "expected_count",
        "expected_usage",
        "length",
        "model_log_score",
        "model_probability",
        "number_of_contexts",
        "number_of_surface_variants",
        "occurrence_support",
        "value",
    }
)


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

        if not math.isfinite(left_number) or not math.isfinite(right_number):
            same_nonfinite = (
                (math.isnan(left_number) and math.isnan(right_number))
                or left_number == right_number
            )
            if not same_nonfinite:
                raise AssertionError(
                    f"{path}: {left_number!r} != {right_number!r}"
                )
            return

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


def _parse_tsv_row(
    row: list[str],
    *,
    header: list[str],
    path: str,
) -> list[str | float]:
    if len(row) != len(header):
        raise AssertionError(
            f"{path}: row has {len(row)} columns; expected {len(header)}"
        )
    return [
        _maybe_float(value) if column in TSV_NUMERIC_COLUMNS else value
        for column, value in zip(header[1:], row[1:], strict=True)
    ]


def _insert_tsv_rows(
    connection: sqlite3.Connection,
    rows: csv.reader,
    *,
    path: Path,
    batch_size: int = 4096,
) -> None:
    batch: list[tuple[str, str]] = []
    try:
        for row in rows:
            if not row:
                raise ValueError(f"empty TSV row in {path}")
            batch.append(
                (
                    row[0],
                    json.dumps(row[1:], ensure_ascii=False, separators=(",", ":")),
                )
            )
            if len(batch) >= batch_size:
                connection.executemany(
                    "INSERT INTO reference_rows(identity, row_json) VALUES (?, ?)",
                    batch,
                )
                batch.clear()
        if batch:
            connection.executemany(
                "INSERT INTO reference_rows(identity, row_json) VALUES (?, ?)",
                batch,
            )
    except sqlite3.IntegrityError as error:
        raise ValueError(f"duplicate first-column identity in {path}") from error


def _compare_tsv(
    left_path: Path,
    right_path: Path,
    *,
    name: str,
    result: Comparison,
    rtol: float,
    atol: float,
    scratch_dir: Path | None,
) -> None:
    if scratch_dir is not None:
        scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="sktlm_artifact_compare_",
        dir=scratch_dir,
    ) as temporary:
        database = Path(temporary) / "reference_rows.sqlite"
        with (
            left_path.open(encoding="utf-8", newline="") as left_handle,
            right_path.open(encoding="utf-8", newline="") as right_handle,
            closing(sqlite3.connect(database)) as connection,
        ):
            left_rows = csv.reader(left_handle, delimiter="\t")
            right_rows = csv.reader(right_handle, delimiter="\t")
            left_header = next(left_rows, None)
            right_header = next(right_rows, None)
            if left_header is None or right_header is None:
                raise ValueError(
                    f"empty TSV artifact: {left_path} or {right_path}"
                )
            _compare(
                left_header,
                right_header,
                path=f"{name}.header",
                result=result,
                rtol=rtol,
                atol=atol,
            )
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute(
                "CREATE TABLE reference_rows("
                "identity TEXT PRIMARY KEY, row_json TEXT NOT NULL"
                ") WITHOUT ROWID"
            )
            _insert_tsv_rows(
                connection,
                left_rows,
                path=left_path,
            )
            connection.commit()

            for right_row in right_rows:
                if not right_row:
                    raise ValueError(f"empty TSV row in {right_path}")
                identity = right_row[0]
                stored = connection.execute(
                    "SELECT row_json FROM reference_rows WHERE identity = ?",
                    (identity,),
                ).fetchone()
                if stored is None:
                    raise AssertionError(
                        f"{name}: unexpected or duplicate identity {identity!r}"
                    )
                left_row = [identity, *json.loads(stored[0])]
                _compare(
                    _parse_tsv_row(
                        left_row,
                        header=left_header,
                        path=f"{name}[{identity}]",
                    ),
                    _parse_tsv_row(
                        right_row,
                        header=right_header,
                        path=f"{name}[{identity}]",
                    ),
                    path=f"{name}[{identity}]",
                    result=result,
                    rtol=rtol,
                    atol=atol,
                )
                connection.execute(
                    "DELETE FROM reference_rows WHERE identity = ?",
                    (identity,),
                )
            missing = connection.execute(
                "SELECT identity FROM reference_rows LIMIT 1"
            ).fetchone()
            if missing is not None:
                raise AssertionError(
                    f"{name}: candidate is missing identity {missing[0]!r}"
                )


def _compare_artifact(
    left_path: Path,
    right_path: Path,
    *,
    name: str,
    result: Comparison,
    rtol: float,
    atol: float,
    scratch_dir: Path | None,
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
            scratch_dir=scratch_dir,
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
    scratch_dir: Path | None = None,
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
            scratch_dir=scratch_dir,
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
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        help="directory for bounded disk-backed TSV comparison scratch space",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            compare_artifacts(
                args.reference,
                args.candidate,
                rtol=args.rtol,
                atol=args.atol,
                scratch_dir=args.scratch_dir,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

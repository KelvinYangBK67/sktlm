"""Deterministic static workload selection for S1M2 continuous profiling.

This module reads representation text and frontend structure only.  It never
builds candidates, scores analyses, or observes model runtime/outcomes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sktlm.latent.frontend import CueKind, parse_surface
from sktlm.latent.training import EXPECTED_FREEZE_ID


IMPLEMENTATION = "s1m2-continuous-static-structure-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state(repo_root: Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, not bool(status.strip())


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _quantile_from_counts(counts: Counter[int], numerator: int) -> int:
    if not counts:
        return 0
    total = sum(counts.values())
    target = ((total - 1) * numerator + 50) // 100
    seen = 0
    for value, count in sorted(counts.items()):
        seen += count
        if seen > target:
            return value
    raise AssertionError("nonempty histogram has no terminal quantile")


def _span_summary(counts: Counter[int], maximum: int) -> dict[str, int]:
    return {
        "count": sum(counts.values()),
        "p50": _quantile_from_counts(counts, 50),
        "p90": _quantile_from_counts(counts, 90),
        "p95": _quantile_from_counts(counts, 95),
        "p99": _quantile_from_counts(counts, 99),
        "max": maximum,
    }


@dataclass(frozen=True, slots=True)
class StaticInput:
    cell_id: str
    manifest: Path
    manifest_sha256: str
    script: str
    condition: str = "continuous"


@dataclass(frozen=True, slots=True)
class ContinuousSelectionConfig:
    inputs: tuple[StaticInput, ...]
    selection_basis_cell: str
    representative_percentiles: tuple[int, ...]
    stress_documents: int
    require_clean_git: bool = True

    @classmethod
    def load(cls, path: Path, *, repo_root: Path) -> "ContinuousSelectionConfig":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "sktlm-s1m2-continuous-selection/v1":
            raise ValueError("Unsupported continuous-selection configuration.")
        inputs = tuple(
            StaticInput(
                cell_id=str(item["cell_id"]),
                manifest=(repo_root / item["manifest"]).resolve(),
                manifest_sha256=str(item["manifest_sha256"]),
                script=str(item["script"]),
                condition=str(item["condition"]),
            )
            for item in payload["inputs"]
        )
        percentiles = tuple(
            int(value) for value in payload["selection"]["representative_percentiles"]
        )
        if not inputs or len({item.cell_id for item in inputs}) != len(inputs):
            raise ValueError("Continuous inputs must have unique cell IDs.")
        if any(item.condition != "continuous" for item in inputs):
            raise ValueError("Static S1M2 selection accepts continuous cells only.")
        if any(not 0 <= value <= 100 for value in percentiles):
            raise ValueError("Representative percentiles must be in [0, 100].")
        stress_documents = int(payload["selection"]["stress_documents"])
        if stress_documents < 1:
            raise ValueError("stress_documents must be >= 1")
        return cls(
            inputs=inputs,
            selection_basis_cell=str(payload["selection"]["basis_cell"]),
            representative_percentiles=percentiles,
            stress_documents=stress_documents,
            require_clean_git=bool(payload.get("require_clean_git", True)),
        )


def _manifest_rows(item: StaticInput, repo_root: Path) -> tuple[dict[str, str], ...]:
    actual_hash = _sha256(item.manifest)
    if actual_hash != item.manifest_sha256:
        raise ValueError(
            f"Manifest identity mismatch for {item.cell_id}: {actual_hash}"
        )
    with item.manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(
            row
            for row in csv.DictReader(handle)
            if row.get("script") == item.script
            and row.get("condition") == item.condition
        )
    if not rows:
        raise ValueError(f"No manifest rows for {item.cell_id}.")
    if {row["freeze_id"] for row in rows} != {EXPECTED_FREEZE_ID}:
        raise ValueError(f"Unexpected freeze identity for {item.cell_id}.")
    if len({row["relative_path"] for row in rows}) != len(rows):
        raise ValueError(f"Duplicate relative paths for {item.cell_id}.")
    return tuple(sorted(rows, key=lambda row: row["relative_path"]))


def _scan_document(
    row: dict[str, str],
    *,
    script: str,
    repo_root: Path,
) -> dict[str, Any]:
    path = Path(row["representation_path"])
    if not path.is_absolute():
        path = repo_root / path
    if not path.is_file():
        raise FileNotFoundError(path)
    byte_count = path.stat().st_size
    if row.get("byte_count") and byte_count != int(row["byte_count"]):
        raise ValueError(f"Manifest byte count mismatch: {path}")

    written_characters = 0
    lines = 0
    nonempty_lines = 0
    phonemes = 0
    punctuation_delimiters = 0
    span_counts: Counter[int] = Counter()
    max_span = 0
    span_phoneme_sum = 0
    span_squared_phonemes = 0
    span_digest = hashlib.sha256()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw_line in handle:
            lines += 1
            written_characters += len(raw_line)
            text = raw_line.rstrip("\r\n")
            parsed = parse_surface(text, script=script)
            phonemes += len(parsed.phonemes)
            if parsed.phonemes:
                nonempty_lines += 1
            offsets = [
                cue.phoneme_offset
                for cue in parsed.cues
                if cue.kind == CueKind.PUNCTUATION
            ]
            punctuation_delimiters += len(offsets)
            previous = 0
            for offset in (*offsets, len(parsed.phonemes)):
                length = offset - previous
                previous = offset
                if length <= 0:
                    continue
                span_counts[length] += 1
                max_span = max(max_span, length)
                span_phoneme_sum += length
                span_squared_phonemes += length * length
                span_digest.update(length.to_bytes(8, "big"))
    if row.get("line_count") and lines != int(row["line_count"]):
        raise ValueError(f"Manifest line count mismatch: {path}")
    if row.get("char_count") and written_characters != int(row["char_count"]):
        raise ValueError(f"Manifest character count mismatch: {path}")
    if row.get("phoneme_count") and phonemes != int(row["phoneme_count"]):
        raise ValueError(f"Manifest phoneme count mismatch: {path}")
    return {
        "relative_path": row["relative_path"],
        "representation_path": Path(row["representation_path"]).as_posix(),
        "representation_hash": row["representation_hash"],
        "bytes": byte_count,
        "written_characters": written_characters,
        "lines": lines,
        "nonempty_lines": nonempty_lines,
        "phonemes": phonemes,
        "punctuation_delimiters": punctuation_delimiters,
        "continuous_spans": _span_summary(span_counts, max_span),
        "span_phoneme_sum": span_phoneme_sum,
        "span_squared_phonemes": span_squared_phonemes,
        "span_length_sha256": span_digest.hexdigest(),
    }


def _aggregate(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = tuple(documents)
    max_span = max(int(row["continuous_spans"]["max"]) for row in rows)
    document_maxima = Counter(
        int(row["continuous_spans"]["max"]) for row in rows
    )
    return {
        "documents": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "written_characters": sum(int(row["written_characters"]) for row in rows),
        "lines": sum(int(row["lines"]) for row in rows),
        "phonemes": sum(int(row["phonemes"]) for row in rows),
        "punctuation_delimiters": sum(
            int(row["punctuation_delimiters"]) for row in rows
        ),
        "continuous_spans": sum(
            int(row["continuous_spans"]["count"]) for row in rows
        ),
        "span_phoneme_sum": sum(int(row["span_phoneme_sum"]) for row in rows),
        "span_squared_phonemes": sum(
            int(row["span_squared_phonemes"]) for row in rows
        ),
        "document_max_span_distribution": _span_summary(
            document_maxima,
            max_span,
        ),
    }


def _select_documents(
    rows: tuple[dict[str, Any], ...],
    *,
    percentiles: tuple[int, ...],
    stress_count: int,
) -> dict[str, list[str]]:
    if stress_count >= len(rows):
        raise ValueError("Stress selection must leave representative candidates.")
    stress_rows = sorted(
        rows,
        key=lambda row: (
            -int(row["continuous_spans"]["max"]),
            -int(row["span_squared_phonemes"]),
            -int(row["phonemes"]),
            str(row["relative_path"]),
        ),
    )[:stress_count]
    stress = {str(row["relative_path"]) for row in stress_rows}
    ranked = sorted(
        (row for row in rows if str(row["relative_path"]) not in stress),
        key=lambda row: (
            int(row["span_squared_phonemes"]),
            int(row["continuous_spans"]["max"]),
            int(row["phonemes"]),
            str(row["relative_path"]),
        ),
    )
    representative: list[str] = []
    used_indices: set[int] = set()
    for percentile in percentiles:
        target = ((len(ranked) - 1) * percentile + 50) // 100
        index = next(
            candidate
            for distance in range(len(ranked))
            for candidate in (target - distance, target + distance)
            if 0 <= candidate < len(ranked) and candidate not in used_indices
        )
        used_indices.add(index)
        path = str(ranked[index]["relative_path"])
        representative.append(path)
    return {
        "representative": representative,
        "stress": [str(row["relative_path"]) for row in stress_rows],
    }


def scan_continuous_structure(
    config: ContinuousSelectionConfig,
    *,
    repo_root: Path,
    config_path: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    commit, clean = _git_state(repo_root)
    if config.require_clean_git and not clean:
        raise RuntimeError("Static scan requires a clean Git worktree.")
    cells: dict[str, Any] = {}
    for item in config.inputs:
        rows = _manifest_rows(item, repo_root)
        documents = tuple(
            _scan_document(row, script=item.script, repo_root=repo_root)
            for row in rows
        )
        cells[item.cell_id] = {
            "script": item.script,
            "condition": item.condition,
            "manifest": _display_path(item.manifest, repo_root),
            "manifest_sha256": item.manifest_sha256,
            "aggregate": _aggregate(documents),
            "documents": documents,
        }
    if config.selection_basis_cell not in cells:
        raise ValueError("Selection basis cell is not one of the configured inputs.")
    basis = tuple(cells[config.selection_basis_cell]["documents"])
    by_cell = {
        cell_id: {row["relative_path"]: row for row in value["documents"]}
        for cell_id, value in cells.items()
    }
    expected_paths = set(by_cell[config.selection_basis_cell])
    for cell_id, documents in by_cell.items():
        if set(documents) != expected_paths:
            raise ValueError(f"Document membership differs for {cell_id}.")
    mismatches = []
    for relative_path in sorted(expected_paths):
        reference = by_cell[config.selection_basis_cell][relative_path]
        for cell_id, documents in by_cell.items():
            candidate = documents[relative_path]
            if (
                candidate["phonemes"] != reference["phonemes"]
                or candidate["span_length_sha256"]
                != reference["span_length_sha256"]
            ):
                mismatches.append((relative_path, cell_id))
    if mismatches:
        raise ValueError(f"Cross-frontend continuous structure mismatch: {mismatches[:5]}")
    return {
        "schema_version": "sktlm-s1m2-continuous-static-structure/v1",
        "implementation": IMPLEMENTATION,
        "git_commit": commit,
        "git_worktree_clean": clean,
        "config": _display_path(config_path, repo_root),
        "config_sha256": _sha256(config_path),
        "selection_basis_cell": config.selection_basis_cell,
        "selection_rule": {
            "representative": (
                "remove stress set; rank by (span_squared_phonemes, max_span, "
                "phonemes, relative_path); take configured nearest ranks"
            ),
            "stress": (
                "rank by (max_span, span_squared_phonemes, phonemes) descending, "
                "then relative_path ascending"
            ),
            "representative_percentiles": list(config.representative_percentiles),
            "stress_documents": config.stress_documents,
        },
        "selection": _select_documents(
            basis,
            percentiles=config.representative_percentiles,
            stress_count=config.stress_documents,
        ),
        "cross_frontend_structure_identity": "PASS",
        "cells": cells,
    }


def _write_list(path: Path, values: Iterable[str], *, heading: str) -> None:
    content = f"# {heading}\n" + "".join(f"{value}\n" for value in values)
    path.write_text(content, encoding="utf-8", newline="")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Scan static continuous structure and freeze S1M2 workloads."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmarks/s1m2_continuous_selection.json"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    config_path = (
        args.config if args.config.is_absolute() else repo_root / args.config
    ).resolve()
    output_dir = (
        args.output_dir
        if args.output_dir.is_absolute()
        else repo_root / args.output_dir
    ).resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite static scan: {output_dir}")
    config = ContinuousSelectionConfig.load(config_path, repo_root=repo_root)
    payload = scan_continuous_structure(
        config,
        repo_root=repo_root,
        config_path=config_path,
    )
    output_dir.mkdir(parents=True)
    (output_dir / "structure.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    _write_list(
        output_dir / "representative_documents.txt",
        payload["selection"]["representative"],
        heading="S1M2 continuous representative workload",
    )
    _write_list(
        output_dir / "stress_documents.txt",
        payload["selection"]["stress"],
        heading="S1M2 continuous long-span stress workload",
    )
    (output_dir / "complete.json").write_text(
        json.dumps(
            {
                "schema_version": "sktlm-s1m2-static-scan-completion/v1",
                "git_commit": payload["git_commit"],
                "config_sha256": payload["config_sha256"],
                "structure_sha256": _sha256(output_dir / "structure.json"),
                "status": "COMPLETE",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    print(f"static scan: {output_dir}")
    print(f"git commit: {payload['git_commit']}")
    print("status: COMPLETE")


if __name__ == "__main__":
    main()

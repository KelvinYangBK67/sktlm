#!/usr/bin/env python3
"""
Read-only S1M2 execution-pressure audit.

This is intentionally a thin analysis entry point:

- reuses the existing S1M2 continuous static scanner for document-level metrics;
- adds only line-level pressure concentration needed for granularity diagnosis;
- maps the frozen Round1 72-document calibration order to zero-based indices;
- never builds candidates, runs inference, trains a model, or reads runtime outcomes.

Default target:
    M0 / Devanagari / continuous
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from sktlm.latent.continuous_structure import (
    ContinuousSelectionConfig,
    _manifest_rows,
    _scan_document,
)
from sktlm.latent.frontend import CueKind, parse_surface


DEFAULT_CONFIG = Path("configs/benchmarks/s1m2_continuous_selection.json")
DEFAULT_CALIBRATION = Path(
    "configs/benchmarks/s1m2_worker_calibration_documents.txt"
)
DEFAULT_OUTPUT = Path("artifacts/s1m2_execution_pressure_audit")


def _resolve(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _read_calibration_order(path: Path) -> tuple[str, ...]:
    values = tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not values:
        raise ValueError(f"Calibration list is empty: {path}")
    if len(set(values)) != len(values):
        raise ValueError(f"Calibration list contains duplicates: {path}")
    return values


def _line_pressure(
    representation_path: Path,
    *,
    script: str,
) -> dict[str, Any]:
    """
    Compute line-level pressure using the same continuous-span definition as
    src/sktlm/latent/continuous_structure.py:

        parse_surface(...)
        punctuation cue offsets delimit spans
        pressure = sum(span_length ** 2)

    Newline itself contributes no pressure here; each existing representation
    line is audited independently, matching the current static scanner.
    """

    line_pressures: list[int] = []
    line_phonemes: list[int] = []
    line_span_counts: list[int] = []

    with representation_path.open("r", encoding="utf-8", newline="") as handle:
        for raw_line in handle:
            text = raw_line.rstrip("\r\n")
            parsed = parse_surface(text, script=script)

            offsets = [
                cue.phoneme_offset
                for cue in parsed.cues
                if cue.kind == CueKind.PUNCTUATION
            ]

            previous = 0
            pressure = 0
            spans = 0

            for offset in (*offsets, len(parsed.phonemes)):
                length = offset - previous
                previous = offset

                if length <= 0:
                    continue

                pressure += length * length
                spans += 1

            line_pressures.append(pressure)
            line_phonemes.append(len(parsed.phonemes))
            line_span_counts.append(spans)

    nonzero = [
        (index + 1, pressure)
        for index, pressure in enumerate(line_pressures)
        if pressure > 0
    ]
    ranked = sorted(nonzero, key=lambda item: (-item[1], item[0]))

    total_pressure = sum(line_pressures)

    def share(top_n: int) -> float:
        if total_pressure == 0:
            return 0.0
        return (
            sum(pressure for _, pressure in ranked[:top_n])
            / total_pressure
        )

    max_line_number = ranked[0][0] if ranked else None
    max_line_pressure = ranked[0][1] if ranked else 0

    return {
        "line_count": len(line_pressures),
        "nonempty_pressure_lines": len(nonzero),
        "max_line_number": max_line_number,
        "max_line_pressure": max_line_pressure,
        "top1_line_pressure_share": share(1),
        "top5_line_pressure_share": share(5),
        "top10_line_pressure_share": share(10),
        "top_lines": [
            {
                "line_number": line_number,
                "pressure": pressure,
                "pressure_share": (
                    pressure / total_pressure
                    if total_pressure
                    else 0.0
                ),
                "phonemes": line_phonemes[line_number - 1],
                "continuous_spans": line_span_counts[line_number - 1],
            }
            for line_number, pressure in ranked[:10]
        ],
    }


def _classify(
    *,
    total_pressure: int,
    max_span: int,
    top1_line_share: float,
    top5_line_share: float,
) -> str:
    """
    Descriptive diagnosis only; this does not select a scheduler policy.

    C: one scientific span alone contributes >= 50% of document pressure.
    B: pressure is concentrated in one/few existing lines.
    A: pressure is comparatively distributed across many lines/spans.
    """

    if total_pressure <= 0:
        return "EMPTY"

    max_span_share = (max_span * max_span) / total_pressure

    if max_span_share >= 0.50:
        return "C_ONE_DOMINANT_PATHOLOGICAL_SPAN"

    if top1_line_share >= 0.50 or top5_line_share >= 0.80:
        return "B_PRESSURE_CONCENTRATED_IN_FEW_LINES_OR_SPANS"

    return "A_MANY_EXPENSIVE_INDEPENDENT_LINES_OR_SPANS"


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("No rows to write.")

    fieldnames = list(rows[0].keys())

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit S1M2 document/line static execution pressure."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    parser.add_argument(
        "--calibration-documents",
        type=Path,
        default=DEFAULT_CALIBRATION,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    config_path = _resolve(repo_root, args.config)
    calibration_path = _resolve(
        repo_root,
        args.calibration_documents,
    )
    output_dir = _resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = ContinuousSelectionConfig.load(
        config_path,
        repo_root=repo_root,
    )

    basis_inputs = [
        item
        for item in config.inputs
        if item.cell_id == config.selection_basis_cell
    ]
    if len(basis_inputs) != 1:
        raise ValueError(
            "Expected exactly one configured selection-basis cell."
        )

    basis = basis_inputs[0]

    if basis.cell_id != "m0_devanagari_continuous":
        raise ValueError(
            "This audit expects the frozen M0 Devanagari continuous "
            f"selection basis, got {basis.cell_id!r}."
        )

    manifest_rows = _manifest_rows(basis, repo_root)

    calibration_order = _read_calibration_order(calibration_path)
    calibration_index = {
        relative_path: index
        for index, relative_path in enumerate(calibration_order)
    }

    manifest_paths = {
        row["relative_path"]
        for row in manifest_rows
    }
    missing_calibration = [
        path
        for path in calibration_order
        if path not in manifest_paths
    ]
    if missing_calibration:
        raise ValueError(
            "Calibration documents missing from basis manifest: "
            f"{missing_calibration[:5]}"
        )

    documents: list[dict[str, Any]] = []

    for row in manifest_rows:
        static = _scan_document(
            row,
            script=basis.script,
            repo_root=repo_root,
        )

        representation_path = Path(row["representation_path"])
        if not representation_path.is_absolute():
            representation_path = repo_root / representation_path

        line = _line_pressure(
            representation_path,
            script=basis.script,
        )

        total_pressure = int(static["span_squared_phonemes"])
        max_span = int(static["continuous_spans"]["max"])

        max_span_pressure_share = (
            (max_span * max_span) / total_pressure
            if total_pressure
            else 0.0
        )

        classification = _classify(
            total_pressure=total_pressure,
            max_span=max_span,
            top1_line_share=float(
                line["top1_line_pressure_share"]
            ),
            top5_line_share=float(
                line["top5_line_pressure_share"]
            ),
        )

        documents.append(
            {
                "relative_path": row["relative_path"],
                "round1_calibration_index": calibration_index.get(
                    row["relative_path"],
                    "",
                ),
                "phonemes": int(static["phonemes"]),
                "continuous_spans": int(
                    static["continuous_spans"]["count"]
                ),
                "max_span": max_span,
                "span_squared_phonemes": total_pressure,
                "max_span_pressure_share": max_span_pressure_share,
                "line_count": int(line["line_count"]),
                "nonempty_pressure_lines": int(
                    line["nonempty_pressure_lines"]
                ),
                "max_line_number": (
                    line["max_line_number"]
                    if line["max_line_number"] is not None
                    else ""
                ),
                "max_line_pressure": int(
                    line["max_line_pressure"]
                ),
                "top1_line_pressure_share": float(
                    line["top1_line_pressure_share"]
                ),
                "top5_line_pressure_share": float(
                    line["top5_line_pressure_share"]
                ),
                "top10_line_pressure_share": float(
                    line["top10_line_pressure_share"]
                ),
                "pressure_class": classification,
            }
        )

    # Rank highest static-pressure document as rank 1.
    documents.sort(
        key=lambda item: (
            -int(item["span_squared_phonemes"]),
            -int(item["max_span"]),
            -int(item["phonemes"]),
            str(item["relative_path"]),
        )
    )

    for rank, row in enumerate(documents, 1):
        row["full_corpus_pressure_rank"] = rank

    # Put rank near the front of TSV.
    ordered_rows: list[dict[str, Any]] = []
    for row in documents:
        ordered_rows.append(
            {
                "full_corpus_pressure_rank":
                    row["full_corpus_pressure_rank"],
                "round1_calibration_index":
                    row["round1_calibration_index"],
                "relative_path":
                    row["relative_path"],
                "phonemes":
                    row["phonemes"],
                "continuous_spans":
                    row["continuous_spans"],
                "max_span":
                    row["max_span"],
                "span_squared_phonemes":
                    row["span_squared_phonemes"],
                "max_span_pressure_share":
                    row["max_span_pressure_share"],
                "line_count":
                    row["line_count"],
                "nonempty_pressure_lines":
                    row["nonempty_pressure_lines"],
                "max_line_number":
                    row["max_line_number"],
                "max_line_pressure":
                    row["max_line_pressure"],
                "top1_line_pressure_share":
                    row["top1_line_pressure_share"],
                "top5_line_pressure_share":
                    row["top5_line_pressure_share"],
                "top10_line_pressure_share":
                    row["top10_line_pressure_share"],
                "pressure_class":
                    row["pressure_class"],
            }
        )

    _write_tsv(
        output_dir / "document_pressure.tsv",
        ordered_rows,
    )

    by_path = {
        row["relative_path"]: row
        for row in documents
    }

    # Round1 NEXT_DOC=50 is zero-based.
    target_index = 50
    if target_index >= len(calibration_order):
        raise ValueError(
            f"Round1 index {target_index} is outside calibration list."
        )

    target_path = calibration_order[target_index]
    target = by_path[target_path]

    # Recompute just this document's top-line detail for the summary.
    target_manifest_row = next(
        row
        for row in manifest_rows
        if row["relative_path"] == target_path
    )
    target_representation = Path(
        target_manifest_row["representation_path"]
    )
    if not target_representation.is_absolute():
        target_representation = (
            repo_root / target_representation
        )

    target_line = _line_pressure(
        target_representation,
        script=basis.script,
    )

    index50_summary = {
        "schema_version":
            "sktlm-s1m2-execution-pressure-index50/v1",
        "round1_index_semantics": "zero_based",
        "round1_calibration_index": target_index,
        "relative_path": target_path,
        "full_corpus_pressure_rank":
            int(target["full_corpus_pressure_rank"]),
        "phonemes": int(target["phonemes"]),
        "continuous_spans": int(target["continuous_spans"]),
        "max_span": int(target["max_span"]),
        "span_squared_phonemes":
            int(target["span_squared_phonemes"]),
        "max_span_pressure_share":
            float(target["max_span_pressure_share"]),
        "line_count": int(target["line_count"]),
        "nonempty_pressure_lines":
            int(target["nonempty_pressure_lines"]),
        "max_line_number": target["max_line_number"],
        "max_line_pressure":
            int(target["max_line_pressure"]),
        "top1_line_pressure_share":
            float(target["top1_line_pressure_share"]),
        "top5_line_pressure_share":
            float(target["top5_line_pressure_share"]),
        "top10_line_pressure_share":
            float(target["top10_line_pressure_share"]),
        "pressure_class": target["pressure_class"],
        "top_lines": target_line["top_lines"],
    }

    (output_dir / "round1_index50_summary.json").write_text(
        json.dumps(
            index50_summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    total_corpus_pressure = sum(
        int(row["span_squared_phonemes"])
        for row in documents
    )
    total_round1_pressure = sum(
        int(by_path[path]["span_squared_phonemes"])
        for path in calibration_order
    )

    class_counts: dict[str, int] = {}
    for row in documents:
        key = str(row["pressure_class"])
        class_counts[key] = class_counts.get(key, 0) + 1

    top10_pressure = sum(
        int(row["span_squared_phonemes"])
        for row in documents[:10]
    )

    summary = {
        "schema_version":
            "sktlm-s1m2-execution-pressure-audit/v1",
        "selection_basis_cell": basis.cell_id,
        "script": basis.script,
        "condition": basis.condition,
        "documents": len(documents),
        "round1_calibration_documents":
            len(calibration_order),
        "corpus_span_squared_phonemes":
            total_corpus_pressure,
        "round1_span_squared_phonemes":
            total_round1_pressure,
        "top10_document_pressure_share": (
            top10_pressure / total_corpus_pressure
            if total_corpus_pressure
            else 0.0
        ),
        "pressure_classes": dict(
            sorted(class_counts.items())
        ),
        "round1_index50": index50_summary,
    }

    (output_dir / "summary.json").write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 92)
    print("S1M2 EXECUTION PRESSURE AUDIT")
    print("=" * 92)
    print(f"documents                  : {len(documents)}")
    print(
        "round1 calibration docs     : "
        f"{len(calibration_order)}"
    )
    print(
        "corpus span^2 pressure       : "
        f"{total_corpus_pressure:,}"
    )
    print(
        "top-10 document share        : "
        f"{summary['top10_document_pressure_share']:.2%}"
    )

    print()
    print("ROUND1 ZERO-BASED INDEX 50")
    print("-" * 92)
    print(f"path                       : {target_path}")
    print(
        "full corpus pressure rank  : "
        f"{target['full_corpus_pressure_rank']}"
    )
    print(
        "phonemes                   : "
        f"{int(target['phonemes']):,}"
    )
    print(
        "continuous spans           : "
        f"{int(target['continuous_spans']):,}"
    )
    print(
        "max span                   : "
        f"{int(target['max_span']):,}"
    )
    print(
        "span^2 pressure            : "
        f"{int(target['span_squared_phonemes']):,}"
    )
    print(
        "max-span pressure share    : "
        f"{float(target['max_span_pressure_share']):.2%}"
    )
    print(
        "max-line pressure share    : "
        f"{float(target['top1_line_pressure_share']):.2%}"
    )
    print(
        "top-5 line pressure share  : "
        f"{float(target['top5_line_pressure_share']):.2%}"
    )
    print(
        "classification             : "
        f"{target['pressure_class']}"
    )

    print()
    print("TOP 20 DOCUMENTS BY STATIC PRESSURE")
    print("-" * 92)
    print(
        f"{'rank':>4}  {'r1idx':>5}  {'pressure':>14}  "
        f"{'max':>6}  {'maxspan%':>8}  {'line1%':>7}  path"
    )

    for row in documents[:20]:
        r1 = row["round1_calibration_index"]
        r1_text = str(r1) if r1 != "" else "-"

        print(
            f"{int(row['full_corpus_pressure_rank']):4d}  "
            f"{r1_text:>5}  "
            f"{int(row['span_squared_phonemes']):14,d}  "
            f"{int(row['max_span']):6,d}  "
            f"{float(row['max_span_pressure_share']):7.1%}  "
            f"{float(row['top1_line_pressure_share']):6.1%}  "
            f"{row['relative_path']}"
        )

    print()
    print("outputs:")
    print(f"  {output_dir / 'document_pressure.tsv'}")
    print(f"  {output_dir / 'round1_index50_summary.json'}")
    print(f"  {output_dir / 'summary.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
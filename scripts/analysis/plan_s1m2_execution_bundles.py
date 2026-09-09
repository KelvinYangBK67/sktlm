#!/usr/bin/env python3
"""
Build deterministic static execution-bundle candidate plans for S1M2 continuous workloads.

Analysis/planning only: no model training, candidate construction, or latent inference.
The repository's existing frontend segmentation is reused exactly. Every existing
ObservedSegment is indivisible. Adjacent segments from the same document are packed
with static pressure = phoneme_count ** 2.

Default outputs:
  artifacts/s1m2_execution_bundle_plans/
    scan_summary.json
    candidates_summary.json
    candidate_002048/{summary.json,bundles.jsonl,documents.tsv}
    candidate_004096/{summary.json,bundles.jsonl,documents.tsv}
    candidate_008192/{summary.json,bundles.jsonl,documents.tsv}
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from sktlm.latent.continuous_structure import ContinuousSelectionConfig, _manifest_rows
from sktlm.latent.execution_bundles import PLANNER_IMPLEMENTATION
from sktlm.latent.frontend import ObservedSegment
from sktlm.latent.training import (
    CorpusDocument,
    TrainingConfig,
    _iter_document_segments as _iter_training_segments,
)

DEFAULT_CONFIG = Path("configs/benchmarks/s1m2_continuous_selection.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/s1m2_execution_bundle_plans")
DEFAULT_TARGET_BUNDLES = (2048, 4096, 8192)
DEFAULT_MAX_SEGMENTS_PER_BUNDLE = 256
DEFAULT_MAX_SEGMENT_TOKENS = 128


@dataclass(frozen=True, slots=True)
class SegmentRecord:
    document_index: int
    relative_path: str
    ordinal: int
    line_number: int
    segment_index: int
    phonemes: int
    pressure: int


@dataclass(frozen=True, slots=True)
class BundleRecord:
    document_index: int
    relative_path: str
    bundle_index: int
    first_segment_ordinal: int
    last_segment_ordinal_exclusive: int
    first_line_number: int
    first_segment_index: int
    last_line_number: int
    last_segment_index: int
    segment_count: int
    phonemes: int
    pressure: int
    oversized_single_segment: bool
    closed_by_segment_cap: bool


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (repo_root / path).resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head(repo_root: Path) -> str | None:
    try:
        return subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=repo_root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_dirty(repo_root: Path) -> bool | None:
    try:
        status = subprocess.run(
            ("git", "status", "--porcelain"), cwd=repo_root, check=True,
            capture_output=True, text=True,
        ).stdout
        return bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def _segment_phoneme_count(segment: ObservedSegment) -> int:
    return sum(len(token.phonemes) for token in segment.tokens)


def _iter_document_segments(
    path: Path,
    *,
    document_index: int,
    relative_path: str,
    script: str,
    max_segment_tokens: int,
    max_lines_per_document: int | None,
) -> Iterator[SegmentRecord]:
    ordinal = 0
    document = CorpusDocument(
        relative_path=relative_path,
        path=path,
        document_id=relative_path.replace("/", ":"),
        freeze_id="planner-read-only",
    )
    config = TrainingConfig(
        script=script,
        condition="continuous",
        max_segment_tokens=max_segment_tokens,
        max_lines_per_document=max_lines_per_document,
    )
    for line_number, segment_index, segment in _iter_training_segments(
        document, config
    ):
        phonemes = _segment_phoneme_count(segment)
        if phonemes < 1:
            raise ValueError(
                f"Trainer emitted an empty ObservedSegment in {relative_path}: "
                f"{line_number}:{segment_index}"
            )
        yield SegmentRecord(
            document_index=document_index,
            relative_path=relative_path,
            ordinal=ordinal,
            line_number=line_number,
            segment_index=segment_index,
            phonemes=phonemes,
            pressure=phonemes * phonemes,
        )
        ordinal += 1


def _quantile(values: Sequence[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[int(round((len(ordered) - 1) * q))]


def _stats(values: Sequence[int]) -> dict[str, int | float]:
    if not values:
        return {"count": 0, "sum": 0, "mean": 0.0, "p50": 0, "p90": 0,
                "p95": 0, "p99": 0, "max": 0}
    total = sum(values)
    return {
        "count": len(values), "sum": total, "mean": total / len(values),
        "p50": _quantile(values, 0.50), "p90": _quantile(values, 0.90),
        "p95": _quantile(values, 0.95), "p99": _quantile(values, 0.99),
        "max": max(values),
    }


def _scan_segments(
    *, repo_root: Path, rows: Sequence[dict[str, str]], script: str,
    max_segment_tokens: int, max_lines_per_document: int | None,
) -> tuple[list[list[SegmentRecord]], dict[str, Any]]:
    by_document: list[list[SegmentRecord]] = []
    segment_digest = hashlib.sha256()
    representation_digest = hashlib.sha256()
    total_phonemes = 0
    total_pressure = 0
    segment_lengths: list[int] = []
    document_rows: list[dict[str, Any]] = []

    for document_index, row in enumerate(rows):
        relative_path = row["relative_path"]
        representation_path = Path(row["representation_path"])
        if not representation_path.is_absolute():
            representation_path = repo_root / representation_path
        if not representation_path.is_file():
            raise FileNotFoundError(representation_path)

        actual_hash = _sha256(representation_path)
        expected_hash = row.get("representation_hash")
        if expected_hash and actual_hash != expected_hash:
            raise ValueError(
                f"Representation hash mismatch for {relative_path}: "
                f"{actual_hash} != {expected_hash}"
            )

        representation_digest.update(relative_path.encode("utf-8"))
        representation_digest.update(b"\0")
        representation_digest.update(actual_hash.encode("ascii"))
        representation_digest.update(b"\n")

        segments = list(_iter_document_segments(
            representation_path,
            document_index=document_index,
            relative_path=relative_path,
            script=script,
            max_segment_tokens=max_segment_tokens,
            max_lines_per_document=max_lines_per_document,
        ))
        by_document.append(segments)

        doc_phonemes = sum(item.phonemes for item in segments)
        doc_pressure = sum(item.pressure for item in segments)
        doc_max = max((item.phonemes for item in segments), default=0)
        total_phonemes += doc_phonemes
        total_pressure += doc_pressure
        segment_lengths.extend(item.phonemes for item in segments)

        for item in segments:
            segment_digest.update((
                f"{item.document_index}\t{item.relative_path}\t{item.ordinal}\t"
                f"{item.line_number}\t{item.segment_index}\t{item.phonemes}\n"
            ).encode("utf-8"))

        document_rows.append({
            "document_index": document_index,
            "relative_path": relative_path,
            "segments": len(segments),
            "phonemes": doc_phonemes,
            "pressure": doc_pressure,
            "max_segment_phonemes": doc_max,
            "representation_hash": actual_hash,
        })

    return by_document, {
        "documents": len(rows),
        "segments": sum(len(items) for items in by_document),
        "phonemes": total_phonemes,
        "pressure": total_pressure,
        "segment_phonemes": _stats(segment_lengths),
        "segment_sequence_sha256": segment_digest.hexdigest(),
        "representation_set_sha256": representation_digest.hexdigest(),
        "documents_detail": document_rows,
    }


def _make_bundle(
    items: Sequence[SegmentRecord], *, bundle_index: int,
    target_pressure: int, closed_by_segment_cap: bool,
) -> BundleRecord:
    if not items:
        raise ValueError("Cannot create an empty bundle")
    first, last = items[0], items[-1]
    pressure = sum(item.pressure for item in items)
    return BundleRecord(
        document_index=first.document_index,
        relative_path=first.relative_path,
        bundle_index=bundle_index,
        first_segment_ordinal=first.ordinal,
        last_segment_ordinal_exclusive=last.ordinal + 1,
        first_line_number=first.line_number,
        first_segment_index=first.segment_index,
        last_line_number=last.line_number,
        last_segment_index=last.segment_index,
        segment_count=len(items),
        phonemes=sum(item.phonemes for item in items),
        pressure=pressure,
        oversized_single_segment=(len(items) == 1 and pressure > target_pressure),
        closed_by_segment_cap=closed_by_segment_cap,
    )


def _pack_document(
    segments: Sequence[SegmentRecord], *, target_pressure: int,
    max_segments_per_bundle: int,
) -> list[BundleRecord]:
    """Contiguous closest-to-target greedy packing; segments are never split."""
    if target_pressure < 1 or max_segments_per_bundle < 1:
        raise ValueError("packing limits must be >= 1")
    bundles: list[BundleRecord] = []
    current: list[SegmentRecord] = []
    current_pressure = 0

    def emit(*, cap: bool = False) -> None:
        nonlocal current, current_pressure
        if not current:
            return
        bundles.append(_make_bundle(
            current,
            bundle_index=len(bundles),
            target_pressure=target_pressure,
            closed_by_segment_cap=cap,
        ))
        current = []
        current_pressure = 0

    for segment in segments:
        if not current:
            current = [segment]
            current_pressure = segment.pressure
            if current_pressure >= target_pressure:
                emit()
            continue

        if len(current) >= max_segments_per_bundle:
            emit(cap=True)
            current = [segment]
            current_pressure = segment.pressure
            if current_pressure >= target_pressure:
                emit()
            continue

        proposed = current_pressure + segment.pressure
        if proposed < target_pressure:
            current.append(segment)
            current_pressure = proposed
            continue

        # Choose the contiguous cut closer to the target pressure.
        under_distance = target_pressure - current_pressure
        over_distance = proposed - target_pressure
        if over_distance <= under_distance:
            current.append(segment)
            current_pressure = proposed
            emit()
        else:
            emit()
            current = [segment]
            current_pressure = segment.pressure
            if current_pressure >= target_pressure:
                emit()

    emit()
    return bundles


def _plan(
    by_document: Sequence[Sequence[SegmentRecord]], *, target_bundle_count: int,
    total_pressure: int, max_segments_per_bundle: int,
) -> tuple[list[BundleRecord], dict[str, Any]]:
    if target_bundle_count < 1 or total_pressure < 1:
        raise ValueError("target bundle count and total pressure must be positive")
    target_pressure = max(1, int(round(total_pressure / target_bundle_count)))
    bundles: list[BundleRecord] = []
    per_document_counts: list[int] = []
    for segments in by_document:
        doc_bundles = _pack_document(
            segments,
            target_pressure=target_pressure,
            max_segments_per_bundle=max_segments_per_bundle,
        )
        bundles.extend(doc_bundles)
        per_document_counts.append(len(doc_bundles))

    pressures = [item.pressure for item in bundles]
    counts = [item.segment_count for item in bundles]
    phonemes = [item.phonemes for item in bundles]
    return bundles, {
        "target_bundle_count": target_bundle_count,
        "actual_bundle_count": len(bundles),
        "target_pressure": target_pressure,
        "actual_to_target_bundle_count_ratio": len(bundles) / target_bundle_count,
        "bundle_pressure": _stats(pressures),
        "bundle_segments": _stats(counts),
        "bundle_phonemes": _stats(phonemes),
        "bundles_below_half_target_pressure": sum(v < 0.5 * target_pressure for v in pressures),
        "bundles_above_150pct_target_pressure": sum(v > 1.5 * target_pressure for v in pressures),
        "oversized_single_segment_bundles": sum(b.oversized_single_segment for b in bundles),
        "segment_cap_closed_bundles": sum(b.closed_by_segment_cap for b in bundles),
        "documents_with_zero_bundles": sum(c == 0 for c in per_document_counts),
        "max_bundles_in_one_document": max(per_document_counts, default=0),
    }


def _bundle_payload(bundle: BundleRecord) -> dict[str, Any]:
    return {
        "schema_version": "sktlm-s1m2-execution-bundle/v1",
        "document_index": bundle.document_index,
        "relative_path": bundle.relative_path,
        "bundle_index": bundle.bundle_index,
        "first_segment_ordinal": bundle.first_segment_ordinal,
        "last_segment_ordinal_exclusive": bundle.last_segment_ordinal_exclusive,
        "first_line_number": bundle.first_line_number,
        "first_segment_index": bundle.first_segment_index,
        "last_line_number": bundle.last_line_number,
        "last_segment_index": bundle.last_segment_index,
        "segment_count": bundle.segment_count,
        "phonemes": bundle.phonemes,
        "pressure": bundle.pressure,
        "oversized_single_segment": bundle.oversized_single_segment,
        "closed_by_segment_cap": bundle.closed_by_segment_cap,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _write_documents_tsv(
    path: Path, *, scan_rows: Sequence[dict[str, Any]], bundles: Sequence[BundleRecord],
) -> None:
    bundle_map: dict[int, list[BundleRecord]] = {}
    for bundle in bundles:
        bundle_map.setdefault(bundle.document_index, []).append(bundle)
    fields = (
        "document_index", "relative_path", "segments", "phonemes", "pressure",
        "max_segment_phonemes", "bundles", "max_bundle_pressure",
        "max_bundle_segments", "oversized_single_segment_bundles",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in scan_rows:
            doc_bundles = bundle_map.get(int(row["document_index"]), [])
            writer.writerow({
                "document_index": row["document_index"],
                "relative_path": row["relative_path"],
                "segments": row["segments"],
                "phonemes": row["phonemes"],
                "pressure": row["pressure"],
                "max_segment_phonemes": row["max_segment_phonemes"],
                "bundles": len(doc_bundles),
                "max_bundle_pressure": max((b.pressure for b in doc_bundles), default=0),
                "max_bundle_segments": max((b.segment_count for b in doc_bundles), default=0),
                "oversized_single_segment_bundles": sum(b.oversized_single_segment for b in doc_bundles),
            })


def _plan_digest(
    bundles: Sequence[BundleRecord], *, scan_signature: str,
    target_pressure: int, max_segments_per_bundle: int,
) -> str:
    digest = hashlib.sha256()
    digest.update(f"{scan_signature}\n{target_pressure}\n{max_segments_per_bundle}\n".encode("ascii"))
    for b in bundles:
        digest.update((
            f"{b.document_index}\t{b.relative_path}\t{b.bundle_index}\t"
            f"{b.first_segment_ordinal}\t{b.last_segment_ordinal_exclusive}\t"
            f"{b.segment_count}\t{b.phonemes}\t{b.pressure}\n"
        ).encode("utf-8"))
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static S1M2 execution-bundle candidate plans")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basis-cell", default=None)
    parser.add_argument("--target-bundles", type=int, nargs="+", default=list(DEFAULT_TARGET_BUNDLES))
    parser.add_argument("--max-segments-per-bundle", type=int, default=DEFAULT_MAX_SEGMENTS_PER_BUNDLE)
    parser.add_argument("--max-segment-tokens", type=int, default=DEFAULT_MAX_SEGMENT_TOKENS)
    parser.add_argument(
        "--max-lines-per-document", type=int, default=None,
        help="Unset for full docs; use 256 only to model old Round1",
    )
    args = parser.parse_args()

    if args.max_segments_per_bundle < 1 or args.max_segment_tokens < 1:
        parser.error("segment limits must be >= 1")
    if args.max_lines_per_document is not None and args.max_lines_per_document < 1:
        parser.error("--max-lines-per-document must be >= 1")
    if any(v < 1 for v in args.target_bundles) or len(set(args.target_bundles)) != len(args.target_bundles):
        parser.error("--target-bundles must contain unique positive integers")

    repo_root = args.repo_root.resolve()
    config_path = _resolve(repo_root, args.config)
    output_dir = _resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = ContinuousSelectionConfig.load(config_path, repo_root=repo_root)
    basis_cell = args.basis_cell or config.selection_basis_cell
    matches = [item for item in config.inputs if item.cell_id == basis_cell]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one configured basis cell {basis_cell!r}")
    basis = matches[0]
    if basis.condition != "continuous":
        raise ValueError("This planner accepts continuous cells only")
    rows = _manifest_rows(basis, repo_root)

    print("=" * 92)
    print("S1M2 STATIC EXECUTION-BUNDLE PLANNER")
    print("=" * 92)
    print(f"basis cell                 : {basis.cell_id}")
    print(f"script                     : {basis.script}")
    print(f"documents                  : {len(rows)}")
    print(f"max lines/document         : {args.max_lines_per_document or 'FULL'}")
    print(f"max segment tokens         : {args.max_segment_tokens}")
    print("scanning existing ObservedSegments...")

    by_document, scan = _scan_segments(
        repo_root=repo_root, rows=rows, script=basis.script,
        max_segment_tokens=args.max_segment_tokens,
        max_lines_per_document=args.max_lines_per_document,
    )

    sig = hashlib.sha256()
    for value in (
        scan["segment_sequence_sha256"], scan["representation_set_sha256"],
        basis.cell_id, basis.script, str(args.max_segment_tokens),
        str(args.max_lines_per_document),
    ):
        sig.update(str(value).encode("utf-8")); sig.update(b"\n")
    scan_signature = sig.hexdigest()

    scan_summary = {
        "schema_version": "sktlm-s1m2-execution-bundle-scan/v1",
        "planner_implementation": PLANNER_IMPLEMENTATION,
        "segment_enumerator": "sktlm.latent.training._iter_document_segments",
        "git_head": _git_head(repo_root),
        "git_worktree_dirty": _git_dirty(repo_root),
        "config": str(config_path.relative_to(repo_root)),
        "config_sha256": _sha256(config_path),
        "cell_id": basis.cell_id,
        "script": basis.script,
        "condition": basis.condition,
        "manifest": str(basis.manifest.relative_to(repo_root)),
        "manifest_sha256": basis.manifest_sha256,
        "max_segment_tokens": args.max_segment_tokens,
        "max_lines_per_document": args.max_lines_per_document,
        "pressure_definition": "observed_segment_phonemes_squared",
        "segment_atomicity": "complete_existing_ObservedSegment_never_split",
        "cross_document_bundles": False,
        "scan_signature_sha256": scan_signature,
        **{k: v for k, v in scan.items() if k != "documents_detail"},
    }
    _write_json(output_dir / "scan_summary.json", scan_summary)

    print(f"segments                   : {scan['segments']:,}")
    print(f"phonemes                   : {scan['phonemes']:,}")
    print(f"total pressure             : {scan['pressure']:,}")
    sp = scan["segment_phonemes"]
    print(f"segment phonemes p50/p95/max: {sp['p50']:,} / {sp['p95']:,} / {sp['max']:,}")
    print()

    candidate_summaries: list[dict[str, Any]] = []
    for target_count in args.target_bundles:
        bundles, summary = _plan(
            by_document,
            target_bundle_count=target_count,
            total_pressure=int(scan["pressure"]),
            max_segments_per_bundle=args.max_segments_per_bundle,
        )
        plan_sha = _plan_digest(
            bundles, scan_signature=scan_signature,
            target_pressure=int(summary["target_pressure"]),
            max_segments_per_bundle=args.max_segments_per_bundle,
        )
        candidate_dir = output_dir / f"candidate_{target_count:06d}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        plan_summary = {
            "schema_version": "sktlm-s1m2-execution-bundle-plan/v1",
            "planner_implementation": PLANNER_IMPLEMENTATION,
            "scan_signature_sha256": scan_signature,
            "plan_sha256": plan_sha,
            "cell_id": basis.cell_id,
            "script": basis.script,
            "condition": basis.condition,
            "pressure_definition": "observed_segment_phonemes_squared",
            "packing_rule": "within-document contiguous closest-to-target greedy; complete ObservedSegments only",
            "max_segments_per_bundle": args.max_segments_per_bundle,
            "max_segment_tokens": args.max_segment_tokens,
            "max_lines_per_document": args.max_lines_per_document,
            "total_segments": scan["segments"],
            "total_phonemes": scan["phonemes"],
            "total_pressure": scan["pressure"],
            **summary,
        }
        _write_json(candidate_dir / "summary.json", plan_summary)
        _write_jsonl(candidate_dir / "bundles.jsonl", (_bundle_payload(b) for b in bundles))
        _write_documents_tsv(candidate_dir / "documents.tsv", scan_rows=scan["documents_detail"], bundles=bundles)
        candidate_summaries.append(plan_summary)

        bp, bs = summary["bundle_pressure"], summary["bundle_segments"]
        print(f"candidate target bundles    : {target_count:,}")
        print(f"  actual bundles            : {summary['actual_bundle_count']:,}")
        print(f"  target pressure           : {summary['target_pressure']:,}")
        print(f"  bundle pressure p50/p95/max: {bp['p50']:,} / {bp['p95']:,} / {bp['max']:,}")
        print(f"  bundle segments p50/p95/max: {bs['p50']:,} / {bs['p95']:,} / {bs['max']:,}")
        print(f"  <0.5x / >1.5x target      : {summary['bundles_below_half_target_pressure']:,} / {summary['bundles_above_150pct_target_pressure']:,}")
        print(f"  giant single-segment      : {summary['oversized_single_segment_bundles']:,}")
        print(f"  closed by segment cap     : {summary['segment_cap_closed_bundles']:,}")
        print(f"  plan sha256               : {plan_sha}")
        print()

    _write_json(output_dir / "candidates_summary.json", {
        "schema_version": "sktlm-s1m2-execution-bundle-candidates/v1",
        "scan_signature_sha256": scan_signature,
        "candidates": candidate_summaries,
    })
    print("outputs:")
    print(f"  {output_dir / 'scan_summary.json'}")
    print(f"  {output_dir / 'candidates_summary.json'}")
    for target_count in args.target_bundles:
        print(f"  {output_dir / f'candidate_{target_count:06d}'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

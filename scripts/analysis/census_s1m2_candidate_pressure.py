#!/usr/bin/env python3
"""
Read-only full-corpus census of S1M2 candidate pressure.

This script deliberately stops after production candidate construction.

It:
- uses the production document loader and segment iterator;
- uses the production S1M2 lazy candidate builder;
- performs no inference;
- performs no EM / learner updates;
- does not alter max_internal_matches semantics;
- records both segment-level aggregate raw counts and the lattice-level
  raw counts to which max_internal_matches actually applies.

Default target:
    frozen M0 / Devanagari / continuous
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.lazy_candidates import build_lazy_candidate_graph
from sktlm.latent.training import (
    S1M2_MODEL,
    TrainingConfig,
    _iter_document_segments,
    load_documents,
)


DEFAULT_MANIFEST = Path("data/manifests/representations.csv")
DEFAULT_OUTPUT = Path(
    "artifacts/s1m2_candidate_pressure/full_m0_devanagari_continuous"
)
DEFAULT_RULES = Path("data/rules/external_sandhi.tsv")

THRESHOLDS = (512, 1024, 2048, 4096, 8192, 16384)

ROUND2_STRESS_EXPECTED = {
    "segments": 241,
    "overflow_segments": 34,
    "raw_total": 59554,
    "raw_max": 2484,
    "power2_histogram": {
        0: 1,
        4: 1,
        8: 2,
        16: 17,
        32: 23,
        64: 62,
        128: 35,
        256: 31,
        512: 35,
        1024: 22,
        2048: 11,
        4096: 1,
    },
}


def resolve(repo_root: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_output(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def power2_upper_bucket(value: int) -> int:
    """
    Match the telemetry-style upper-bound power-of-two histogram.

    Examples:
        0 -> 0
        1 -> 1
        3 -> 4
        512 -> 512
        513 -> 1024
        2484 -> 4096
    """
    if value <= 0:
        return 0
    return 1 << (value - 1).bit_length()


def power2_histogram(exact: Counter[int]) -> Counter[int]:
    result: Counter[int] = Counter()
    for value, count in exact.items():
        result[power2_upper_bucket(value)] += count
    return result


def percentile_from_hist(
    histogram: Counter[int],
    total_count: int,
    quantile: float,
) -> int | None:
    """Exact nearest-rank percentile from an integer frequency table."""
    if total_count <= 0:
        return None
    rank = max(1, math.ceil(quantile * total_count))
    cumulative = 0
    for value in sorted(histogram):
        cumulative += histogram[value]
        if cumulative >= rank:
            return value
    raise AssertionError("histogram count does not match total_count")


def distribution_summary(
    histogram: Counter[int],
    *,
    total_count: int,
    total_value: int,
    maximum: int,
) -> dict[str, Any]:
    if total_count == 0:
        return {
            "count": 0,
            "total": 0,
            "min": None,
            "mean": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "p99_9": None,
            "max": None,
            "threshold_exceedances": {
                f"gt_{threshold}": 0 for threshold in THRESHOLDS
            },
        }

    minimum = min(histogram)
    return {
        "count": total_count,
        "total": total_value,
        "min": minimum,
        "mean": total_value / total_count,
        "p50": percentile_from_hist(histogram, total_count, 0.50),
        "p90": percentile_from_hist(histogram, total_count, 0.90),
        "p95": percentile_from_hist(histogram, total_count, 0.95),
        "p99": percentile_from_hist(histogram, total_count, 0.99),
        "p99_9": percentile_from_hist(histogram, total_count, 0.999),
        "max": maximum,
        "threshold_exceedances": {
            f"gt_{threshold}": sum(
                count
                for value, count in histogram.items()
                if value > threshold
            )
            for threshold in THRESHOLDS
        },
    }


def write_histogram(
    path: Path,
    exact_histogram: Counter[int],
) -> None:
    upper = power2_histogram(exact_histogram)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(
            handle,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writerow(
            [
                "raw_internal_matches",
                "exact_count",
                "power2_upper_bucket",
            ]
        )
        for value in sorted(exact_histogram):
            writer.writerow(
                [
                    value,
                    exact_histogram[value],
                    power2_upper_bucket(value),
                ]
            )

    upper_path = path.with_name(
        path.stem + "_power2.tsv"
    )
    with upper_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(
            handle,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writerow(["upper_bound", "count"])
        for bucket in sorted(upper):
            writer.writerow([bucket, upper[bucket]])


def validate_round2_stress(
    *,
    segments: int,
    overflow_segments: int,
    raw_total: int,
    raw_max: int,
    segment_histogram: Counter[int],
) -> None:
    failures: list[str] = []

    expected = ROUND2_STRESS_EXPECTED

    checks = {
        "segments": segments,
        "overflow_segments": overflow_segments,
        "raw_total": raw_total,
        "raw_max": raw_max,
    }

    for name, actual in checks.items():
        if actual != expected[name]:
            failures.append(
                f"{name}: expected {expected[name]}, got {actual}"
            )

    actual_power2 = dict(
        sorted(power2_histogram(segment_histogram).items())
    )
    expected_power2 = expected["power2_histogram"]

    if actual_power2 != expected_power2:
        failures.append(
            "power2 histogram differs:\n"
            f"expected={expected_power2}\n"
            f"actual={actual_power2}"
        )

    if failures:
        raise RuntimeError(
            "ROUND2_STRESS_VALIDATION=FAIL\n"
            + "\n".join(failures)
        )

    print("ROUND2_STRESS_VALIDATION=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only S1M2 raw candidate-pressure census."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument(
        "--document-list",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--script",
        default="devanagari",
    )
    parser.add_argument(
        "--condition",
        default="continuous",
    )
    parser.add_argument(
        "--max-internal-matches",
        type=int,
        default=512,
    )
    parser.add_argument(
        "--max-segment-tokens",
        type=int,
        default=128,
    )
    parser.add_argument(
        "--max-lines-per-document",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=100,
        help="Number of highest-pressure segments retained in summary.json.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Print progress every N completed documents.",
    )
    parser.add_argument(
        "--expect-round2-stress",
        action="store_true",
        help=(
            "Require exact reproduction of the frozen Round2 "
            "stress candidate metrics."
        ),
    )
    args = parser.parse_args()

    if args.max_internal_matches < 1:
        raise ValueError("--max-internal-matches must be >= 1")
    if args.max_segment_tokens < 1:
        raise ValueError("--max-segment-tokens must be >= 1")
    if args.top_k < 1:
        raise ValueError("--top-k must be >= 1")
    if args.progress_every < 1:
        raise ValueError("--progress-every must be >= 1")

    repo_root = args.repo_root.resolve()
    manifest = resolve(repo_root, args.manifest)
    document_list = resolve(repo_root, args.document_list)
    output_dir = resolve(repo_root, args.output_dir)

    assert manifest is not None
    assert output_dir is not None

    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    if document_list is not None and not document_list.is_file():
        raise FileNotFoundError(document_list)

    output_dir.mkdir(parents=True, exist_ok=True)

    rules_path = resolve(repo_root, DEFAULT_RULES)
    assert rules_path is not None

    grammar = StructuredSandhiGrammar.from_default_inventory()

    config = TrainingConfig(
        manifest=manifest,
        document_list=document_list,
        model=S1M2_MODEL,
        script=args.script,
        condition=args.condition,
        passes=1,
        workers=1,
        max_internal_matches=args.max_internal_matches,
        max_segment_tokens=args.max_segment_tokens,
        max_lines_per_document=args.max_lines_per_document,
        max_documents=args.max_documents,
    )

    documents = load_documents(
        manifest,
        repo_root=repo_root,
        max_documents=args.max_documents,
        document_list=document_list,
        script=args.script,
        condition=args.condition,
    )

    if not documents:
        raise RuntimeError("No documents selected.")

    git_sha = git_output(repo_root, "rev-parse", "HEAD")
    git_branch = git_output(repo_root, "branch", "--show-current")
    dirty = bool(git_output(repo_root, "status", "--porcelain"))

    start_time = time.perf_counter()

    total_documents = 0
    total_lines_seen: set[tuple[str, int]] = set()
    total_segments = 0

    total_segment_raw = 0
    max_segment_raw = 0
    segment_exact_hist: Counter[int] = Counter()

    total_lattice_raw = 0
    max_lattice_raw = 0
    lattice_count = 0
    lattice_exact_hist: Counter[int] = Counter()

    total_retained_raw = 0

    overflow_segments = 0
    overflow_tokens = 0
    overflow_lattices = 0

    freeze_ids: set[str] = set()

    # Heap entries:
    # (segment_raw, monotonic_sequence, compact_row)
    top_heap: list[tuple[int, int, dict[str, Any]]] = []
    sequence = 0

    offenders_path = output_dir / "offenders.tsv"
    documents_path = output_dir / "document_summary.tsv"

    offender_fields = [
        "relative_path",
        "document_id",
        "line_number",
        "segment_index",
        "source_start",
        "source_end",
        "characters",
        "tokens",
        "phonemes",
        "segment_raw_internal_matches",
        "segment_retained_internal_matches",
        "max_lattice_raw_internal_matches",
        "overflow_lattice_raw_max",
        "token_lattices",
        "overflow_lattices",
        "overflowed_tokens",
        "overflow_token_indices",
        "overflow_token_raw_max",
        "boundary_options",
        "factors",
        "merged_factors",
        "lattice_nodes",
    ]

    document_fields = [
        "relative_path",
        "document_id",
        "lines",
        "segments",
        "token_lattices",
        "raw_internal_matches",
        "retained_internal_matches",
        "overflow_segments",
        "overflowed_tokens",
        "overflow_lattices",
        "max_segment_raw_internal_matches",
        "max_lattice_raw_internal_matches",
        "max_phonemes_per_segment",
        "max_tokens_per_segment",
    ]

    with (
        offenders_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as offenders_handle,
        documents_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as documents_handle,
    ):
        offender_writer = csv.DictWriter(
            offenders_handle,
            fieldnames=offender_fields,
            delimiter="\t",
            lineterminator="\n",
        )
        offender_writer.writeheader()

        document_writer = csv.DictWriter(
            documents_handle,
            fieldnames=document_fields,
            delimiter="\t",
            lineterminator="\n",
        )
        document_writer.writeheader()

        for document_index, document in enumerate(documents):
            total_documents += 1
            freeze_ids.add(document.freeze_id)

            doc_lines: set[int] = set()
            doc_segments = 0
            doc_lattices = 0
            doc_raw = 0
            doc_retained = 0
            doc_overflow_segments = 0
            doc_overflow_tokens = 0
            doc_overflow_lattices = 0
            doc_max_segment_raw = 0
            doc_max_lattice_raw = 0
            doc_max_phonemes = 0
            doc_max_tokens = 0

            for (
                line_number,
                segment_index,
                segment,
            ) in _iter_document_segments(document, config):
                total_segments += 1
                doc_segments += 1
                doc_lines.add(line_number)
                total_lines_seen.add(
                    (document.relative_path, line_number)
                )

                graph = build_lazy_candidate_graph(
                    segment,
                    grammar,
                    config.candidate_config,
                )

                lattices = [
                    factor.lattice
                    for factor in graph.factors
                    if factor.lattice is not None
                ]

                segment_raw = sum(
                    lattice.raw_internal_matches
                    for lattice in lattices
                )
                segment_retained = sum(
                    lattice.retained_internal_matches
                    for lattice in lattices
                )
                segment_lattice_max = max(
                    (
                        lattice.raw_internal_matches
                        for lattice in lattices
                    ),
                    default=0,
                )

                overflowing_lattices = [
                    lattice
                    for lattice in lattices
                    if lattice.overflowed
                ]
                overflow_lattice_max = max(
                    (
                        lattice.raw_internal_matches
                        for lattice in overflowing_lattices
                    ),
                    default=0,
                )

                token_raw_max: dict[int, int] = {}
                overflow_token_indices: set[int] = set()

                for factor in graph.factors:
                    lattice = factor.lattice
                    if lattice is None:
                        continue

                    lattice_count += 1
                    doc_lattices += 1

                    raw = lattice.raw_internal_matches
                    total_lattice_raw += raw
                    lattice_exact_hist[raw] += 1

                    if raw > max_lattice_raw:
                        max_lattice_raw = raw
                    if raw > doc_max_lattice_raw:
                        doc_max_lattice_raw = raw

                    if lattice.overflowed:
                        overflow_lattices += 1
                        doc_overflow_lattices += 1
                        overflow_token_indices.add(
                            factor.start_token
                        )
                        token_raw_max[factor.start_token] = max(
                            token_raw_max.get(
                                factor.start_token,
                                0,
                            ),
                            raw,
                        )

                segment_exact_hist[segment_raw] += 1
                total_segment_raw += segment_raw
                total_retained_raw += segment_retained

                max_segment_raw = max(
                    max_segment_raw,
                    segment_raw,
                )
                doc_max_segment_raw = max(
                    doc_max_segment_raw,
                    segment_raw,
                )

                phonemes = sum(
                    len(token.phonemes)
                    for token in segment.tokens
                )
                tokens = len(segment.tokens)

                doc_max_phonemes = max(
                    doc_max_phonemes,
                    phonemes,
                )
                doc_max_tokens = max(
                    doc_max_tokens,
                    tokens,
                )

                doc_raw += segment_raw
                doc_retained += segment_retained

                if graph.overflowed_tokens:
                    overflow_segments += 1
                    overflow_tokens += graph.overflowed_tokens
                    doc_overflow_segments += 1
                    doc_overflow_tokens += graph.overflowed_tokens

                boundary_options = sum(
                    len(options)
                    for options in graph.boundary_options
                )
                merged_factors = sum(
                    int(factor.is_merge)
                    for factor in graph.factors
                )
                lattice_nodes = sum(
                    len(lattice.nodes)
                    for lattice in lattices
                )

                compact_row = {
                    "relative_path": document.relative_path,
                    "document_id": document.document_id,
                    "line_number": line_number,
                    "segment_index": segment_index,
                    "source_start": segment.source_start,
                    "source_end": segment.source_end,
                    "characters": len(segment.written),
                    "tokens": tokens,
                    "phonemes": phonemes,
                    "segment_raw_internal_matches": segment_raw,
                    "segment_retained_internal_matches": (
                        segment_retained
                    ),
                    "max_lattice_raw_internal_matches": (
                        segment_lattice_max
                    ),
                    "overflow_lattice_raw_max": (
                        overflow_lattice_max
                    ),
                    "token_lattices": len(lattices),
                    "overflow_lattices": len(
                        overflowing_lattices
                    ),
                    "overflowed_tokens": (
                        graph.overflowed_tokens
                    ),
                    "overflow_token_indices": ",".join(
                        str(index)
                        for index in sorted(
                            overflow_token_indices
                        )
                    ),
                    "overflow_token_raw_max": ",".join(
                        f"{index}:{token_raw_max[index]}"
                        for index in sorted(token_raw_max)
                    ),
                    "boundary_options": boundary_options,
                    "factors": len(graph.factors),
                    "merged_factors": merged_factors,
                    "lattice_nodes": lattice_nodes,
                }

                if graph.overflowed_tokens:
                    offender_writer.writerow(compact_row)

                sequence += 1
                heap_item = (
                    segment_raw,
                    sequence,
                    compact_row,
                )
                if len(top_heap) < args.top_k:
                    heapq.heappush(top_heap, heap_item)
                elif segment_raw > top_heap[0][0]:
                    heapq.heapreplace(top_heap, heap_item)

            document_writer.writerow(
                {
                    "relative_path": document.relative_path,
                    "document_id": document.document_id,
                    "lines": len(doc_lines),
                    "segments": doc_segments,
                    "token_lattices": doc_lattices,
                    "raw_internal_matches": doc_raw,
                    "retained_internal_matches": (
                        doc_retained
                    ),
                    "overflow_segments": (
                        doc_overflow_segments
                    ),
                    "overflowed_tokens": (
                        doc_overflow_tokens
                    ),
                    "overflow_lattices": (
                        doc_overflow_lattices
                    ),
                    "max_segment_raw_internal_matches": (
                        doc_max_segment_raw
                    ),
                    "max_lattice_raw_internal_matches": (
                        doc_max_lattice_raw
                    ),
                    "max_phonemes_per_segment": (
                        doc_max_phonemes
                    ),
                    "max_tokens_per_segment": (
                        doc_max_tokens
                    ),
                }
            )

            if (
                total_documents % args.progress_every == 0
                or total_documents == len(documents)
            ):
                elapsed = time.perf_counter() - start_time
                print(
                    "PROGRESS "
                    f"documents={total_documents}/{len(documents)} "
                    f"segments={total_segments} "
                    f"overflow_segments={overflow_segments} "
                    f"overflow_tokens={overflow_tokens} "
                    f"max_segment_raw={max_segment_raw} "
                    f"max_lattice_raw={max_lattice_raw} "
                    f"elapsed_seconds={elapsed:.1f}",
                    flush=True,
                )

    elapsed = time.perf_counter() - start_time

    write_histogram(
        output_dir / "segment_histogram.tsv",
        segment_exact_hist,
    )
    write_histogram(
        output_dir / "lattice_histogram.tsv",
        lattice_exact_hist,
    )

    top_segments = [
        row
        for _raw, _seq, row in sorted(
            top_heap,
            key=lambda item: (
                -item[0],
                item[2]["relative_path"],
                item[2]["line_number"],
                item[2]["segment_index"],
            ),
        )
    ]

    summary = {
        "schema_version": (
            "sktlm-s1m2-candidate-pressure-census/v1"
        ),
        "classification": "read_only_candidate_construction_only",
        "git": {
            "sha": git_sha,
            "branch": git_branch,
            "dirty_worktree": dirty,
        },
        "input": {
            "manifest": str(
                args.manifest.as_posix()
            ),
            "manifest_sha256": sha256(manifest),
            "document_list": (
                None
                if args.document_list is None
                else args.document_list.as_posix()
            ),
            "document_list_sha256": (
                None
                if document_list is None
                else sha256(document_list)
            ),
            "rules": DEFAULT_RULES.as_posix(),
            "rules_sha256": (
                sha256(rules_path)
                if rules_path.is_file()
                else None
            ),
            "freeze_ids": sorted(freeze_ids),
            "script": args.script,
            "condition": args.condition,
            "max_internal_matches": (
                args.max_internal_matches
            ),
            "max_segment_tokens": (
                args.max_segment_tokens
            ),
            "max_lines_per_document": (
                args.max_lines_per_document
            ),
        },
        "scope": {
            "documents": total_documents,
            "lines": len(total_lines_seen),
            "segments": total_segments,
        },
        "production_overflow": {
            "segments": overflow_segments,
            "tokens": overflow_tokens,
            "lattices": overflow_lattices,
        },
        "segment_raw_internal_matches": (
            distribution_summary(
                segment_exact_hist,
                total_count=total_segments,
                total_value=total_segment_raw,
                maximum=max_segment_raw,
            )
        ),
        "lattice_raw_internal_matches": (
            distribution_summary(
                lattice_exact_hist,
                total_count=lattice_count,
                total_value=total_lattice_raw,
                maximum=max_lattice_raw,
            )
        ),
        "retained_internal_matches_total": (
            total_retained_raw
        ),
        "top_segments_by_raw_internal_matches": (
            top_segments
        ),
        "runtime": {
            "elapsed_seconds": elapsed,
            "segments_per_second": (
                total_segments / elapsed
                if elapsed > 0
                else None
            ),
        },
        "notes": {
            "segment_metric": (
                "Sum of raw_internal_matches across all "
                "token lattices/factors in one observed segment; "
                "this matches production segment telemetry."
            ),
            "lattice_metric": (
                "Raw internal matches for one LazyTokenLattice. "
                "max_internal_matches is applied at this level, "
                "so this distribution is the relevant one for "
                "ceiling/remedy decisions."
            ),
            "overflow_semantics": (
                "production_overflow is taken directly from "
                "the production lazy graph/lattice overflow flags; "
                "it is not inferred from the segment aggregate."
            ),
        },
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )

    if args.expect_round2_stress:
        validate_round2_stress(
            segments=total_segments,
            overflow_segments=overflow_segments,
            raw_total=total_segment_raw,
            raw_max=max_segment_raw,
            segment_histogram=segment_exact_hist,
        )

    print()
    print("CENSUS_COMPLETE")
    print(f"documents={total_documents}")
    print(f"segments={total_segments}")
    print(f"overflow_segments={overflow_segments}")
    print(f"overflow_tokens={overflow_tokens}")
    print(f"overflow_lattices={overflow_lattices}")
    print(f"segment_raw_total={total_segment_raw}")
    print(f"max_segment_raw={max_segment_raw}")
    print(f"max_lattice_raw={max_lattice_raw}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"summary={summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
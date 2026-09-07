#!/usr/bin/env python3
"""Bounded paired measurement of retained versus promptly retired S1M2 shards."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import sktlm.latent.training as training
from sktlm.latent.training import EXPECTED_FREEZE_ID, S1M2_MODEL, TrainingConfig
from sktlm.representations.devanagari import transliterate_iast_to_devanagari


SCIENTIFIC_ARTIFACTS = (
    "iteration_metrics.json",
    "piece_inventory.tsv",
    "lexical_diagnostics.tsv",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "rule_usage.tsv",
    "summary.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fixture(root: Path, documents: int) -> Path:
    manifest = root / "representations.csv"
    text = transliterate_iast_to_devanagari(
        "devo'pi rama iti rama uta maitra pautra dakani batani ramani"
    ).replace(" ", "") + "।\n"
    rows: list[dict[str, str]] = []
    for index in range(documents):
        corpus = root / f"document-{index:04d}.txt"
        corpus.write_text(text, encoding="utf-8", newline="")
        rows.append(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": f"bounded/document-{index:04d}.txt",
                "script": "devanagari",
                "condition": "continuous",
                "representation_path": corpus.as_posix(),
            }
        )
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def _run(root: Path, manifest: Path, run_id: str) -> tuple[Path, float, dict[str, Any]]:
    started = time.perf_counter()
    result = training.run_training(
        TrainingConfig(
            manifest=manifest,
            output_root=root / "runs",
            run_id=run_id,
            model=S1M2_MODEL,
            script="devanagari",
            condition="continuous",
            passes=1,
            workers=2,
            analysis_top_k=4,
            flush_types=128,
            piece_max_length=3,
        ),
        repo_root=Path("."),
    )
    elapsed = time.perf_counter() - started
    return result.run_dir, elapsed, result.runtime


def benchmark(documents: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="sktlm-opt15-lifetime-") as raw_root:
        root = Path(raw_root)
        manifest = _fixture(root, documents)
        retire = training._retire_inspection_shard

        def retain_shard(*_: object, **__: object) -> None:
            return None

        training._retire_inspection_shard = retain_shard
        try:
            baseline_dir, baseline_seconds, baseline_runtime = _run(
                root, manifest, "retain-all"
            )
        finally:
            training._retire_inspection_shard = retire
        candidate_dir, candidate_seconds, candidate_runtime = _run(
            root, manifest, "retire-after-reduction"
        )
        comparison = {
            name: {
                "baseline_sha256": _sha256(baseline_dir / name),
                "candidate_sha256": _sha256(candidate_dir / name),
            }
            for name in SCIENTIFIC_ARTIFACTS
        }
        exact = all(
            item["baseline_sha256"] == item["candidate_sha256"]
            for item in comparison.values()
        )
        baseline_peak = int(
            baseline_runtime["gauges"]["artifact_transient_bytes"]
        )
        candidate_peak = int(
            candidate_runtime["gauges"]["artifact_transient_bytes"]
        )
        return {
            "schema_version": "sktlm-s1m2-opt15-lifecycle-benchmark/v1",
            "documents": documents,
            "workers": 2,
            "runs_per_variant": 1,
            "frontend": "devanagari",
            "condition": "continuous",
            "baseline": {
                "policy": "retain every reduced inspection shard until completion",
                "peak_bytes": baseline_peak,
                "seconds": baseline_seconds,
            },
            "candidate": {
                "policy": "retire each shard after successful canonical reduction",
                "peak_bytes": candidate_peak,
                "seconds": candidate_seconds,
                "retired_shard_bytes": int(
                    candidate_runtime["counters"]["inspection_shard_bytes_retired"]
                ),
            },
            "peak_reduction_percent": 100.0
            * (baseline_peak - candidate_peak)
            / baseline_peak,
            "runtime_change_percent": 100.0
            * (candidate_seconds - baseline_seconds)
            / baseline_seconds,
            "scientific_artifacts_exact": exact,
            "scientific_artifacts": comparison,
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=int, default=24)
    args = parser.parse_args()
    if args.documents < 8:
        parser.error("--documents must be at least 8")
    print(json.dumps(benchmark(args.documents), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

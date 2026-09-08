#!/usr/bin/env python3
"""Bounded-memory integrity and exact-identity audit for latent run artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


SCIENTIFIC_FILES = (
    "iteration_metrics.json",
    "summary.json",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "latent_lexicon.tsv",
    "rule_usage.tsv",
)
S1M2_SCIENTIFIC_FILES = (
    "iteration_metrics.json",
    "piece_inventory.tsv",
    "lexical_diagnostics.tsv",
    "analyses.jsonl",
    "boundary_posteriors.jsonl",
    "rule_usage.tsv",
    "summary.json",
)
BASE_REQUIRED_FILES = (
    "timing_metrics.json",
    "checkpoint.json",
    "config.json",
    "provenance.json",
    "learner.sqlite",
    *SCIENTIFIC_FILES,
)
BENCHMARK_METRICS_FILE = "benchmark_metrics.json"
VOCABULARY_FILES = ("vocabulary_budget.json", "vocabulary.tsv")
FORMAL_SCRIPTS = frozenset({"iast", "devanagari"})
FORMAL_CONDITIONS = frozenset({"surface_word", "legacy_joined", "continuous"})
EXPECTED_FREEZE_ID = (
    "9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40"
)
EXPECTED_RULES = 1_218
EXPECTED_HYPERPARAMETERS = {
    "lexical_alpha": 0.1,
    "complexity_weight": 0.5,
    "complexity_tau": 1.0,
    "whitespace_merge_penalty": 8.0,
    "analysis_top_k": 8,
    "max_internal_matches": 512,
    "max_segment_tokens": 128,
}
EXPECTED_S1M2_HYPERPARAMETERS = {
    **EXPECTED_HYPERPARAMETERS,
    "piece_max_length": 8,
    "piece_boundary_probability": 0.5,
    "piece_alpha": 0.1,
    "piece_complexity_weight": 0.5,
    "piece_complexity_kappa": 1.0,
    "piece_complexity_beta": 0.25,
    "piece_complexity_tau": 1.0,
    "piece_base_stop_probability": 0.5,
    "piece_min_reuse_occurrences": 2,
    "piece_support_epsilon": 0.0,
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_database(path: Path, model: str = "latent_lexicon_v1") -> dict[str, Any]:
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if model == "reusable_pieces_v1":
            piece_lexicon = connection.execute(
                "SELECT COUNT(*), SUM(expected_count) FROM piece_lexicon"
            ).fetchone()
            tables = sorted(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )
        else:
            lexicon = connection.execute(
                "SELECT COUNT(*), SUM(expected_count) FROM lexicon"
            ).fetchone()
            inspection = connection.execute(
                "SELECT COUNT(*), SUM(expected_count) FROM inspection_counts"
            ).fetchone()
            surfaces = connection.execute("SELECT COUNT(*) FROM surface_usage").fetchone()
            contexts = connection.execute("SELECT COUNT(*) FROM context_usage").fetchone()
    finally:
        connection.close()
    if model == "reusable_pieces_v1":
        return {
            "quick_check": quick_check,
            "piece_lexicon_rows": piece_lexicon[0],
            "piece_lexicon_expected_count": piece_lexicon[1],
            "tables": tables,
        }
    return {
        "quick_check": quick_check,
        "lexicon_rows": lexicon[0],
        "lexicon_expected_count": lexicon[1],
        "inspection_rows": inspection[0],
        "inspection_expected_count": inspection[1],
        "surface_usage_rows": surfaces[0],
        "context_usage_rows": contexts[0],
    }


def _direct_full_configuration(config: dict[str, Any]) -> bool:
    return all(
        config.get(name) is None
        for name in ("document_list", "max_documents", "max_lines_per_document")
    )


def _audit_vocabulary(
    run_dir: Path,
    config: dict[str, Any],
    checkpoint: dict[str, Any],
    provenance: dict[str, Any],
    summary: dict[str, Any],
    failures: list[str],
) -> dict[str, Any] | None:
    budget = config.get("vocab_budget")
    if budget is None:
        return None
    missing = [name for name in VOCABULARY_FILES if not (run_dir / name).is_file()]
    if missing:
        failures.append(f"missing fixed-vocabulary files: {missing}")
        return None

    metadata = load_json(run_dir / "vocabulary_budget.json")
    if metadata.get("total_budget") != budget:
        failures.append("vocabulary budget does not match config")
    if metadata.get("base_unit_count") != 50:
        failures.append("vocabulary base-unit count is not 50")
    if metadata.get("status") != "frozen":
        failures.append("vocabulary is not frozen")
    if metadata.get("surface_realizations_consume_slots") is not False:
        failures.append("surface realizations incorrectly consume vocabulary slots")

    with (run_dir / "vocabulary.tsv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    keys = [row.get("form_key", "") for row in rows]
    ranks = [row.get("rank", "") for row in rows]
    if not keys or any(not key for key in keys):
        failures.append("vocabulary.tsv contains an empty or missing form_key")
    if len(keys) != len(set(keys)):
        failures.append("vocabulary.tsv contains duplicate form_key identities")
    if ranks != [str(index) for index in range(1, len(rows) + 1)]:
        failures.append("vocabulary.tsv ranks are not contiguous from 1")
    if sum(row.get("kind") == "base" for row in rows) != 50:
        failures.append("vocabulary.tsv does not contain exactly 50 base units")
    if metadata.get("actual_vocabulary_size") != len(rows):
        failures.append("vocabulary.tsv size does not match vocabulary metadata")
    if len(rows) > int(budget):
        failures.append("vocabulary.tsv exceeds the configured budget")
    allowed_sha = hashlib.sha256(
        "".join(f"{key}\n" for key in sorted(keys)).encode("utf-8")
    ).hexdigest()
    if metadata.get("allowed_key_sha256") != allowed_sha:
        failures.append("vocabulary allowed-key SHA-256 does not match vocabulary.tsv")
    for label, payload in (
        ("checkpoint", checkpoint.get("vocabulary_budget")),
        ("provenance", provenance.get("vocabulary_budget")),
        ("summary", summary.get("vocabulary_budget")),
    ):
        if not isinstance(payload, dict):
            failures.append(f"{label} is missing frozen-vocabulary metadata")
        elif payload.get("allowed_key_sha256") != allowed_sha:
            failures.append(f"{label} frozen-vocabulary SHA-256 differs")
    return {
        "total_budget": budget,
        "actual_vocabulary_size": len(rows),
        "base_unit_count": sum(row.get("kind") == "base" for row in rows),
        "allowed_key_sha256": allowed_sha,
    }


def audit_run(
    run_dir: Path,
    reference: Path | None,
    metrics_dir: Path | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    config_path = run_dir / "config.json"
    if not config_path.is_file():
        return {
            "run_dir": str(run_dir),
            "valid": False,
            "failures": ["missing files: ['config.json']"],
        }
    config = load_json(config_path)
    model = config.get("model", "latent_lexicon_v1")
    scientific_files = (
        S1M2_SCIENTIFIC_FILES
        if model == "reusable_pieces_v1"
        else SCIENTIFIC_FILES
    )
    required_files = tuple(
        dict.fromkeys(
            (
                "timing_metrics.json",
                "checkpoint.json",
                "config.json",
                "provenance.json",
                "learner.sqlite",
                *scientific_files,
            )
        )
    )
    if model == "reusable_pieces_v1":
        required_files += ("storage_manifest.json",)
    missing = [name for name in required_files if not (run_dir / name).is_file()]
    if missing:
        return {
            "run_dir": str(run_dir),
            "valid": False,
            "failures": [f"missing files: {missing}"],
        }

    checkpoint = load_json(run_dir / "checkpoint.json")
    benchmark_path = run_dir / BENCHMARK_METRICS_FILE
    benchmark = load_json(benchmark_path) if benchmark_path.is_file() else None
    production_manifest_path = run_dir / "production_run_manifest.json"
    production_manifest = (
        load_json(production_manifest_path)
        if production_manifest_path.is_file()
        else None
    )
    if production_manifest is not None and not isinstance(production_manifest, dict):
        failures.append("production run manifest is not a JSON object")
        production_manifest = {}
    if benchmark is not None:
        run_kind = "benchmark_harness"
    elif production_manifest is not None:
        run_kind = "s1m2_production_runner"
    elif _direct_full_configuration(config):
        run_kind = "direct_full_m0"
    else:
        return {
            "run_dir": str(run_dir),
            "valid": False,
            "failures": [
                "benchmark_metrics.json is required for a scoped/non-full run"
            ],
        }
    timing = load_json(run_dir / "timing_metrics.json")
    summary = load_json(run_dir / "summary.json")
    provenance = load_json(run_dir / "provenance.json")

    if production_manifest is not None:
        production_expected = {
            "schema_version": "sktlm-s1m2-run-manifest/v1",
            "dirty_worktree": False,
            "run_id": config.get("run_id"),
            "git_sha": provenance.get("git_commit"),
            "result_status": "PASS",
        }
        for name, expected in production_expected.items():
            if production_manifest.get(name) != expected:
                failures.append(f"production run manifest {name} differs")
        if len(str(production_manifest.get("plan_sha256", ""))) != 64:
            failures.append("production run manifest has no valid plan identity")
        if len(str(production_manifest.get("production_contract_sha256", ""))) != 64:
            failures.append("production run manifest has no valid contract identity")
        final_audit = production_manifest.get("final_audit")
        if not isinstance(final_audit, dict) or final_audit.get("valid") is not True:
            failures.append("production run manifest final audit is not valid")

    if checkpoint.get("completed_passes") != config.get("passes"):
        failures.append("checkpoint completed_passes does not match config")
    if checkpoint.get("inspection_complete") is not True:
        failures.append("inspection is not complete")
    if benchmark is not None:
        if benchmark.get("passes") != config.get("passes"):
            failures.append("benchmark passes does not match config")
        if benchmark.get("workers") != config.get("workers"):
            failures.append("benchmark workers does not match config")
        if benchmark.get("runtime") != timing:
            failures.append("timing_metrics does not equal benchmark runtime")
    script = config.get("script", provenance.get("script"))
    condition = config.get("condition", provenance.get("condition"))
    supported_scripts = FORMAL_SCRIPTS | {"iast_m0_prime"}
    if script not in supported_scripts:
        failures.append(f"unsupported formal script: {script!r}")
    if script == "iast_m0_prime" and condition != "continuous":
        failures.append("iast_m0_prime is valid only for continuous spacing")
    if condition not in FORMAL_CONDITIONS:
        failures.append(f"unsupported formal condition: {condition!r}")
    if provenance.get("script") != script:
        failures.append("provenance script does not match config")
    if provenance.get("condition") != condition:
        failures.append("provenance condition does not match config")
    if provenance.get("freeze_id") != EXPECTED_FREEZE_ID:
        failures.append("provenance freeze ID is not frozen M0")
    if provenance.get("external_rule_count") != EXPECTED_RULES:
        failures.append("provenance external rule count is not 1218")
    expected_hyperparameters = (
        EXPECTED_S1M2_HYPERPARAMETERS
        if model == "reusable_pieces_v1"
        else EXPECTED_HYPERPARAMETERS
    )
    for name, expected in expected_hyperparameters.items():
        if config.get(name) != expected:
            failures.append(
                f"config {name} is {config.get(name)!r}, expected {expected!r}"
            )
    if summary.get("overflowed_tokens") != 0:
        failures.append("summary reports candidate overflow")
    if any(item.get("overflowed_tokens") != 0 for item in checkpoint.get("history", ())):
        failures.append("a training pass reports candidate overflow")
    if benchmark is not None:
        if summary.get("segments") != benchmark.get("inspection_segments"):
            failures.append("summary and benchmark segment counts differ")
        if summary.get("characters") != benchmark.get("inspection_characters"):
            failures.append("summary and benchmark character counts differ")
    iteration_metrics = load_json(run_dir / "iteration_metrics.json")
    if iteration_metrics != checkpoint.get("history"):
        failures.append("iteration_metrics does not match checkpoint history")

    process_metrics: dict[str, Any] | None = None
    if metrics_dir is not None:
        process_summary_path = metrics_dir / "process_tree_summary.json"
        if not process_summary_path.is_file():
            failures.append(f"metrics summary is missing: {process_summary_path}")
        else:
            process_metrics = load_json(process_summary_path)
            if process_metrics.get("return_code") != 0:
                failures.append("process-tree metrics reports nonzero return code")

    residue = sorted(
        str(path.relative_to(run_dir))
        for path in run_dir.rglob("*")
        if path.is_file()
        and (
            "shards" in path.relative_to(run_dir).parts
            or path.name.endswith(".tmp")
            or path.name.startswith("learner.sqlite-")
        )
    )
    if residue:
        failures.append(f"residual shard/tmp/SQLite sidecar files: {residue}")

    database = (
        audit_database(run_dir / "learner.sqlite", model)
        if model == "reusable_pieces_v1"
        else audit_database(run_dir / "learner.sqlite")
    )
    if database["quick_check"] != "ok":
        failures.append(f"SQLite quick_check: {database['quick_check']}")
    if model == "reusable_pieces_v1":
        if database.get("tables") != ["metadata", "piece_lexicon"]:
            failures.append("completed S1M2 database is not compact authoritative state")
        storage = load_json(run_dir / "storage_manifest.json")
        if storage.get("status") != "COMPACT":
            failures.append("S1M2 storage manifest is not COMPACT")
        if storage.get("compiled_topology", {}).get(
            "mutable_scores_or_posteriors_stored"
        ) is not False:
            failures.append("topology archive stores mutable scientific state")
        if not tuple((run_dir / "topology").glob("document_*.bin")):
            failures.append("S1M2 topology archive is missing")
    elif database["lexicon_rows"] != database["inspection_rows"]:
        failures.append("training and inspection lexical row counts differ")

    vocabulary = _audit_vocabulary(
        run_dir, config, checkpoint, provenance, summary, failures
    )

    scientific: dict[str, Any] = {}
    for name in scientific_files:
        candidate_path = run_dir / name
        candidate_hash = file_sha256(candidate_path)
        row: dict[str, Any] = {
            "bytes": candidate_path.stat().st_size,
            "sha256": candidate_hash,
        }
        if reference is not None:
            reference_path = reference / name
            if not reference_path.is_file():
                failures.append(f"reference file missing: {reference_path}")
                row["reference_equal"] = False
            else:
                reference_hash = file_sha256(reference_path)
                row["reference_bytes"] = reference_path.stat().st_size
                row["reference_sha256"] = reference_hash
                row["reference_equal"] = (
                    row["bytes"] == row["reference_bytes"]
                    and candidate_hash == reference_hash
                )
                if not row["reference_equal"]:
                    failures.append(f"scientific artifact differs: {name}")
        scientific[name] = row

    return {
        "run_dir": str(run_dir),
        "run_kind": run_kind,
        "reference": None if reference is None else str(reference),
        "valid": not failures,
        "failures": failures,
        "completion": {
            "completed_passes": checkpoint.get("completed_passes"),
            "inspection_complete": checkpoint.get("inspection_complete"),
            "documents": summary.get("documents"),
            "segments": summary.get("segments"),
            "characters": summary.get("characters"),
            "overflowed_tokens": summary.get("overflowed_tokens"),
            "workers": config.get("workers"),
            "script": script,
            "condition": condition,
        },
        "provenance": provenance,
        "process_metrics": process_metrics,
        "vocabulary": vocabulary,
        "database": database,
        "residue": residue,
        "scientific_artifacts": scientific,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--metrics-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_run(args.run_dir, args.reference, args.metrics_dir)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="")
    print(payload, end="")
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

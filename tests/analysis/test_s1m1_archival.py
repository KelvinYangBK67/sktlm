from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sktlm.analysis.s1m1_archival import (
    SCHEMA_VERSION,
    reduce_manifest,
    write_outputs,
)
from sktlm.analysis.six_representation_gate import FORMAL_CELLS, GateValidationError

SHA = "a" * 40


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _analysis_row(
    segment_id: str,
    document: str,
    line_number: int,
    surface: str,
    *,
    entropy: float,
    edges: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "segment_id": segment_id,
        "document": document,
        "line_number": line_number,
        "source_start": 0,
        "source_end": len(surface),
        "surface": surface,
        "top_analyses": [
            {
                "latent_units": [
                    {
                        "form_key": "D.E.V.A",
                        "iast": "deva",
                        "phoneme_ids": ["D", "E", "V", "A"],
                    },
                    {
                        "form_key": "A.P.I",
                        "iast": "api",
                        "phoneme_ids": ["A", "P", "I"],
                    },
                ],
                "debug_serialization": "deva | api",
                "posterior": 0.6,
                "log_score": -1.0,
                "rule_ids": ["R1"],
                "boundaries": [],
            },
            {
                "latent_units": [
                    {
                        "form_key": "D.E.V.A.A.P.I",
                        "iast": "devaapi",
                        "phoneme_ids": ["D", "E", "V", "A", "A", "P", "I"],
                    }
                ],
                "debug_serialization": "devaapi",
                "posterior": 0.25,
                "log_score": -2.0,
                "rule_ids": [],
                "boundaries": [],
            },
        ],
        "top_analysis_mass": 0.85,
        "residual_posterior": 0.15,
        "identity_mass": 0.2,
        "latent_mass": 0.8,
        "entropy": entropy,
        "log_partition": -0.5,
        "candidate_counts": {
            "boundary_options": 2,
            "factors": 3,
            "merged_factors": 1,
            "token_lattices": 2,
            "lattice_nodes": 5,
            "lexical_edges": edges,
            "overflowed_tokens": 0,
        },
    }


def _make_cell(root: Path, script: str, condition: str) -> dict[str, str]:
    cell_id = f"{script}__{condition}"
    run_id = f"run_{cell_id}"
    metrics_id = f"metrics_{cell_id}"
    run = root / "runs" / run_id
    metrics = root / "metrics" / metrics_id
    run.mkdir(parents=True)
    metrics.mkdir(parents=True)
    config = {
        "run_id": run_id,
        "output_root": "artifacts/latent_benchmarks",
        "script": script,
        "condition": condition,
        "passes": 3,
        "workers": 2,
        "document_list": None,
        "max_documents": None,
        "max_lines_per_document": None,
        "vocab_budget": None,
        "analysis_top_k": 2,
        "lexical_alpha": 0.1,
        "complexity_weight": 0.5,
    }
    provenance = {
        "implementation": "latent-lexicon-v1",
        "git_commit": SHA,
        "script": script,
        "condition": condition,
        "freeze_id": "freeze",
        "manifest_sha256": "manifest",
        "rules_sha256": "rules",
        "external_rule_count": 2,
        "document_count": 240,
        "seed": 0,
        "config_signature": f"signature_{cell_id}",
    }
    history = [
        {
            "pass": index,
            "documents": 240,
            "lines": 2,
            "segments": 2,
            "characters": 16,
            "log_partition": -3.0 + index,
            "mean_identity_mass": 0.4 / index,
            "mean_latent_mass": 1.0 - 0.4 / index,
            "expected_lexical_tokens": 4.0 - 0.2 * index,
            "overflowed_tokens": 0,
            "candidate_factors": 6,
            "candidate_nodes": 10,
            "candidate_edges": 18,
            "lexicon_types": 6 - index,
            "lexical_count_total": 4.0 - 0.2 * index,
        }
        for index in range(1, 4)
    ]
    summary = {
        "documents": 240,
        "lines": 2,
        "segments": 2,
        "characters": 16,
        "overflowed_tokens": 0,
        "candidate_factors": 6,
        "candidate_nodes": 10,
        "candidate_edges": 18,
        "expected_lexical_tokens": 11.0,
        "identity_mass_total": 0.4,
        "latent_mass_total": 1.6,
        "mean_identity_mass": 0.2,
        "mean_latent_mass": 0.8,
        "mean_top1_posterior": 0.6,
        "mean_entropy": 0.6,
        "rule_expected_usage_total": 1.5,
        "complexity": {
            "active_lexical_types": 4,
            "expected_lexical_tokens": 11.0,
            "low_count_types": 1,
            "low_count_threshold": 1.0,
            "complexity_raw": 4.0,
            "complexity_penalty": 2.0,
        },
    }
    process = {
        "return_code": 0,
        "wall_seconds": 4.0,
        "peak_process_tree_rss_bytes": 1000,
        "sampled_process_tree_cpu_seconds": 5.0,
        "peak_process_count": 3,
        "sampled_process_tree_read_bytes": 100,
        "sampled_process_tree_write_bytes": 200,
        "logical_cpu_count": 8,
    }
    timing = {
        "timings_seconds": {
            "inspection_candidate_generation": 0.2,
            "inspection_inference": 0.4,
            "inspection_worker_sqlite": 0.1,
            "inspection_serialization": 0.05,
            "lexicon_finalize": 0.02,
        },
        "counters": {"documents_completed": 240},
        "lexical_scorers": [
            {
                "score_calls": 20,
                "cache_hits": 5,
                "cache_misses": 15,
                "sqlite_selects": 15,
                "sqlite_seconds": 0.1,
                "cache_size": 10,
            }
        ],
    }
    checkpoint = {"completed_passes": 3, "inspection_complete": True}
    _json(run / "config.json", config)
    _json(run / "checkpoint.json", checkpoint)
    _json(run / "provenance.json", provenance)
    _json(run / "iteration_metrics.json", history)
    _json(run / "summary.json", summary)
    _json(run / "timing_metrics.json", timing)
    (run / "inspection_report.md").write_text("# fixture\n", encoding="utf-8")
    surfaces = (
        ("deva api", "rama api")
        if script == "iast"
        else (
            "\u0926\u0947\u0935 \u0905\u092a\u093f",
            "\u0930\u093e\u092e \u0905\u092a\u093f",
        )
    )
    analyses = [
        _analysis_row(
            f"{cell_id}:l00000001:s0000",
            "doc-a.txt",
            1,
            surfaces[0],
            entropy=0.7,
            edges=10,
        ),
        _analysis_row(
            f"{cell_id}:l00000002:s0000",
            "doc-b.txt",
            2,
            surfaces[1],
            entropy=0.5,
            edges=8,
        ),
    ]
    (run / "analyses.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in analyses),
        encoding="utf-8",
    )
    boundaries = [
        {
            "schema_version": 1,
            "segment_id": row["segment_id"],
            "surface": row["surface"],
            "boundaries": [
                {
                    "boundary_id": f"{row['segment_id']}:b0",
                    "cue_kind": "space",
                    "source_start": 4,
                    "source_end": 5,
                    "probability": probability,
                }
            ],
        }
        for row, probability in zip(analyses, (0.8, 0.4))
    ]
    (run / "boundary_posteriors.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in boundaries),
        encoding="utf-8",
    )
    (run / "latent_lexicon.tsv").write_text(
        "form_key\tlatent_form\tphoneme_ids\texpected_count\tprobability\t"
        "number_of_surface_variants\tnumber_of_contexts\n"
        "A\ta\tA\t5\t0.4\t3\t10\n"
        "B\tb\tB B\t3\t0.3\t2\t5\n"
        "C\tc\tC C C C C C C C\t2\t0.2\t1\t2\n"
        "D\td\tD D D D D D D D D D D D D D D D\t1\t0.1\t1\t1\n",
        encoding="utf-8",
    )
    (run / "rule_usage.tsv").write_text(
        "rule_id\texpected_usage\nR1\t1.25\nR2\t0.25\n", encoding="utf-8"
    )
    _json(metrics / "process_tree_summary.json", process)
    scientific = {
        name: {"bytes": (run / name).stat().st_size, "sha256": _hash(run / name)}
        for name in (
            "iteration_metrics.json",
            "summary.json",
            "analyses.jsonl",
            "boundary_posteriors.jsonl",
            "latent_lexicon.tsv",
            "rule_usage.tsv",
        )
    }
    audit = {
        "run_dir": f"/remote/artifacts/{run_id}",
        "valid": True,
        "failures": [],
        "provenance": provenance,
        "process_metrics": process,
        "completion": {
            "script": script,
            "condition": condition,
            "workers": 2,
            "documents": 240,
            "segments": 2,
            "characters": 16,
            "overflowed_tokens": 0,
        },
        "scientific_artifacts": scientific,
    }
    audit_path = root / "audits" / f"{run_id}.json"
    _json(audit_path, audit)
    return {
        "script": script,
        "condition": condition,
        "run_id": run_id,
        "metrics_id": metrics_id,
        "scientific_commit": SHA,
        "run_dir": run.relative_to(root).as_posix(),
        "metrics_dir": metrics.relative_to(root).as_posix(),
        "audit_path": audit_path.relative_to(root).as_posix(),
    }


def _manifest(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    payload: dict[str, object] = {
        "schema_version": "sktlm-six-representation-gate-input/v1",
        "gate_id": "fixture-gate",
        "scientific_contract_id": "fixture-contract",
        "approved_scientific_commits": [SHA],
        "cells": [_make_cell(tmp_path, *cell) for cell in FORMAL_CELLS],
    }
    path = tmp_path / "gate.json"
    _json(path, payload)
    return path, payload


def _refresh_scientific_audit(
    root: Path, cell: dict[str, str], artifact: str
) -> None:
    run = root / cell["run_dir"]
    audit_path = root / cell["audit_path"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["scientific_artifacts"][artifact] = {
        "bytes": (run / artifact).stat().st_size,
        "sha256": _hash(run / artifact),
    }
    _json(audit_path, audit)


def test_fixture_reduction_is_deterministic_bounded_and_writes_compact_outputs(
    tmp_path: Path,
) -> None:
    manifest, _payload = _manifest(tmp_path)
    source_hashes = {
        path: _hash(path)
        for path in (tmp_path / "runs").rglob("*")
        if path.is_file()
    }
    first = reduce_manifest(manifest)
    second = reduce_manifest(manifest)
    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert len(first["tables"]["cells"]) == 6
    assert len(first["retention_manifest"]["sources"]) == 78
    assert first["retention_manifest"]["status"] == "post_hoc_descriptive_archival"
    diversity = next(
        row
        for row in first["tables"]["lexicon_distribution"]
        if row["cell_id"] == "iast__surface_word" and row["metric"] == "diversity"
    )
    assert diversity["active_types"] == 4
    assert diversity["effective_vocabulary_exp_entropy"] > 1.0
    reconstructed = [
        row
        for row in first["evidence_samples"]
        if row.get("reconstructed_top_analysis_tokens")
    ]
    assert reconstructed
    output = tmp_path / "archive"
    write_outputs(first, output)
    assert {
        "manifest.json",
        "cells.tsv",
        "pass_dynamics.tsv",
        "lexicon_distribution.tsv",
        "lexical_length.tsv",
        "reuse_distribution.tsv",
        "ambiguity_distribution.tsv",
        "boundary_distribution.tsv",
        "rule_usage.tsv",
        "candidate_scaling.tsv",
        "document_distribution.tsv",
        "length_strata.tsv",
        "runtime_breakdown.tsv",
        "pairwise_stability.tsv",
        "evidence_samples.jsonl",
        "summary.md",
    } == {path.name for path in output.iterdir()}
    assert "does not alter" in (output / "summary.md").read_text(encoding="utf-8")
    assert source_hashes == {path: _hash(path) for path in source_hashes}
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_outputs(first, output)


def test_analysis_and_boundary_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest, payload = _manifest(tmp_path)
    first = payload["cells"][0]
    assert isinstance(first, dict)
    run = tmp_path / first["run_dir"]
    rows = [
        json.loads(line)
        for line in (run / "boundary_posteriors.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    rows[1]["segment_id"] = "different-segment"
    (run / "boundary_posteriors.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    _refresh_scientific_audit(tmp_path, first, "boundary_posteriors.jsonl")
    with pytest.raises(GateValidationError, match="segment identities/order differ"):
        reduce_manifest(manifest)


def test_inconsistent_top_k_mass_fails_closed(tmp_path: Path) -> None:
    manifest, payload = _manifest(tmp_path)
    first = payload["cells"][0]
    assert isinstance(first, dict)
    run = tmp_path / first["run_dir"]
    rows = [
        json.loads(line)
        for line in (run / "analyses.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["top_analysis_mass"] = 0.9
    (run / "analyses.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    _refresh_scientific_audit(tmp_path, first, "analyses.jsonl")
    with pytest.raises(GateValidationError, match="top_analysis_mass differs"):
        reduce_manifest(manifest)


def test_lexicon_schema_and_declared_row_count_fail_closed(tmp_path: Path) -> None:
    manifest, payload = _manifest(tmp_path)
    first = payload["cells"][0]
    assert isinstance(first, dict)
    run = tmp_path / first["run_dir"]
    path = run / "latent_lexicon.tsv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    _refresh_scientific_audit(tmp_path, first, "latent_lexicon.tsv")
    with pytest.raises(GateValidationError, match="row count .* differs"):
        reduce_manifest(manifest)

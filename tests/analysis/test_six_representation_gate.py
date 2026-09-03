from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from sktlm.analysis.six_representation_gate import (
    FORMAL_CELLS,
    GateValidationError,
    _load_cell,
    _parse_manifest,
    aggregate_manifest,
    jensen_shannon_nats,
    lexical_mass_summary,
    scalar_comparison,
    total_variation,
    write_outputs,
)

SHA = "a" * 40


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "workers": 8,
        "document_list": None,
        "max_documents": None,
        "max_lines_per_document": None,
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
    summary = {
        "documents": 240,
        "segments": 10,
        "characters": 100,
        "overflowed_tokens": 0,
        "candidate_factors": 20,
        "candidate_nodes": 30,
        "candidate_edges": 40,
        "expected_lexical_tokens": 10.0,
        "identity_mass_total": 2.0,
        "latent_mass_total": 8.0,
        "mean_identity_mass": 0.2,
        "mean_latent_mass": 0.8,
        "mean_top1_posterior": 0.7,
        "mean_entropy": 0.5,
        "rule_expected_usage_total": 1.0,
        "complexity": {
            "active_lexical_types": 3,
            "expected_lexical_tokens": 10.0,
            "low_count_types": 0,
            "low_count_threshold": 1.0,
            "complexity_raw": 4.0,
            "complexity_penalty": 2.0,
        },
    }
    checkpoint = {"completed_passes": 3, "inspection_complete": True}
    process = {
        "return_code": 0,
        "wall_seconds": 12.0,
        "peak_process_tree_rss_bytes": 1000,
        "sampled_process_tree_cpu_seconds": 20.0,
        "peak_process_count": 9,
        "sampled_process_tree_read_bytes": 100,
        "sampled_process_tree_write_bytes": 200,
        "logical_cpu_count": 16,
    }
    _json(run / "config.json", config)
    _json(run / "checkpoint.json", checkpoint)
    _json(run / "provenance.json", provenance)
    _json(run / "timing_metrics.json", {"timings_seconds": {}})
    _json(run / "iteration_metrics.json", [{"pass": index} for index in range(1, 4)])
    _json(run / "summary.json", summary)
    (run / "inspection_report.md").write_text("# fixture\n", encoding="utf-8")
    (run / "analyses.jsonl").write_text("{}\n", encoding="utf-8")
    (run / "boundary_posteriors.jsonl").write_text("{}\n", encoding="utf-8")
    (run / "latent_lexicon.tsv").write_text(
        "form_key\texpected_count\nA\t5\nB\t3\nC\t2\n", encoding="utf-8"
    )
    (run / "rule_usage.tsv").write_text(
        "rule_id\texpected_usage\nR1\t1\nR2\t0\n", encoding="utf-8"
    )
    _json(metrics / "process_tree_summary.json", process)
    scientific = {
        name: {"bytes": (run / name).stat().st_size, "sha256": _hash(run / name)}
        for name in (
            "iteration_metrics.json", "summary.json", "analyses.jsonl",
            "boundary_posteriors.jsonl", "latent_lexicon.tsv", "rule_usage.tsv",
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
            "workers": 8,
            "documents": 240,
            "segments": 10,
            "characters": 100,
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


def _rewrite_audit(root: Path, cell: dict[str, str], mutate) -> None:
    audit_path = root / cell["audit_path"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    mutate(audit)
    _json(audit_path, audit)


def test_exact_six_cell_fixture_aggregates_and_writes_outputs(tmp_path: Path) -> None:
    manifest, _payload = _manifest(tmp_path)
    result = aggregate_manifest(manifest)
    assert result["validation"]["valid"] is True
    assert [row["cell_id"] for row in result["cells"]] == [
        f"{script}__{condition}" for script, condition in FORMAL_CELLS
    ]
    assert len(result["pairs"]) == 9
    assert result["cells"][0]["lexical_mass_support"]["mass_support_type_counts"]["90%"] == 3
    output = tmp_path / "output"
    write_outputs(result, output)
    assert sorted(path.name for path in output.iterdir()) == [
        "aggregation.json", "cells.tsv", "pairs.tsv", "rule_distances.tsv",
        "rule_usage.tsv", "summary.md",
    ]
    with pytest.raises(FileExistsError):
        write_outputs(result, output)


def test_missing_and_duplicate_cells_fail_closed(tmp_path: Path) -> None:
    manifest, payload = _manifest(tmp_path)
    cells = payload["cells"]
    assert isinstance(cells, list)
    payload["cells"] = cells[:-1]
    _json(manifest, payload)
    with pytest.raises(GateValidationError, match="missing formal cells"):
        aggregate_manifest(manifest)
    payload["cells"] = [*cells[:-1], dict(cells[0])]
    _json(manifest, payload)
    with pytest.raises(GateValidationError, match="duplicate formal cells"):
        aggregate_manifest(manifest)


def test_invalid_audit_and_nonzero_return_code_fail_closed(tmp_path: Path) -> None:
    manifest, payload = _manifest(tmp_path)
    first = payload["cells"][0]
    assert isinstance(first, dict)
    _rewrite_audit(tmp_path, first, lambda audit: audit.update(valid=False))
    with pytest.raises(GateValidationError, match="final audit is not valid"):
        aggregate_manifest(manifest)

    manifest, payload = _manifest(tmp_path / "second")
    first = payload["cells"][0]
    metrics_path = manifest.parent / first["metrics_dir"] / "process_tree_summary.json"
    process = json.loads(metrics_path.read_text(encoding="utf-8"))
    process["return_code"] = 9
    _json(metrics_path, process)
    _rewrite_audit(tmp_path / "second", first, lambda audit: audit.update(process_metrics=process))
    with pytest.raises(GateValidationError, match="return_code is not zero"):
        aggregate_manifest(manifest)


def test_run_and_representation_identity_mismatches_fail_closed(tmp_path: Path) -> None:
    manifest, payload = _manifest(tmp_path)
    first = payload["cells"][0]
    run = manifest.parent / first["run_dir"]
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    config["run_id"] = "wrong"
    _json(run / "config.json", config)
    with pytest.raises(GateValidationError, match="config run_id"):
        aggregate_manifest(manifest)

    manifest, payload = _manifest(tmp_path / "second")
    first = payload["cells"][0]
    run = manifest.parent / first["run_dir"]
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    config["condition"] = "continuous"
    _json(run / "config.json", config)
    with pytest.raises(GateValidationError, match="representation identity"):
        aggregate_manifest(manifest)


def test_explicit_legacy_config_identity_uses_matching_provenance(tmp_path: Path) -> None:
    _manifest_path, payload = _manifest(tmp_path)
    first = payload["cells"][0]
    run = tmp_path / first["run_dir"]
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    del config["script"]
    del config["condition"]
    _json(run / "config.json", config)
    spec = next(
        cell for cell in _parse_manifest(_manifest_path)[1]
        if cell.key == (first["script"], first["condition"])
    )
    loaded = _load_cell(spec, allow_missing_config_identity=True)
    assert loaded.provenance["script"] == first["script"]


def test_lexicon_sorting_and_mass_support_are_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "lexicon.tsv"
    path.write_text("form_key\texpected_count\nA\t5\nB\t3\nC\t2\n", encoding="utf-8")
    result = lexical_mass_summary(path, 2.0)
    assert result["lexical_expected_count_total"] == 10.0
    assert result["low_count_lexical_types"] == 1
    assert result["mass_support_type_counts"] == {
        "90%": 3, "95%": 3, "99%": 3, "99.9%": 3, "99.99%": 3,
    }
    path.write_text("form_key\texpected_count\nB\t5\nA\t5\n", encoding="utf-8")
    with pytest.raises(GateValidationError, match="form_key ASC"):
        lexical_mass_summary(path, 1.0)


def test_scalar_difference_ratio_and_zero_denominator_are_explicit() -> None:
    row = scalar_comparison(2.0, 3.0)
    assert row["signed_difference_b_minus_a"] == 1.0
    assert row["absolute_difference"] == 1.0
    assert row["relative_difference_b_minus_a_over_abs_a"] == 0.5
    assert row["ratio_b_over_a"] == 1.5
    zero = scalar_comparison(0.0, 1.0)
    assert zero["denominator_zero"] is True
    assert zero["relative_difference_b_minus_a_over_abs_a"] is None
    assert zero["ratio_b_over_a"] is None


def test_tv_jsd_known_values_and_zero_probabilities() -> None:
    left = {"R1": 1.0, "R2": 0.0}
    right = {"R2": 1.0, "R3": 0.0}
    assert total_variation(left, right) == pytest.approx(1.0)
    assert jensen_shannon_nats(left, right) == pytest.approx(math.log(2.0))
    assert total_variation(left, left) == 0.0
    assert jensen_shannon_nats(left, left) == 0.0


def test_overflow_is_propagated_not_a_new_aggregator_failure(tmp_path: Path) -> None:
    manifest, payload = _manifest(tmp_path)
    first = payload["cells"][0]
    run = manifest.parent / first["run_dir"]
    summary_path = run / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["overflowed_tokens"] = 2
    _json(summary_path, summary)
    _rewrite_audit(
        tmp_path,
        first,
        lambda audit: (
            audit["completion"].update(overflowed_tokens=2),
            audit["scientific_artifacts"]["summary.json"].update(
                bytes=summary_path.stat().st_size, sha256=_hash(summary_path)
            ),
        ),
    )
    result = aggregate_manifest(manifest)
    metric = result["cells"][0]["scientific_metrics"]
    assert metric["overflowed_tokens"] == 2
    assert metric["overflow_frequency_per_segment"] == pytest.approx(0.2)

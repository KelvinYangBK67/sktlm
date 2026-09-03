from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sktlm.analysis.representation_protocol as protocol
from sktlm.analysis.six_representation_gate import GateValidationError

SHA = "a" * 40


def _write_manifest(path: Path, *, available: int = 4) -> Path:
    cells = []
    supplied = []
    names = (
        ("i_word", "iast", "surface_word"),
        ("d_word", "devanagari", "surface_word"),
        ("i_join", "iast", "legacy_joined"),
        ("d_join", "devanagari", "legacy_joined"),
        ("i_cont", "iast", "continuous"),
        ("d_cont", "devanagari", "continuous"),
    )
    for index, (cell_id, script, representation) in enumerate(names):
        status = (
            "AVAILABLE" if index < available else
            "NA_SCIENTIFICALLY_EXCLUDED" if index == len(names) - 2 else
            "NA_EXECUTION_INCOMPLETE"
        )
        cells.append({
            "cell_id": cell_id, "script": script, "representation": representation,
            "status": status,
            **({} if status == "AVAILABLE" else {
                "reason": "bounded run did not complete",
                "provenance_evidence": {"expected_commit": SHA},
                "runtime_evidence": {"wall_seconds": 12},
                "termination_evidence": {"signal": "timeout"},
            }),
        })
        if status == "AVAILABLE":
            supplied.append({
                "cell_id": cell_id, "run_id": f"run_{cell_id}",
                "metrics_id": f"metrics_{cell_id}", "scientific_commit": SHA,
                "run_dir": f"runs/{cell_id}", "metrics_dir": f"metrics/{cell_id}",
                "audit_path": f"audits/{cell_id}.json",
            })
    payload = {
        "schema_version": protocol.SCHEMA_VERSION,
        "analysis_id": "fixture", "approved_scientific_commits": [SHA],
        "cell_universe": cells, "supplied_cells": supplied,
        "pairwise_comparisons": [
            {"pair_id": "joined", "kind": "script", "cell_a": "i_join", "cell_b": "d_join"},
            {"pair_id": "continuous", "kind": "script", "cell_a": "i_cont", "cell_b": "d_cont"},
        ],
        "top_k_values": [2],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _patch_scientific_loaders(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    loaded: list[str] = []

    def fake_load(spec, **kwargs):
        loaded.append(spec.cell_id)
        return SimpleNamespace(spec=spec)

    scientific = {key: 1.0 for key in protocol.SCIENTIFIC_METRICS}
    payload = {
        "scientific_metrics": scientific, "engineering_metrics": {},
        "lexical_mass_support": {},
        "rule_usage": {"expected_usage": {"r": 1.0}, "normalized_distribution": {"r": 1.0}},
    }
    monkeypatch.setattr(protocol, "_load_cell", fake_load)
    monkeypatch.setattr(protocol, "_validate_cross_cell_contract", lambda cells: None)
    monkeypatch.setattr(protocol, "_cell_scalar_metrics", lambda cell: (dict(payload), {}))
    monkeypatch.setattr(protocol, "_top_forms", lambda path, maximum: ("A", "B"))
    return loaded


def test_four_of_six_aggregates_and_unavailable_pair_is_na(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json")
    loaded = _patch_scientific_loaders(monkeypatch)
    result = protocol.aggregate_manifest(manifest)
    assert result["cell_counts"] == {"declared": 6, "available": 4, "n_a": 2}
    assert len(loaded) == 4
    assert result["pairs"][0]["comparison_status"] == "AVAILABLE"
    assert result["pairs"][0]["top_k_overlap"][0]["jaccard"] == 1.0
    assert result["pairs"][1]["comparison_status"] == "N/A"
    assert result["pairs"][1]["scalar_metrics"]["active_lexical_types"]["value_a"] is None
    continuous = result["cells"][-1]
    assert continuous["scientific_metrics"]["active_lexical_types"] is None
    assert continuous["runtime_evidence"] == {"wall_seconds": 12}
    assert continuous["termination_evidence"] == {"signal": "timeout"}
    assert continuous["provenance_evidence"] == {"expected_commit": SHA}


def test_duplicate_cell_and_unknown_status_fail_closed(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", available=0)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["cell_universe"].append(dict(payload["cell_universe"][0]))
    payload["cell_universe"][1]["status"] = "MISSING"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GateValidationError) as error:
        protocol.aggregate_manifest(manifest)
    message = str(error.value)
    assert "duplicate declared cell_id" in message
    assert "status is unknown" in message


def test_supplied_corruption_fails_but_na_cells_are_never_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json")
    calls: list[str] = []

    def corrupt(spec, **kwargs):
        calls.append(spec.cell_id)
        if spec.cell_id == "iast__surface_word":
            raise GateValidationError(("scientific artifact SHA-256 mismatch",))
        return SimpleNamespace(spec=spec)

    monkeypatch.setattr(protocol, "_load_cell", corrupt)
    with pytest.raises(GateValidationError, match="SHA-256 mismatch"):
        protocol.aggregate_manifest(manifest)
    assert len(calls) == 4
    assert all("continuous" not in cell_id for cell_id in calls)


def test_zero_supplied_cells_is_valid_and_writes_na_not_blanks(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", available=0)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["approved_scientific_commits"] = []
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    result = protocol.aggregate_manifest(manifest)
    output = tmp_path / "out"
    protocol.write_outputs(result, output)
    assert result["cell_counts"]["available"] == 0
    assert "\tN/A\n" in (output / "cells.tsv").read_text(encoding="utf-8")
    assert sorted(path.name for path in output.iterdir()) == [
        "aggregation.json", "cells.tsv", "pairs.tsv", "rule_distances.tsv",
        "rule_usage.tsv", "summary.md", "top_k_overlap.tsv",
    ]

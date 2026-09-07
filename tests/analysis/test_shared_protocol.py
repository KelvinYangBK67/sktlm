"""Experiment-neutral shared analysis and baseline adapter tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

import sktlm.analysis.baseline_adapter as baseline_adapter
from sktlm.analysis.shared_protocol import (
    CellEvidence,
    CellStatus,
    SharedAnalysisError,
    _load_manifest,
    analyze_evidence,
    expand_comparisons,
    publish_analysis,
    run_adapter,
)
from sktlm.experiments.baselines.full_m0 import FullM0MatrixSettings, build_full_m0_run_specs


CONFIG = Path("configs/experiments/baselines/full_m0_matrix.yaml")
COMPARISONS = Path("configs/analysis/full_m0_baseline_comparisons.yaml")


def _cells() -> tuple[CellEvidence, ...]:
    settings = FullM0MatrixSettings.from_yaml(CONFIG)
    return tuple(
        CellEvidence(
            cell_id=spec.cell.condition_id,
            status=CellStatus.AVAILABLE,
            dimensions={
                "method": spec.cell.method,
                "script": spec.cell.script,
                "representation": spec.cell.spacing,
                "substrate": spec.cell.substrate,
            },
            scientific_metrics={"common_downstream_bits_per_character": 1.0},
            engineering_metrics={"runtime_seconds": 2.0},
            provenance={"fixture": True},
            artifacts={"fixture": True},
        )
        for spec in build_full_m0_run_specs(settings)
    )


def test_versioned_comparisons_expand_before_results_and_mark_descriptive_controls() -> None:
    declarations = expand_comparisons(_cells(), _load_manifest(COMPARISONS))
    assert len(declarations) == 60
    assert len({row.comparison_id for row in declarations}) == 60
    descriptive = [row for row in declarations if row.kind == "descriptive_difference"]
    assert len(descriptive) == 8
    assert all(row.strict_control is False for row in descriptive)


def test_shared_protocol_rejects_duplicate_cells_unknown_adapter_and_undeclared_selector(tmp_path: Path) -> None:
    cells = _cells()
    with pytest.raises(SharedAnalysisError, match="duplicate cell IDs"):
        expand_comparisons((*cells, cells[0]), _load_manifest(COMPARISONS))
    with pytest.raises(SharedAnalysisError, match="unknown shared-analysis adapter"):
        run_adapter("missing", {})

    payload = yaml.safe_load(COMPARISONS.read_text(encoding="utf-8"))
    payload["comparison_families"][0]["contexts"][0]["left"]["script"] = "undeclared"
    path = tmp_path / "comparisons.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(SharedAnalysisError, match="match exactly one cell"):
        analyze_evidence(
            adapter_id=baseline_adapter.ADAPTER_ID,
            cells=cells,
            comparison_manifest=path,
            adapter_provenance={},
        )


def test_shared_publication_is_atomic_and_refuses_overwrite(tmp_path: Path) -> None:
    result = analyze_evidence(
        adapter_id=baseline_adapter.ADAPTER_ID,
        cells=_cells(),
        comparison_manifest=COMPARISONS,
        adapter_provenance={"validated": True},
    )
    output = tmp_path / "analysis"
    publish_analysis(result, output)
    assert sorted(path.name for path in output.iterdir()) == [
        "analysis.json", "cells.tsv", "comparisons.tsv", "summary.md"
    ]
    assert result["cell_counts"] == {"declared": 22, "available": 22, "n_a": 0}
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        publish_analysis(result, output)


def test_declared_comparison_with_unavailable_cell_is_explicit_na() -> None:
    cells = list(_cells())
    cells[0] = replace(
        cells[0],
        status=CellStatus.NA_EXECUTION_INCOMPLETE,
        scientific_metrics={},
        reason="formal bundle is incomplete",
    )
    result = analyze_evidence(
        adapter_id=baseline_adapter.ADAPTER_ID,
        cells=cells,
        comparison_manifest=COMPARISONS,
        adapter_provenance={},
    )
    affected = [row for row in result["comparisons"] if row["cell_a"] == cells[0].cell_id or row["cell_b"] == cells[0].cell_id]
    assert affected and all(row["status"] == "N/A" for row in affected)


def test_baseline_adapter_calls_native_aggregate_and_never_requires_other_family_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = FullM0MatrixSettings.from_yaml(CONFIG)
    results = {}
    for spec in build_full_m0_run_specs(settings):
        results[spec.cell.condition_id] = {
            "identity": {
                "method": spec.cell.method,
                "script": spec.cell.script,
                "spacing": spec.cell.spacing,
                "substrate": spec.cell.substrate,
            },
            "provenance": {
                "environment_fingerprint_sha256": "a" * 64,
                "software_versions": {"python": "fixture"},
                "code_commit": "b" * 40,
                "data_fingerprint_sha256": "c" * 64,
                "tokenizer_fingerprint_sha256": "d" * 64,
                "training_instance_id": spec.cell.condition_id,
                "artifact_location": f"artifacts/{spec.cell.condition_id}",
            },
            "artifacts": {"metrics.json": "e" * 64},
            "common_downstream_lm_utility": {"common_downstream_bits_per_character": 1.0},
            "segmentation_statistics": {"token_count": 10},
            "unknown_behavior": {"unk_count": 0},
            "token_inventory_occupancy": {"occupied_token_types": 5},
            "orthographic_diagnostics": {},
            "method_specific_likelihood": {},
            "runtime_resources": {"runtime_seconds": 2.0},
        }
    native = {
        "aggregate_schema_version": "full-m0-baseline-aggregate/v1",
        "condition_manifest_version": settings.condition_manifest_version,
        "full_m0_definition_version": settings.full_m0_definition_version,
        "results": results,
    }
    calls = []
    monkeypatch.setattr(
        baseline_adapter,
        "aggregate_formal_results",
        lambda *args, **kwargs: calls.append((args, kwargs)) or native,
    )
    result = baseline_adapter.adapt_full_m0_baselines(
        settings=settings,
        artifact_root=Path("artifacts"),
        comparison_manifest=COMPARISONS,
    )
    assert len(calls) == 1
    assert result["cell_counts"]["available"] == 22
    assert all("scientific_metrics" in cell and "engineering_metrics" in cell for cell in result["cells"])
    source = Path(baseline_adapter.__file__).read_text(encoding="utf-8")
    assert "sktlm." + "latent" not in source

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sktlm.analysis.six_representation_gate import GateValidationError

from sktlm.analysis.s1m1_final import (
    FINAL_VALID_CELLS,
    FORMAL_COMPARISONS,
    FinalValidationError,
    INPUT_SCHEMA_VERSION,
    INVALIDATED_CELL,
    INVALIDATION_ARCHIVE_SHA256,
    INVALIDATION_REASON_CODE,
    INVALIDATION_SCIENTIFIC_COMMIT,
    parse_final_manifest,
    load_final_input,
    reduce_final_per_cell,
    build_formal_comparisons,
    write_final_outputs,
    reduce_final_manifest,
    build_failure_mode_indicators,
    build_decision_inputs,
    _lexicon_failure_rows,
    PER_CELL_TABLE_NAMES,
    FINAL_TABLE_NAMES,
)


SHA = "a" * 40


def _cell(script: str, condition: str) -> dict[str, str]:
    cell_id = f"{script}__{condition}"
    return {
        "script": script,
        "condition": condition,
        "run_id": f"run_{cell_id}",
        "metrics_id": f"metrics_{cell_id}",
        "scientific_commit": SHA,
        "run_dir": f"runs/run_{cell_id}",
        "metrics_dir": f"metrics/metrics_{cell_id}",
        "audit_path": f"audits/run_{cell_id}.json",
    }


def _invalidation() -> dict[str, object]:
    return {
        "script": "iast",
        "condition": "continuous",
        "scientific_status": "INVALIDATED",
        "runtime_status": "TERMINATED_EARLY_BY_RESEARCHER",
        "formal_comparison": "EXCLUDED",
        "diagnostic_evidence": "RETAINED",
        "rerun_repair": "NONE",
        "reason_code": INVALIDATION_REASON_CODE,
        "completed_passes": 2,
        "termination_pass": 3,
        "next_document_index": 86,
        "scientific_commit": INVALIDATION_SCIENTIFIC_COMMIT,
        "termination_archive_sha256": INVALIDATION_ARCHIVE_SHA256,
    }


def _payload() -> dict[str, object]:
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "analysis_id": "fixture-s1m1-final",
        "scientific_contract_id": "s1m1-final-analysis-plan-v1",
        "approved_scientific_commits": [SHA],
        "cells": [_cell(*cell) for cell in FINAL_VALID_CELLS],
        "invalidated_cells": [_invalidation()],
    }


def _write_manifest(
    tmp_path: Path,
    payload: dict[str, object],
) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def test_exact_five_cell_contract_and_formal_comparisons(
    tmp_path: Path,
) -> None:
    path = _write_manifest(tmp_path, _payload())
    _manifest, cells, invalidated = parse_final_manifest(path)

    assert tuple(cell.key for cell in cells) == FINAL_VALID_CELLS
    assert invalidated.key == INVALIDATED_CELL

    assert len(FORMAL_COMPARISONS) == 6
    assert len({pair.pair_id for pair in FORMAL_COMPARISONS}) == 6

    assert all(
        INVALIDATED_CELL not in (pair.cell_a, pair.cell_b)
        for pair in FORMAL_COMPARISONS
    )

    continuous_pairs = [
        pair
        for pair in FORMAL_COMPARISONS
        if pair.cell_a[1] == "continuous"
        or pair.cell_b[1] == "continuous"
    ]
    assert len(continuous_pairs) == 2
    assert all(
        pair.cell_a[0] == "devanagari"
        and pair.cell_b[0] == "devanagari"
        for pair in continuous_pairs
    )


def test_missing_valid_cell_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    cells = payload["cells"]
    assert isinstance(cells, list)
    cells.pop()

    path = _write_manifest(tmp_path, payload)
    with pytest.raises(FinalValidationError, match="missing valid cells"):
        parse_final_manifest(path)


def test_iast_continuous_cannot_be_a_valid_cell(
    tmp_path: Path,
) -> None:
    payload = _payload()
    cells = payload["cells"]
    assert isinstance(cells, list)
    cells[-1] = _cell("iast", "continuous")

    path = _write_manifest(tmp_path, payload)
    with pytest.raises(
        FinalValidationError,
        match="scientifically invalidated",
    ):
        parse_final_manifest(path)


def test_missing_invalidation_record_fails_closed(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["invalidated_cells"] = []

    path = _write_manifest(tmp_path, payload)
    with pytest.raises(
        FinalValidationError,
        match="exactly one invalidated cell record",
    ):
        parse_final_manifest(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scientific_status", "VALID"),
        ("runtime_status", "COMPLETED"),
        ("formal_comparison", "INCLUDED"),
        ("diagnostic_evidence", "DISCARDED"),
        ("rerun_repair", "RERUN"),
        ("reason_code", "other"),
        ("completed_passes", 3),
        ("termination_pass", 2),
        ("next_document_index", 87),
        ("scientific_commit", "b" * 40),
        ("termination_archive_sha256", "0" * 64),
    ],
)
def test_contradictory_invalidation_record_fails_closed(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    payload = _payload()
    records = payload["invalidated_cells"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    record[field] = value

    path = _write_manifest(tmp_path, payload)
    with pytest.raises(
        FinalValidationError,
        match="provenance mismatch",
    ):
        parse_final_manifest(path)


def test_final_validation_error_uses_final_output_schema(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["cells"] = []

    path = _write_manifest(tmp_path, payload)
    with pytest.raises(FinalValidationError) as caught:
        parse_final_manifest(path)

    error_payload = caught.value.payload()
    assert error_payload["schema_version"] == "sktlm-s1m1-final-analysis/v1"
    assert error_payload["validation"]["valid"] is False
    assert error_payload["validation"]["errors"]



def _fake_loaded_cell(spec, *, passes: int = 3):
    class FakeLoaded:
        pass

    loaded = FakeLoaded()
    loaded.spec = spec
    loaded.config = {
        "run_id": spec.run_id,
        "script": spec.script,
        "condition": spec.condition,
        "output_root": "artifacts/latent_benchmarks",
        "passes": passes,
        "workers": 8,
        "vocab_budget": None,
    }
    loaded.provenance = {
        "implementation": "latent-lexicon-v1",
        "freeze_id": "freeze",
        "manifest_sha256": "manifest",
        "rules_sha256": "rules",
        "external_rule_count": 2,
        "document_count": 240,
        "seed": 0,
    }
    return loaded


def test_final_input_loads_exactly_five_valid_cells(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _payload())
    calls = []

    def fake_load(spec):
        calls.append(spec.key)
        return _fake_loaded_cell(spec)

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._load_cell",
        fake_load,
    )

    _manifest, loaded, invalidated = load_final_input(path)

    assert tuple(calls) == FINAL_VALID_CELLS
    assert tuple(cell.spec.key for cell in loaded) == FINAL_VALID_CELLS
    assert invalidated.key == INVALIDATED_CELL
    assert INVALIDATED_CELL not in calls


def test_final_input_translates_cell_audit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _payload())

    def fake_load(spec):
        if spec.key == ("devanagari", "continuous"):
            raise GateValidationError(
                ("devanagari__continuous: final audit is missing",)
            )
        return _fake_loaded_cell(spec)

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._load_cell",
        fake_load,
    )

    with pytest.raises(
        FinalValidationError,
        match="final audit is missing",
    ):
        load_final_input(path)


def test_final_input_rejects_cross_cell_scientific_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _payload())

    def fake_load(spec):
        passes = (
            4
            if spec.key == ("devanagari", "legacy_joined")
            else 3
        )
        return _fake_loaded_cell(spec, passes=passes)

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._load_cell",
        fake_load,
    )

    with pytest.raises(
        FinalValidationError,
        match="non-identity scientific configuration differs",
    ):
        load_final_input(path)


def _patch_per_cell_reducers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    boundary_digest: str = "same",
) -> None:
    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._reduce_passes",
        lambda cell: (
            [
                {
                    "cell_id": cell.spec.cell_id,
                    "pass": 1,
                    "metric": "fixture",
                    "value": 1.0,
                }
            ],
            3,
        ),
    )

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._reduce_lexicon",
        lambda cell: SimpleNamespace(
            row_count=4,
            distribution_rows=[],
            length_rows=[],
            reuse_rows=[],
            evidence=[],
            top_order=(),
            top_weights={},
            mass_sketches={},
        ),
    )

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._reduce_analyses",
        lambda cell: SimpleNamespace(
            row_count=2,
            phoneme_count=8,
            id_digest="same",
            ambiguity_rows=[],
            candidate_rows=[],
            document_rows=[],
            length_rows=[],
            evidence=[],
            topk_rule_mass={},
        ),
    )

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._reduce_boundaries",
        lambda cell: SimpleNamespace(
            row_count=2,
            boundary_count=1,
            expected_boundary_total=0.5,
            id_digest=boundary_digest,
            rows=[],
            evidence=[],
        ),
    )

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._reduce_rules",
        lambda cell, **kwargs: (
            [
                {
                    "cell_id": cell.spec.cell_id,
                    "family": "exact_global_rule",
                    "metric": "R1",
                    "expected_usage": 1.0,
                    "normalized_usage": 1.0,
                }
            ],
            1,
        ),
    )

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._reduce_runtime",
        lambda cell, **kwargs: [
            {
                "cell_id": cell.spec.cell_id,
                "family": "fixture",
                "metric": "wall_seconds",
                "value": 1.0,
            }
        ],
    )


def test_final_per_cell_reduction_uses_exactly_five_valid_cells(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _payload())
    payload, specs, invalidated = parse_final_manifest(path)
    loaded = tuple(_fake_loaded_cell(spec) for spec in specs)

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final.load_final_input",
        lambda manifest_path: (payload, loaded, invalidated),
    )
    _patch_per_cell_reducers(monkeypatch)

    result = reduce_final_per_cell(path)

    assert tuple(
        (row["script"], row["condition"])
        for row in result.tables["cells"]
    ) == FINAL_VALID_CELLS
    assert len(result.tables["cells"]) == 5
    assert set(result.lexicons) == {
        f"{script}__{condition}"
        for script, condition in FINAL_VALID_CELLS
    }
    assert set(result.boundaries) == set(result.lexicons)
    assert INVALIDATED_CELL not in {
        (row["script"], row["condition"])
        for row in result.tables["cells"]
    }
    assert "formal_comparisons" not in result.tables
    assert "pairwise_stability" not in result.tables
    assert "failure_mode_indicators" not in result.tables


def test_final_per_cell_reduction_rejects_segment_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _payload())
    payload, specs, invalidated = parse_final_manifest(path)
    loaded = tuple(_fake_loaded_cell(spec) for spec in specs)

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final.load_final_input",
        lambda manifest_path: (payload, loaded, invalidated),
    )
    _patch_per_cell_reducers(
        monkeypatch,
        boundary_digest="different",
    )

    with pytest.raises(
        FinalValidationError,
        match="segment identities/order differ",
    ):
        reduce_final_per_cell(path)


def test_final_per_cell_reduction_translates_legacy_reducer_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _payload())
    payload, specs, invalidated = parse_final_manifest(path)
    loaded = tuple(_fake_loaded_cell(spec) for spec in specs)

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final.load_final_input",
        lambda manifest_path: (payload, loaded, invalidated),
    )
    _patch_per_cell_reducers(monkeypatch)

    def fail_lexicon(cell):
        raise GateValidationError(
            (f"{cell.spec.cell_id}: fixture lexicon failure",)
        )

    monkeypatch.setattr(
        "sktlm.analysis.s1m1_final._reduce_lexicon",
        fail_lexicon,
    )

    with pytest.raises(
        FinalValidationError,
        match="fixture lexicon failure",
    ):
        reduce_final_per_cell(path)


def _formal_comparison_fixture(
    tmp_path: Path,
) -> SimpleNamespace:
    path = _write_manifest(tmp_path, _payload())
    _payload_obj, specs, _invalidated = parse_final_manifest(path)
    loaded = tuple(_fake_loaded_cell(spec) for spec in specs)

    tables = {
        name: []
        for name in (
            "cells",
            "pass_dynamics",
            "lexicon_distribution",
            "lexical_length",
            "reuse_distribution",
            "ambiguity_distribution",
            "boundary_distribution",
            "rule_usage",
            "candidate_scaling",
            "document_distribution",
            "length_strata",
            "runtime_breakdown",
        )
    }

    for index, cell in enumerate(loaded, start=1):
        cell_id = cell.spec.cell_id
        tables["cells"].append(
            {
                "cell_id": cell_id,
                "script": cell.spec.script,
                "condition": cell.spec.condition,
                "lexical_types": 10 * index,
                "expected_boundaries": float(index),
            }
        )
        tables["lexical_length"].append(
            {
                "cell_id": cell_id,
                "weighting": "expected_mass_tail",
                "threshold": "length>=8",
                "mass_fraction": index / 10.0,
            }
        )
        tables["ambiguity_distribution"].append(
            {
                "cell_id": cell_id,
                "family": "segment_posterior",
                "metric": "identity_mass",
                "mean": index / 5.0,
                "estimate_scope": "exact_full_posterior_summary",
            }
        )
        tables["runtime_breakdown"].append(
            {
                "cell_id": cell_id,
                "family": "process_tree",
                "metric": "wall_seconds",
                "value": 100.0 * index,
            }
        )

    return SimpleNamespace(
        loaded=loaded,
        tables=tables,
    )


def test_formal_comparisons_use_exactly_six_designated_pairs(
    tmp_path: Path,
) -> None:
    reduction = _formal_comparison_fixture(tmp_path)

    rows = build_formal_comparisons(reduction)

    assert {row["pair_id"] for row in rows} == {
        pair.pair_id for pair in FORMAL_COMPARISONS
    }
    assert len({row["pair_id"] for row in rows}) == 6
    assert all(
        "iast__continuous"
        not in (row["cell_a"], row["cell_b"])
        for row in rows
    )
    assert not any(
        row["pair_id"].startswith("iast__continuous")
        for row in rows
    )


def test_formal_comparison_scalar_arithmetic_and_scope(
    tmp_path: Path,
) -> None:
    reduction = _formal_comparison_fixture(tmp_path)

    rows = build_formal_comparisons(reduction)
    row = next(
        item
        for item in rows
        if (
            item["pair_id"] == "script_surface_word"
            and item["source_table"] == "ambiguity_distribution"
            and item["row_identity"]
            == "family=segment_posterior|metric=identity_mass"
            and item["value_field"] == "mean"
        )
    )

    assert row["value_a"] == pytest.approx(0.2)
    assert row["value_b"] == pytest.approx(0.6)
    assert row["signed_difference_b_minus_a"] == pytest.approx(0.4)
    assert row["relative_change_from_a"] == pytest.approx(2.0)
    assert row["ratio_b_over_a"] == pytest.approx(3.0)
    assert (
        row["scope_a"]
        == "estimate_scope=exact_full_posterior_summary"
    )
    assert row["scope_b"] == row["scope_a"]


def test_formal_comparison_zero_reference_has_no_ratio_or_relative_change(
    tmp_path: Path,
) -> None:
    reduction = _formal_comparison_fixture(tmp_path)

    for row in reduction.tables["cells"]:
        if (
            row["script"],
            row["condition"],
        ) == ("iast", "surface_word"):
            row["expected_boundaries"] = 0.0
        elif (
            row["script"],
            row["condition"],
        ) == ("devanagari", "surface_word"):
            row["expected_boundaries"] = 2.0

    rows = build_formal_comparisons(reduction)
    row = next(
        item
        for item in rows
        if (
            item["pair_id"] == "script_surface_word"
            and item["source_table"] == "cells"
            and item["value_field"] == "expected_boundaries"
        )
    )

    assert row["value_a"] == 0.0
    assert row["value_b"] == 2.0
    assert row["signed_difference_b_minus_a"] == 2.0
    assert row["relative_change_from_a"] is None
    assert row["ratio_b_over_a"] is None


def test_formal_comparison_keeps_engineering_domain_separate(
    tmp_path: Path,
) -> None:
    reduction = _formal_comparison_fixture(tmp_path)

    rows = build_formal_comparisons(reduction)
    runtime_rows = [
        row
        for row in rows
        if row["source_table"] == "runtime_breakdown"
    ]

    assert runtime_rows
    assert all(row["domain"] == "engineering" for row in runtime_rows)
    assert all(
        row["domain"] != "engineering"
        for row in rows
        if row["source_table"] == "ambiguity_distribution"
    )



def _final_synthesis_fixture(tmp_path: Path) -> tuple[Path, SimpleNamespace]:
    path = _write_manifest(tmp_path, _payload())
    payload, specs, invalidated = parse_final_manifest(path)
    loaded = tuple(_fake_loaded_cell(spec) for spec in specs)
    tables = {name: [] for name in PER_CELL_TABLE_NAMES}
    for index, cell in enumerate(loaded, start=1):
        cid = cell.spec.cell_id
        tables["cells"].append({"cell_id": cid, "script": cell.spec.script, "condition": cell.spec.condition, "run_id": cell.spec.run_id, "metrics_id": cell.spec.metrics_id, "scientific_git_sha": cell.spec.scientific_commit, "segments": 2, "surface_phonemes": 8, "lexical_types": 10 * index, "candidate_boundaries": 2, "expected_boundaries": float(index), "rules": 2})
        tables["pass_dynamics"].append({"cell_id": cid, "pass": 1, "metric": "mean_identity_mass", "value": index / 10.0})
        tables["lexicon_distribution"].append({"cell_id": cid, "family": "diversity", "metric": "diversity", "active_types": 10 * index, "effective_vocabulary_exp_entropy": 5.0 * index, "inverse_simpson_effective_vocabulary": 4.0 * index, "gini_expected_count": index / 10.0})
        tables["lexical_length"].append({"cell_id": cid, "weighting": "expected_mass_tail", "threshold": "length>=8", "mass": float(index), "mass_fraction": index / 10.0})
        tables["reuse_distribution"].append({"cell_id": cid, "family": "reuse_threshold", "metric": "contexts>=2", "type_fraction": index / 10.0, "mass_fraction": index / 20.0, "usage_semantics": "fixture"})
        tables["ambiguity_distribution"].extend((
            {"cell_id": cid, "family": "segment_posterior", "metric": "identity_mass", "count": 2, "mean": index / 5.0, "minimum": index / 10.0, "maximum": index / 4.0, "estimate_scope": "exact_full_posterior_summary"},
            {"cell_id": cid, "family": "segment_posterior", "metric": "latent_mass", "count": 2, "mean": 1.0 - index / 5.0, "minimum": 0.0, "maximum": 1.0, "estimate_scope": "exact_full_posterior_summary"},
        ))
        tables["boundary_distribution"].append({"cell_id": cid, "family": "boundary", "metric": "expected_boundaries_per_segment", "count": 2, "mean": index / 10.0, "quantile_method": "fixture_exact"})
        tables["rule_usage"].append({"cell_id": cid, "family": "exact_global_summary", "metric": "rule_usage", "rule_inventory_size": 2, "rules_with_positive_usage": index, "positive_rule_coverage": index / 5.0, "expected_usage_total": float(index), "shannon_entropy_nats": index / 10.0, "effective_rule_count": 1.0 + index / 10.0, "usage_per_segment": index / 2.0, "usage_per_expected_boundary": 1.0, "usage_per_phoneme": index / 8.0})
        tables["candidate_scaling"].append({"cell_id": cid, "family": "candidate_scaling", "metric": "lexical_edges", "mean": 100.0 * index})
        tables["runtime_breakdown"].append({"cell_id": cid, "family": "process_tree", "metric": "wall_seconds", "value": 1000.0 * index})
    return path, SimpleNamespace(manifest_payload=payload, invalidated=invalidated, loaded=loaded, tables=tables, evidence=[], lexicons={}, boundaries={})


def _fixture_failure_scan(cell) -> list[dict[str, object]]:
    return [
        {"indicator_family": "long_form_lexicalization", "cell_id": cell.spec.cell_id, "metric": "phoneme_length>=8", "type_count": 1, "type_fraction": 0.1, "expected_mass": 1.0, "expected_mass_fraction": 0.1, "scope": "fixture"},
        {"indicator_family": "low_reuse_memorization", "cell_id": cell.spec.cell_id, "metric": "contexts<2", "type_count": 1, "type_fraction": 0.1, "expected_mass": 1.0, "expected_mass_fraction": 0.1, "scope": "fixture"},
    ]


def test_exact_lexicon_failure_indicator_stream(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _payload()); _payload_obj, specs, _invalidated = parse_final_manifest(path)
    cell = _fake_loaded_cell(specs[0]); cell.spec.run_dir.mkdir(parents=True, exist_ok=True)
    (cell.spec.run_dir / "latent_lexicon.tsv").write_text(
        "form_key\tphoneme_ids\texpected_count\tprobability\tnumber_of_surface_variants\tnumber_of_contexts\n"
        "short\ta b c d\t8\t0.8\t10\t10\n"
        "long\ta b c d e f g h\t2\t0.2\t1\t1\n", encoding="utf-8")
    rows = _lexicon_failure_rows(cell)
    long8 = next(row for row in rows if row["indicator_family"] == "long_form_lexicalization" and row["metric"] == "phoneme_length>=8")
    assert long8["type_fraction"] == pytest.approx(0.5); assert long8["expected_mass_fraction"] == pytest.approx(0.2)
    low2 = next(row for row in rows if row["indicator_family"] == "low_reuse_memorization" and row["metric"] == "contexts<2")
    assert low2["type_fraction"] == pytest.approx(0.5); assert low2["expected_mass_fraction"] == pytest.approx(0.2)


def test_failure_indicators_cover_frozen_families(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _path, reduction = _final_synthesis_fixture(tmp_path); formal = build_formal_comparisons(reduction)
    monkeypatch.setattr("sktlm.analysis.s1m1_final._lexicon_failure_rows", _fixture_failure_scan)
    families = {row["indicator_family"] for row in build_failure_mode_indicators(reduction, formal)}
    assert {"long_form_lexicalization", "low_reuse_memorization", "identity_latent_concentration", "spacing_removal_lexicalization", "devanagari_continuous_stress", "sandhi_use_displacement"} <= families


def test_decision_inputs_are_objective_synthesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _path, reduction = _final_synthesis_fixture(tmp_path); formal = build_formal_comparisons(reduction)
    monkeypatch.setattr("sktlm.analysis.s1m1_final._lexicon_failure_rows", _fixture_failure_scan)
    failures = build_failure_mode_indicators(reduction, formal); payload = build_decision_inputs(reduction, formal, failures)
    assert payload["status"] == "objective_evidence_only"; assert set(payload["designated_effects"]) == {"controlled_script", "controlled_spacing", "continuous_stress"}
    assert payload["engineering_evidence"]; assert payload["computational_diagnostics"]; assert "final_conclusion" not in payload; assert "needs_s1m2" not in payload


def test_complete_final_reduction_and_output_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, reduction = _final_synthesis_fixture(tmp_path)
    monkeypatch.setattr("sktlm.analysis.s1m1_final.reduce_final_per_cell", lambda manifest_path: reduction)
    monkeypatch.setattr("sktlm.analysis.s1m1_final._lexicon_failure_rows", _fixture_failure_scan)
    monkeypatch.setattr("sktlm.analysis.s1m1_final._build_sources", lambda manifest_path, final_reduction: [])
    result = reduce_final_manifest(path)
    assert result["schema_version"] == "sktlm-s1m1-final-analysis/v1"; assert tuple(result["tables"]) == FINAL_TABLE_NAMES
    assert {row["pair_id"] for row in result["tables"]["formal_comparisons"]} == {pair.pair_id for pair in FORMAL_COMPARISONS}
    output_dir = tmp_path / "final-output"; write_final_outputs(result, output_dir)
    expected = {"manifest.json", "cells.tsv", "pass_dynamics.tsv", "lexicon_distribution.tsv", "lexical_length.tsv", "reuse_distribution.tsv", "ambiguity_distribution.tsv", "boundary_distribution.tsv", "rule_usage.tsv", "candidate_scaling.tsv", "document_distribution.tsv", "length_strata.tsv", "runtime_breakdown.tsv", "formal_comparisons.tsv", "failure_mode_indicators.tsv", "evidence_samples.jsonl", "decision_inputs.json", "summary.md"}
    assert {item.name for item in output_dir.iterdir()} == expected
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8")); assert len(manifest["valid_cells"]) == 5; assert len(manifest["formal_comparisons"]) == 6
    with pytest.raises(FileExistsError, match="refusing to overwrite"): write_final_outputs(result, output_dir)

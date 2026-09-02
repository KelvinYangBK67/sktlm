from __future__ import annotations

import json
from pathlib import Path

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

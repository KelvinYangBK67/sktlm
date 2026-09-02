"""Tests for the historical and representation-valid M0 matrix contracts."""

from collections import Counter
from pathlib import Path

import pytest

from sktlm.experiments.baselines.matrix import (
    RETIREMENT_DECISION_ID,
    RETIREMENT_REASON,
    BaselineCell,
    BaselineMatrixSettings,
    ConditionRecord,
    build_plan,
    build_run_specs,
    formal_matrix,
    historical_matrix,
    retired_matrix,
    validate_condition_manifest,
    validate_formal_matrix,
)
from sktlm.experiments.baselines.production import build_production_queue


def test_manifest_retains_22_historical_and_selects_18_valid_cells() -> None:
    historical = historical_matrix()
    valid = validate_formal_matrix(formal_matrix())
    retired = retired_matrix()

    assert len(historical) == 22
    assert len({cell.condition_id for cell in historical}) == 22
    assert len(valid) == 18
    assert len(retired) == 4
    assert Counter(cell.method for cell in valid) == {
        "bpe": 5,
        "unigram": 5,
        "unicode_codepoint": 5,
        "aksara_safe_bpe": 1,
        "surface_lattice": 2,
    }
    assert {cell.condition_id for cell in retired} == {
        "bpe__iast__continuous",
        "unigram__iast__continuous",
        "unicode_codepoint__iast__continuous",
        "surface_lattice__iast__continuous",
    }


@pytest.mark.parametrize("obsolete_spacing", ["observed", "lexical_boundary"])
def test_obsolete_spacing_names_are_not_formal(obsolete_spacing: str) -> None:
    with pytest.raises(ValueError, match="unsupported formal spacing"):
        BaselineCell("bpe", "iast", obsolete_spacing)


def test_method_specific_historical_domains_are_enforced() -> None:
    with pytest.raises(ValueError, match="devanagari/continuous"):
        BaselineCell("aksara_safe_bpe", "iast", "continuous")
    with pytest.raises(ValueError, match="only for IAST"):
        BaselineCell("surface_lattice", "devanagari", "continuous")


def test_valid_matrix_and_historical_manifest_fail_closed() -> None:
    cells = formal_matrix()
    with pytest.raises(ValueError, match="duplicate"):
        validate_formal_matrix((*cells, cells[0]))
    with pytest.raises(ValueError, match="mismatch"):
        validate_formal_matrix(cells[:-1])

    settings = BaselineMatrixSettings.from_yaml(
        Path("configs/experiments/baselines/m0_matrix.yaml")
    )
    records = settings.condition_manifest
    retired = next(record for record in records if record.status == "retired")
    invalid = ConditionRecord(
        cell=retired.cell,
        status="retired",
        decision_id=RETIREMENT_DECISION_ID,
        reason=RETIREMENT_REASON,
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_condition_manifest((*records, invalid))


def test_run_specs_address_all_18_valid_cells_independently() -> None:
    config_path = Path("configs/experiments/baselines/m0_matrix.yaml")
    settings = BaselineMatrixSettings.from_yaml(config_path)
    specs = build_run_specs(settings)
    assert len(specs) == 18
    assert len({spec.artifact_dir for spec in specs}) == 18
    assert all(spec.cell.spacing != "continuous" for spec in specs if spec.cell.script == "iast")

    plan = build_plan(settings)
    assert plan["historical_cell_count"] == 22
    assert plan["valid_production_cell_count"] == 18
    assert plan["retired_cell_count"] == 4
    assert plan["tokenizer_supported_cell_count"] == 18
    assert plan["pending_method_contract_cell_count"] == 0
    assert all(cell["condition_status"] == "valid" for cell in plan["cells"])
    assert all(cell["retirement_reason"] is None for cell in plan["cells"])
    assert all(len(cell["required_provenance"]) == 14 for cell in plan["cells"])

    queue = build_production_queue(settings, config_path=config_path)
    assert queue["scheduled_job_count"] == 18
    assert queue["launches_jobs"] is False
    assert all("__iast__continuous" not in job["condition_id"] for job in queue["jobs"])

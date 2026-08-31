"""Tests for the exact formal M₀ baseline matrix contract."""

from collections import Counter
from pathlib import Path

import pytest

from sktlm.experiments.baselines.matrix import (
    BaselineCell,
    BaselineMatrixSettings,
    build_plan,
    build_run_specs,
    formal_matrix,
    validate_formal_matrix,
)


def test_formal_matrix_contains_exactly_22_unique_cells() -> None:
    cells = validate_formal_matrix(formal_matrix())
    assert len(cells) == 22
    assert len({cell.condition_id for cell in cells}) == 22
    assert Counter(cell.method for cell in cells) == {
        "bpe": 6,
        "unigram": 6,
        "unicode_codepoint": 6,
        "aksara_safe_bpe": 1,
        "surface_lattice": 3,
    }


@pytest.mark.parametrize("obsolete_spacing", ["observed", "lexical_boundary"])
def test_obsolete_spacing_names_are_not_formal(obsolete_spacing: str) -> None:
    with pytest.raises(ValueError, match="unsupported formal spacing"):
        BaselineCell("bpe", "iast", obsolete_spacing)


def test_method_specific_domains_are_enforced() -> None:
    with pytest.raises(ValueError, match="devanagari/continuous"):
        BaselineCell("aksara_safe_bpe", "iast", "continuous")
    with pytest.raises(ValueError, match="only for IAST"):
        BaselineCell("surface_lattice", "devanagari", "continuous")


def test_matrix_validator_rejects_missing_and_duplicate_cells() -> None:
    cells = formal_matrix()
    with pytest.raises(ValueError, match="duplicate"):
        validate_formal_matrix((*cells, cells[0]))
    with pytest.raises(ValueError, match="mismatch"):
        validate_formal_matrix(cells[:-1])


def test_run_specs_address_all_22_implemented_cells_independently() -> None:
    settings = BaselineMatrixSettings.from_yaml(
        Path("configs/experiments/baselines/m0_matrix.yaml")
    )
    specs = build_run_specs(settings)
    assert sum(spec.cell.tokenizer_supported for spec in specs) == 22
    assert sum(not spec.cell.tokenizer_supported for spec in specs) == 0
    assert len({spec.artifact_dir for spec in specs}) == 22

    plan = build_plan(settings)
    assert plan["formal_cell_count"] == 22
    assert plan["tokenizer_supported_cell_count"] == 22
    assert plan["pending_method_contract_cell_count"] == 0
    assert all(cell["corpus_freeze_id"] == settings.freeze_id for cell in plan["cells"])
    assert all(cell["implementation_status"] == "implemented" for cell in plan["cells"])
    assert all(cell["tokenizer"] is not None for cell in plan["cells"])
    assert all(len(cell["required_provenance"]) == 11 for cell in plan["cells"])

"""Tests for first-cell failure classification."""

import json
from pathlib import Path

import pytest

from sktlm.corpus.dataset import file_sha256
from sktlm.experiments.baselines.audit import audit_first_production_cell
from sktlm.experiments.baselines.matrix import (
    BaselineMatrixSettings,
    RetiredConditionError,
)


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _complete(path: Path, condition_id: str) -> None:
    files = {
        item.relative_to(path).as_posix(): file_sha256(item)
        for item in path.rglob("*")
        if item.is_file() and item.name != "COMPLETED.json"
    }
    _json(
        path / "COMPLETED.json",
        {
            "schema_version": "m0-baseline-completion-v1",
            "condition_id": condition_id,
            "condition_status": "valid",
            "run_scope": "formal_production",
            "files": files,
        },
    )


def _settings() -> BaselineMatrixSettings:
    return BaselineMatrixSettings.from_yaml(
        Path("configs/experiments/baselines/m0_matrix.yaml")
    )


def test_audit_classifies_missing_bundle_as_engineering_failure(tmp_path) -> None:
    result = audit_first_production_cell(
        _settings(), "unicode_codepoint__devanagari__surface_word", tmp_path / "missing"
    )
    assert result["classification"] == "engineering_failure"


def test_audit_distinguishes_scientific_semantics_failure(tmp_path) -> None:
    condition_id = "unicode_codepoint__devanagari__surface_word"
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    provenance = {
        "run_scope": "formal_production",
        "training_initialization": "fresh_per_cell",
        "training_instance_id": "unique",
        "code_commit": "a" * 40,
        "corpus_freeze_id": _settings().freeze_id,
        "data_fingerprint_sha256": "b" * 64,
        "tokenizer_fingerprint_sha256": "c" * 64,
        "environment_fingerprint_sha256": "d" * 64,
        "condition_status": "valid",
    }
    metrics = {
        "run_scope": "formal_production",
        "condition_id": condition_id,
        "condition_status": "valid",
        "runtime_seconds": 1.0,
        "peak_rss_bytes": 1024,
        "common_downstream_checkpoint": "downstream_lm/model.pt",
        "unk_count": 1,
        "unk_rate": 2.0,
        "unknown_semantics": "fixture",
        "common_downstream_status": "complete",
        "common_downstream_finite": True,
        "common_downstream_bits_per_character": 1.0,
        "common_downstream_bits_per_byte": 1.0,
        "bits_per_canonical_unit": 1.0,
        "script_specific_diagnostic": {"applicability": "applicable"},
    }
    for name, value in (
        ("provenance", provenance),
        ("metrics", metrics),
        ("data_fingerprint", {}),
        ("tokenizer_fingerprint", {}),
        ("environment", {}),
    ):
        _json(artifact / f"{name}.json", value)
    (artifact / "requirements-freeze.txt").write_text("x==1\n", encoding="utf-8")
    checkpoint = artifact / "downstream_lm/model.pt"
    checkpoint.parent.mkdir()
    checkpoint.write_bytes(b"checkpoint")
    _complete(artifact, condition_id)

    result = audit_first_production_cell(_settings(), condition_id, artifact)
    assert result["classification"] == "scientific_semantics_failure"
    assert all(check["passed"] for check in result["engineering_checks"])
    assert not all(check["passed"] for check in result["scientific_semantics_checks"])


def test_audit_rejects_retired_first_cell(tmp_path) -> None:
    with pytest.raises(RetiredConditionError, match="retired condition"):
        audit_first_production_cell(
            _settings(), "bpe__iast__continuous", tmp_path / "artifact"
        )

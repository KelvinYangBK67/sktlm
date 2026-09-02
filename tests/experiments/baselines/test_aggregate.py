"""Fail-closed matrix aggregation tests."""

import json
from pathlib import Path

import pytest
import yaml

from sktlm.corpus.dataset import file_sha256
from sktlm.experiments.artifacts import payload_sha256
from sktlm.experiments.baselines.aggregate import (
    AggregateValidationError,
    aggregate_formal_results,
)
from sktlm.experiments.baselines.matrix import (
    FROZEN_M0_ID,
    REQUIRED_PROVENANCE,
    BaselineMatrixSettings,
    build_run_specs,
)


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _finish(artifact_dir: Path, condition_id: str) -> None:
    files = {
        path.relative_to(artifact_dir).as_posix(): file_sha256(path)
        for path in sorted(artifact_dir.rglob("*"))
        if path.is_file() and path.name != "COMPLETED.json"
    }
    _write_json(
        artifact_dir / "COMPLETED.json",
        {
            "schema_version": "m0-baseline-completion-v1",
            "condition_id": condition_id,
            "condition_status": "valid",
            "run_scope": "formal_production",
            "files": files,
        },
    )


def _build_complete_matrix(tmp_path: Path) -> tuple[BaselineMatrixSettings, Path]:
    base = BaselineMatrixSettings.from_yaml(
        Path("configs/experiments/baselines/m0_matrix.yaml")
    )
    artifact_root = tmp_path / "formal"
    settings = BaselineMatrixSettings(
        freeze_id=base.freeze_id,
        canonical_manifest=base.canonical_manifest,
        representation_manifest=base.representation_manifest,
        artifact_root=artifact_root,
        seed=base.seed,
        vocab_size=base.vocab_size,
        condition_manifest_version=base.condition_manifest_version,
        condition_manifest=base.condition_manifest,
        downstream_lm=base.downstream_lm,
    )
    requirements = b"pytest==1\n"
    requirements_hash = __import__("hashlib").sha256(requirements).hexdigest()
    for index, spec in enumerate(build_run_specs(settings)):
        condition_id = spec.cell.condition_id
        artifact_dir = spec.artifact_dir
        artifact_dir.mkdir(parents=True)
        config = {
            "condition_id": condition_id,
            "limits": {"max_train_segments": None, "max_eval_segments": None},
            "common_downstream_lm": {
                "enabled": True,
                "contract": settings.downstream_lm.as_dict(),
                "runtime_device_override": None,
                "runtime_max_steps_override": None,
            },
        }
        (artifact_dir / "config.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        data = {
            "corpus_freeze_id": FROZEN_M0_ID,
            "script": spec.cell.script,
            "spacing": spec.cell.spacing,
        }
        data["fingerprint_sha256"] = payload_sha256(data)
        tokenizer = {"condition_id": condition_id}
        tokenizer["fingerprint_sha256"] = payload_sha256(tokenizer)
        environment = {
            "schema_version": "sktlm-environment-v1",
            "requirements_freeze_sha256": requirements_hash,
        }
        environment["environment_fingerprint_sha256"] = payload_sha256(environment)
        _write_json(artifact_dir / "data_fingerprint.json", data)
        _write_json(artifact_dir / "tokenizer_fingerprint.json", tokenizer)
        _write_json(artifact_dir / "environment.json", environment)
        (artifact_dir / "requirements-freeze.txt").write_bytes(requirements)
        (artifact_dir / "git_commit.txt").write_text("a" * 40 + "\n", encoding="utf-8")
        provenance = {
            "method": spec.cell.method,
            "script": spec.cell.script,
            "spacing": spec.cell.spacing,
            "condition_status": "valid",
            "retirement_reason": None,
            "condition_manifest_version": settings.condition_manifest_version,
            "run_scope": "formal_production",
            "config": config,
            "config_sha256": payload_sha256(config),
            "seed": settings.seed,
            "code_commit": "a" * 40,
            "corpus_freeze_id": FROZEN_M0_ID,
            "canonical_manifest_sha256": "b" * 64,
            "representation_manifest_sha256": "c" * 64,
            "data_fingerprint_sha256": data["fingerprint_sha256"],
            "tokenizer_fingerprint_sha256": tokenizer["fingerprint_sha256"],
            "environment_fingerprint_sha256": environment[
                "environment_fingerprint_sha256"
            ],
            "training_initialization": "fresh_per_cell",
            "training_instance_id": f"instance-{index:02d}",
            "software_versions": {"python": "3.11"},
            "artifact_location": artifact_dir.as_posix(),
        }
        assert set(REQUIRED_PROVENANCE) <= set(provenance)
        _write_json(artifact_dir / "provenance.json", provenance)
        metrics = {
            "condition_id": condition_id,
            "condition_status": "valid",
            "run_scope": "formal_production",
            "common_downstream_status": "complete",
            "common_downstream_finite": True,
            "common_downstream_bits_per_character": 1.0 + index,
            "common_downstream_bits_per_byte": 0.5 + index,
            "bits_per_canonical_unit": 1.1 + index,
            "bits_per_character": 1.0 + index,
            "bits_per_byte": 0.5 + index,
            "unk_count": 0,
            "unk_rate": 0.0,
            "unknown_semantics": "fixture",
            "runtime_seconds": 1.0,
            "peak_rss_bytes": 1024,
            "token_count": 10,
            "occupied_token_types": 5,
        }
        _write_json(artifact_dir / "metrics.json", metrics)
        _finish(artifact_dir, condition_id)
    return settings, artifact_root


def test_complete_18_cell_aggregate_has_valid_comparison_structure(tmp_path) -> None:
    settings, artifact_root = _build_complete_matrix(tmp_path)
    aggregate = aggregate_formal_results(settings, artifact_root)
    assert aggregate["complete_valid_cell_count"] == 18
    assert len(aggregate["results"]) == 18
    assert aggregate["comparisons"]["continuous_script_pair_generated"] is False
    assert aggregate["comparisons"]["spacing_comparisons"]["iast"] == [
        "surface_word",
        "legacy_joined",
    ]


def test_aggregate_rejects_missing_or_duplicate_cells(tmp_path) -> None:
    settings, artifact_root = _build_complete_matrix(tmp_path)
    missing = artifact_root / "bpe__iast__surface_word"
    moved = tmp_path / "held"
    missing.rename(moved)
    with pytest.raises(AggregateValidationError, match="condition set mismatch"):
        aggregate_formal_results(settings, artifact_root)
    moved.rename(missing)
    duplicate = missing / "seed_99"
    duplicate.mkdir()
    with pytest.raises(AggregateValidationError, match="duplicate or wrong-seed"):
        aggregate_formal_results(settings, artifact_root)


def test_aggregate_rejects_retired_artifact_even_if_valid_cells_are_complete(tmp_path) -> None:
    settings, artifact_root = _build_complete_matrix(tmp_path)
    (artifact_root / "bpe__iast__continuous").mkdir()
    with pytest.raises(AggregateValidationError, match="retired condition"):
        aggregate_formal_results(settings, artifact_root)


def test_aggregate_rejects_tampered_data_fingerprint(tmp_path) -> None:
    settings, artifact_root = _build_complete_matrix(tmp_path)
    artifact_dir = artifact_root / "bpe__iast__surface_word/seed_0"
    data_path = artifact_dir / "data_fingerprint.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data["script"] = "devanagari"
    _write_json(data_path, data)
    _finish(artifact_dir, "bpe__iast__surface_word")
    with pytest.raises(AggregateValidationError, match="fingerprint mismatch"):
        aggregate_formal_results(settings, artifact_root)

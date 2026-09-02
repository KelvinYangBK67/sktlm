"""Tests for the independent TransLIST adapter."""

import json

import pytest

from sktlm.experiments.baselines.translist import run_translist_adapter
from sktlm.representations.validity import RetiredRepresentationError


def _write(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _row(segment_id, surface, desandhi, *, spacing="surface_word"):
    return {
        "schema_version": "sktlm-translist-adapter-v1",
        "document_id": "doc-test",
        "segment_id": segment_id,
        "split": "test",
        "script": "iast",
        "spacing": spacing,
        "input_text": "devopi",
        "surface_segments": surface,
        "desandhi_segments": desandhi,
    }


def test_translist_adapter_is_separate_and_scores_segmentation_and_desandhi(tmp_path) -> None:
    references = tmp_path / "references.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    _write(references, [_row("seg-1", ["devo", "pi"], ["devaḥ", "api"])])
    _write(predictions, [_row("seg-1", ["devo", "pi"], ["devaḥ", "api"])])
    artifact_dir = run_translist_adapter(
        references, predictions, tmp_path / "artifacts", repo_root=tmp_path
    )
    metrics = json.loads((artifact_dir / "metrics.json").read_text(encoding="utf-8"))
    provenance = json.loads(
        (artifact_dir / "provenance.json").read_text(encoding="utf-8")
    )
    assert metrics["matrix_condition"] is False
    assert metrics["segmentation_boundary_f1"] == 1.0
    assert metrics["desandhi_exact_match_rate"] == 1.0
    assert metrics["split_identity_sha256"] == provenance["split_identity_sha256"]
    assert (artifact_dir / "environment.json").is_file()
    assert (artifact_dir / "requirements-freeze.txt").is_file()


def test_translist_adapter_rejects_identity_mismatch(tmp_path) -> None:
    references = tmp_path / "references.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    _write(references, [_row("seg-1", ["devo", "pi"], ["devaḥ", "api"])])
    _write(predictions, [_row("seg-2", ["devo", "pi"], ["devaḥ", "api"])])
    with pytest.raises(ValueError, match="membership mismatch"):
        run_translist_adapter(references, predictions, tmp_path / "artifacts")


def test_translist_adapter_rejects_iast_continuous(tmp_path) -> None:
    references = tmp_path / "references.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    row = _row("seg-1", ["devopi"], ["devaḥ", "api"], spacing="continuous")
    _write(references, [row])
    _write(predictions, [row])
    with pytest.raises(RetiredRepresentationError, match="not injective"):
        run_translist_adapter(references, predictions, tmp_path / "artifacts")

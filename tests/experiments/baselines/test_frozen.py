"""Tests for direct, manifest-addressed frozen representation loading."""

import csv
import json
from pathlib import Path

import pytest

from sktlm.experiments.baselines.frozen import load_frozen_catalog
from sktlm.experiments.baselines.matrix import (
    FROZEN_M0_ID,
    FORMAL_SCRIPTS,
    FORMAL_SPACINGS,
    BaselineMatrixSettings,
    REQUIRED_PROVENANCE,
)
from sktlm.experiments.baselines.runner import run_supported_cell


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_fixture(tmp_path: Path) -> BaselineMatrixSettings:
    freeze_id = FROZEN_M0_ID
    canonical_manifest = Path("data/manifests/canonical.csv")
    representation_manifest = Path("data/manifests/representations.csv")
    documents = [
        {
            "freeze_input_path": "a/doc_a.txt",
            "document_id": "doc_a",
            "split": "train",
            "source": "gretil",
            "layer": "veda",
            "freeze_id": freeze_id,
        },
        {
            "freeze_input_path": "b/doc_b.txt",
            "document_id": "doc_b",
            "split": "test",
            "source": "gretil",
            "layer": "epic",
            "freeze_id": freeze_id,
        },
    ]
    _write_csv(
        tmp_path / canonical_manifest,
        ["freeze_input_path", "document_id", "split", "source", "layer", "freeze_id"],
        documents,
    )

    representation_rows: list[dict[str, str]] = []
    for script in FORMAL_SCRIPTS:
        for spacing in FORMAL_SPACINGS:
            for document in documents:
                relative = document["freeze_input_path"]
                representation_path = Path("data/representations") / script / spacing / relative
                target = tmp_path / representation_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "first line\n\nthird line\n" if relative.startswith("a/") else "test line\n",
                    encoding="utf-8",
                )
                representation_rows.append(
                    {
                        "freeze_id": freeze_id,
                        "relative_path": relative,
                        "script": script,
                        "condition": spacing,
                        "representation_path": representation_path.as_posix(),
                        "representation_hash": f"hash-{script}-{spacing}-{relative}",
                    }
                )
    _write_csv(
        tmp_path / representation_manifest,
        [
            "freeze_id",
            "relative_path",
            "script",
            "condition",
            "representation_path",
            "representation_hash",
        ],
        representation_rows,
    )
    return BaselineMatrixSettings(
        freeze_id=freeze_id,
        canonical_manifest=canonical_manifest,
        representation_manifest=representation_manifest,
        artifact_root=Path("artifacts/baselines/test"),
        seed=0,
        vocab_size=32,
    )


def test_catalog_requires_all_six_conditions_and_directly_loads_frozen_text(tmp_path) -> None:
    settings = _build_fixture(tmp_path)
    catalog = load_frozen_catalog(
        settings,
        repo_root=tmp_path,
        expected_documents=2,
    )
    assert catalog.document_count == 2
    assert catalog.representation_file_count == 12
    assert set(catalog.files_by_condition) == {
        (script, spacing) for script in FORMAL_SCRIPTS for spacing in FORMAL_SPACINGS
    }

    segments = list(catalog.iter_segments("iast", "surface_word", splits={"train"}))
    assert [segment.text for segment in segments] == ["first line", "third line"]
    assert [segment.segment_id for segment in segments] == [
        "doc_a:l00000001",
        "doc_a:l00000003",
    ]
    assert all(segment.script == "iast" for segment in segments)
    assert all(segment.spacing == "surface_word" for segment in segments)


def test_catalog_segment_limit_is_bounded(tmp_path) -> None:
    settings = _build_fixture(tmp_path)
    catalog = load_frozen_catalog(
        settings,
        repo_root=tmp_path,
        expected_documents=2,
    )
    segments = list(catalog.iter_segments("devanagari", "continuous", max_segments=1))
    assert len(segments) == 1


def test_supported_cell_reads_frozen_text_and_writes_complete_provenance(tmp_path) -> None:
    settings = _build_fixture(tmp_path)
    artifact_dir = run_supported_cell(
        settings,
        "unicode_codepoint__iast__surface_word",
        repo_root=tmp_path,
        max_train_segments=1,
        max_eval_segments=1,
        prediction_examples=1,
        expected_documents=2,
        require_clean_git=False,
    )

    assert artifact_dir == tmp_path / "artifacts/baselines/test" / (
        "unicode_codepoint__iast__surface_word/seed_0"
    )
    assert {path.name for path in artifact_dir.iterdir()} == {
        "config.yaml",
        "metrics.json",
        "provenance.json",
        "data_fingerprint.json",
        "tokenizer_fingerprint.json",
        "git_commit.txt",
        "predictions.jsonl",
        "logs.txt",
        "result.csv",
    }
    provenance = json.loads((artifact_dir / "provenance.json").read_text(encoding="utf-8"))
    assert set(REQUIRED_PROVENANCE) <= set(provenance)
    assert provenance["corpus_freeze_id"] == FROZEN_M0_ID
    assert provenance["software_versions"]["python"]

    fingerprint = json.loads(
        (artifact_dir / "data_fingerprint.json").read_text(encoding="utf-8")
    )
    assert fingerprint["train"]["segment_count"] == 1
    assert fingerprint["evaluation"]["segment_count"] == 1
    assert fingerprint["train"]["declared_representation_set_sha256"]
    assert fingerprint["fingerprint_sha256"]

    prediction = json.loads(
        (artifact_dir / "predictions.jsonl").read_text(encoding="utf-8").strip()
    )
    assert prediction["text"] == "test line"

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_supported_cell(
            settings,
            "unicode_codepoint__iast__surface_word",
            repo_root=tmp_path,
            max_train_segments=1,
            max_eval_segments=1,
            expected_documents=2,
            require_clean_git=False,
        )


def test_supported_bpe_cell_fits_only_from_frozen_train_segments(tmp_path) -> None:
    settings = _build_fixture(tmp_path)
    artifact_dir = run_supported_cell(
        settings,
        "bpe__iast__continuous",
        repo_root=tmp_path,
        max_train_segments=2,
        max_eval_segments=1,
        prediction_examples=0,
        expected_documents=2,
        require_clean_git=False,
    )

    model_path = artifact_dir / "tokenizer" / "bpe_32.model"
    assert model_path.is_file()
    assert not (artifact_dir / "tokenizer" / "bpe_32_segments.txt").exists()
    tokenizer_fingerprint = json.loads(
        (artifact_dir / "tokenizer_fingerprint.json").read_text(encoding="utf-8")
    )
    assert tokenizer_fingerprint["runtime"]["model_sha256"]


def test_pending_method_contract_cannot_run_through_a_substitute(tmp_path) -> None:
    settings = _build_fixture(tmp_path)
    with pytest.raises(NotImplementedError, match="no substitute is allowed"):
        run_supported_cell(
            settings,
            "surface_lattice__iast__continuous",
            repo_root=tmp_path,
            expected_documents=2,
            require_clean_git=False,
        )


def test_supported_cell_requires_reproducible_git_state_by_default(tmp_path) -> None:
    settings = _build_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="requires a Git commit"):
        run_supported_cell(
            settings,
            "unicode_codepoint__iast__surface_word",
            repo_root=tmp_path,
            expected_documents=2,
        )

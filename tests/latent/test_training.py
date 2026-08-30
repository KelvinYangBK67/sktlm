from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import sktlm.latent.training as latent_training
from sktlm.latent.store import LexiconStore
from sktlm.latent.training import EXPECTED_FREEZE_ID, TrainingConfig, run_training


def test_bounded_training_writes_research_artifacts(tmp_path: Path) -> None:
    corpus_path = tmp_path / "surface.txt"
    corpus_path.write_text(
        "devo'pi devaḥ ca api ca\n"
        "rāmo'pi rāmaḥ ca api tat\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "representations.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "freeze_id",
                "relative_path",
                "script",
                "condition",
                "representation_path",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": "tiny.txt",
                "script": "iast",
                "condition": "surface_word",
                "representation_path": str(corpus_path),
            }
        )

    result = run_training(
        TrainingConfig(
            manifest=manifest,
            output_root=tmp_path / "artifacts",
            run_id="tiny",
            passes=2,
            analysis_top_k=4,
        ),
        repo_root=Path("."),
    )

    expected = {
        "config.json",
        "provenance.json",
        "checkpoint.json",
        "iteration_metrics.json",
        "learner.sqlite",
        "latent_lexicon.tsv",
        "analyses.jsonl",
        "boundary_posteriors.jsonl",
        "rule_usage.tsv",
        "summary.json",
        "inspection_report.md",
    }
    assert expected <= {path.name for path in result.run_dir.iterdir()}
    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["segments"] == 2
    assert summary["complexity"]["active_lexical_types"] > 0
    analysis = json.loads(
        (result.run_dir / "analyses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert analysis["top_analyses"]
    assert "residual_posterior" in analysis


def _write_resume_fixture(tmp_path: Path) -> Path:
    manifest = tmp_path / "representations.csv"
    rows = []
    for index, text in enumerate(
        (
            "devo'pi devaḥ ca api ca\n",
            "rāmo'pi rāmaḥ ca api tat\n",
        )
    ):
        corpus_path = tmp_path / f"surface-{index}.txt"
        corpus_path.write_text(text, encoding="utf-8")
        rows.append(
            {
                "freeze_id": EXPECTED_FREEZE_ID,
                "relative_path": f"tiny-{index}.txt",
                "script": "iast",
                "condition": "surface_word",
                "representation_path": str(corpus_path),
            }
        )
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "freeze_id",
                "relative_path",
                "script",
                "condition",
                "representation_path",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def _run_resume_fixture(
    tmp_path: Path,
    manifest: Path,
    run_id: str,
    *,
    resume: bool = False,
) -> Path:
    return run_training(
        TrainingConfig(
            manifest=manifest,
            output_root=tmp_path / "artifacts",
            run_id=run_id,
            passes=1,
            analysis_top_k=4,
            flush_types=1,
            resume=resume,
        ),
        repo_root=Path("."),
    ).run_dir


def _assert_same_scientific_outputs(reference: Path, resumed: Path) -> None:
    for name in (
        "iteration_metrics.json",
        "latent_lexicon.tsv",
        "analyses.jsonl",
        "boundary_posteriors.jsonl",
        "rule_usage.tsv",
        "summary.json",
    ):
        assert (resumed / name).read_bytes() == (reference / name).read_bytes()


def test_resume_rolls_back_partial_document_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_resume_fixture(tmp_path)
    reference = _run_resume_fixture(tmp_path, manifest, "reference")
    original_commit = LexiconStore.commit_document
    crashed = False

    def crash_before_commit(
        self: LexiconStore,
        checkpoint: dict[str, object],
    ) -> None:
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("simulated crash after count writes")
        original_commit(self, checkpoint)

    monkeypatch.setattr(LexiconStore, "commit_document", crash_before_commit)
    with pytest.raises(RuntimeError, match="simulated crash"):
        _run_resume_fixture(tmp_path, manifest, "crashed")
    monkeypatch.setattr(LexiconStore, "commit_document", original_commit)

    resumed = _run_resume_fixture(tmp_path, manifest, "crashed", resume=True)
    _assert_same_scientific_outputs(reference, resumed)


def test_resume_uses_database_checkpoint_after_json_lags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_resume_fixture(tmp_path)
    reference = _run_resume_fixture(tmp_path, manifest, "reference")
    original_save = latent_training._save_checkpoint
    crashed = False

    def crash_after_commit(path: Path, checkpoint: dict[str, object]) -> None:
        nonlocal crashed
        if (
            not crashed
            and checkpoint.get("active_pass") == 1
            and checkpoint.get("next_document_index") == 1
        ):
            crashed = True
            raise RuntimeError("simulated crash after document commit")
        original_save(path, checkpoint)

    monkeypatch.setattr(latent_training, "_save_checkpoint", crash_after_commit)
    with pytest.raises(RuntimeError, match="simulated crash"):
        _run_resume_fixture(tmp_path, manifest, "json-lag")
    monkeypatch.setattr(latent_training, "_save_checkpoint", original_save)

    resumed = _run_resume_fixture(tmp_path, manifest, "json-lag", resume=True)
    _assert_same_scientific_outputs(reference, resumed)


def test_legacy_partial_run_is_not_resumed(tmp_path: Path) -> None:
    manifest = _write_resume_fixture(tmp_path)
    run_dir = tmp_path / "artifacts" / "legacy"
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "completed_passes": 0,
                "active_pass": 1,
                "next_document_index": 1,
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    store = LexiconStore(run_dir / "learner.sqlite")
    store.set_metadata(
        "config_signature",
        latent_training._config_signature(
            TrainingConfig(
                manifest=manifest,
                output_root=tmp_path / "artifacts",
                run_id="legacy",
                passes=1,
                analysis_top_k=4,
                flush_types=1,
            )
        ),
    )
    store.begin_count_pass(
        resume=False,
        checkpoint={
            "completed_passes": 0,
            "active_pass": 1,
            "next_document_index": 1,
            "history": [],
        },
    )
    store.connection.execute(
        "DELETE FROM metadata WHERE key = 'training_checkpoint'"
    )
    store.connection.commit()
    store.close()

    with pytest.raises(RuntimeError, match="cannot be resumed safely"):
        _run_resume_fixture(tmp_path, manifest, "legacy", resume=True)

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

import sktlm.latent.training as latent_training
from sktlm.experiments.training.s1m2_lexeme_probe import (
    _read_challenge,
    _read_extra_challenge,
    _validate_held_out,
    build_arg_parser,
    evaluate_challenge,
)
from sktlm.latent.training import (
    DiagnosticCorpusSource,
    S1M2_MODEL,
    TrainingConfig,
    _file_sha256,
    load_documents,
    run_training,
)


def _diagnostic_fixture(tmp_path: Path) -> tuple[DiagnosticCorpusSource, list[dict]]:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("devaḥ ca\nrāmaḥ ca\n", encoding="utf-8")
    challenge = tmp_path / "challenge.jsonl"
    challenge.write_text(
        json.dumps(
            {
                "target_id": "noun_high_deva",
                "text": "devaḥ api",
                "matches": [
                    {"form": "devaḥ", "unsandhied": "devaḥ", "lemma": "deva"}
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return (
        DiagnosticCorpusSource(
            corpus=corpus,
            corpus_sha256=_file_sha256(corpus),
            challenge=challenge,
            challenge_sha256=_file_sha256(challenge),
            target_id="noun_high_deva",
            level="E000",
        ),
        _read_challenge(challenge),
    )


def test_formal_manifest_still_rejects_wrong_freeze(tmp_path: Path) -> None:
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
                "freeze_id": "not-the-frozen-m0-id",
                "relative_path": "fake.txt",
                "script": "iast",
                "condition": "surface_word",
                "representation_path": str(tmp_path / "fake.txt"),
            }
        )
    with pytest.raises(ValueError, match="Unexpected or mixed M0 freeze IDs"):
        load_documents(manifest, repo_root=tmp_path, max_documents=None)


def test_diagnostic_identity_is_sha_sensitive(tmp_path: Path) -> None:
    source, _ = _diagnostic_fixture(tmp_path)
    before = source.identity_payload()
    source.corpus.write_text("devaḥ ca\nrāmaḥ ca\neva\n", encoding="utf-8")
    changed = DiagnosticCorpusSource(
        corpus=source.corpus,
        corpus_sha256=_file_sha256(source.corpus),
        challenge=source.challenge,
        challenge_sha256=source.challenge_sha256,
        target_id=source.target_id,
        level=source.level,
    )
    assert before["corpus_sha256"] != changed.identity_payload()["corpus_sha256"]
    assert source.identity_sha256() != changed.identity_sha256()
    assert "freeze_id" not in changed.identity_payload()


def test_verbatim_challenge_leakage_is_rejected(tmp_path: Path) -> None:
    source, rows = _diagnostic_fixture(tmp_path)
    _validate_held_out(source.corpus, rows)
    source.corpus.write_text("devaḥ api\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Challenge sentence occurs verbatim"):
        _validate_held_out(source.corpus, rows)


def test_extra_surface_challenge_uses_explicit_gold_jsonl(tmp_path: Path) -> None:
    text = tmp_path / "extra.txt"
    text.write_text("svayaṃbhv ekam\n", encoding="utf-8")
    gold = tmp_path / "extra.jsonl"
    gold.write_text(
        json.dumps(
            {
                "text": "svayaṃbhv ekam",
                "matches": [{"form": "svayaṃbhv", "unsandhied": "svayaṃbhū"}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    assert _read_extra_challenge(text, None) == [
        {"text": "svayaṃbhv ekam", "matches": []}
    ]
    assert _read_extra_challenge(text, gold)[0]["matches"][0][
        "unsandhied"
    ] == "svayaṃbhū"


def test_diagnostic_exact_training_and_read_only_heldout_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, challenge_rows = _diagnostic_fixture(tmp_path)
    config = TrainingConfig(
        output_root=tmp_path / "artifacts",
        run_id="tiny-probe",
        model=S1M2_MODEL,
        passes=1,
        workers=1,
        analysis_top_k=2,
        piece_max_length=3,
        sandhi_transformation_penalty=1.0,
        piece_boundary_probability=0.4,
    )
    assert config.payload()["sandhi_transformation_penalty"] == 1.0
    assert config.payload()["piece_boundary_probability"] == 0.4
    seen_training_paths: list[Path] = []
    original_iter = latent_training._iter_document_segments

    def track_training_document(document, training_config):
        seen_training_paths.append(document.path)
        yield from original_iter(document, training_config)

    monkeypatch.setattr(latent_training, "_iter_document_segments", track_training_document)
    monkeypatch.setattr(
        latent_training,
        "load_documents",
        lambda *args, **kwargs: pytest.fail("diagnostic used formal manifest loader"),
    )
    result = run_training(
        config,
        repo_root=Path("."),
        stop_after_training=True,
        _diagnostic_source=source,
    )
    assert len(result.history) == 1
    assert seen_training_paths and set(seen_training_paths) == {source.corpus}
    provenance = json.loads((result.run_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["source_kind"] == "diagnostic_s1m2_lexeme_probe"
    assert provenance["corpus_sha256"] == source.corpus_sha256
    assert provenance["challenge_sha256"] == source.challenge_sha256
    assert "freeze_id" not in provenance
    assert "manifest_sha256" not in provenance
    assert provenance["formal_manifest_used"] is False
    assert provenance["diagnostic_input_signature"] == source.identity_sha256()
    with sqlite3.connect(result.run_dir / "learner.sqlite") as connection:
        before = connection.execute(
            "SELECT form_key, expected_count FROM piece_lexicon ORDER BY form_key"
        ).fetchall()
    first = evaluate_challenge(
        config=config,
        run_dir=result.run_dir,
        source=source,
        challenge_rows=challenge_rows,
    )
    output = (result.run_dir / "challenge_analyses.jsonl").read_bytes()
    second = evaluate_challenge(
        config=config,
        run_dir=result.run_dir,
        source=source,
        challenge_rows=challenge_rows,
    )
    assert first == second
    assert output == (result.run_dir / "challenge_analyses.jsonl").read_bytes()
    with sqlite3.connect(result.run_dir / "learner.sqlite") as connection:
        after = connection.execute(
            "SELECT form_key, expected_count FROM piece_lexicon ORDER BY form_key"
        ).fetchall()
    assert before == after
    assert first["challenge_sentences"] == 1
    assert first["target_occurrences"] == 1
    assert first["exact_lexical_recovery_posterior_mean"] is None
    record = json.loads(output.decode("utf-8").splitlines()[0])
    assert record["sentence_text"] == "devaḥ api"
    assert record["dcs_unsandhied_gold_form"] == "devaḥ"
    assert record["target_gold_lexical_form_posterior"] is None
    assert record["top_analysis_lexical_forms"]
    assert record["target_top_analysis"] is not None
    assert record["target_top_analysis"]["pieces"]
    assert 0.0 <= record["top_analysis_posterior"] <= 1.0


def test_probe_cli_defaults_and_help() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--corpus", "corpus.txt",
            "--challenge", "challenge.jsonl",
            "--target-id", "noun_high_deva",
            "--level", "E000",
            "--output-root", "artifacts/diagnostics",
        ]
    )
    assert args.passes == 3
    assert args.sandhi_transformation_penalty == 1.0
    assert args.piece_boundary_probability == 0.4
    assert "--extra-challenge" in parser.format_help()

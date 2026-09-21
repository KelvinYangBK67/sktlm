from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import sktlm.latent.training as training
from sktlm.experiments.training.s1m2_semantic_diagnostics import (
    ANALYSES_NAME,
    PROVENANCE_NAME,
    SUMMARY_NAME,
    V3_ANALYSES_NAME,
    V3_PROVENANCE_NAME,
    V3_SUMMARY_NAME,
    analyze_semantic_records,
    build_training_gold_inventory,
    read_piece_lexicon_values,
    read_role_pooling_diagnostics,
    run_semantic_diagnostics,
)
from sktlm.latent.phonology import parse_iast_form
from sktlm.latent.training import (
    S1M2_MODEL,
    S1M2_REUSABLE_PIECES_V3,
    TrainingConfig,
    _config_signature,
    _file_sha256,
)


def _record(
    *,
    sentence_index: int,
    gold: str,
    predicted: str | None,
    pieces: list[str],
    recovered: bool | None,
    reason: str | None = None,
    surface_form: str | None = None,
) -> dict:
    target = None
    if recovered is not None:
        target = {
            "lexical_form": predicted,
            "pieces": pieces,
            "piece_count": len(pieces) if pieces else None,
            "whole_form": len(pieces) == 1,
        }
    return {
        "localization_schema_version": 2,
        "target_id": "noun_high_deva",
        "sentence_index": sentence_index,
        "match_index": 0,
        "dcs_id": 1,
        "dcs_occ_id": f"occ-{sentence_index}",
        "dcs_target_form": surface_form or gold,
        "dcs_unsandhied_gold_form": gold,
        "gold_unavailable_reason": None,
        "target_top_analysis": target,
        "target_localization_reason": reason,
        "top1_lexical_recovered": recovered,
    }


def test_wrong_host_coalition_and_exact_wordform_strata() -> None:
    records = [
        _record(
            sentence_index=0, gold="devam", predicted="devam",
            pieces=["deva", "m"], recovered=True,
        ),
        _record(
            sentence_index=1, gold="devasya", predicted="devas",
            pieces=["deva", "s"], recovered=False,
        ),
        _record(
            sentence_index=2, gold="devāḥ", predicted="devas",
            pieces=["deva", "s"], recovered=False, surface_form="devo",
        ),
        _record(
            sentence_index=3, gold="devena", predicted="devau",
            pieces=["deva", "u"], recovered=False,
        ),
        _record(
            sentence_index=4, gold="devam", predicted=None, pieces=[],
            recovered=None, reason="dcs_component_factor_alignment_ambiguous",
        ),
    ]
    piece_values = {
        "deva": {
            "raw_expected_count": 10.0,
            "max_host_expected_usage": 4.0,
            "reusable_count": 6.0,
        },
        "m": {"raw_expected_count": 2.0, "max_host_expected_usage": 1.0, "reusable_count": 1.0},
        "s": {"raw_expected_count": 3.0, "max_host_expected_usage": 2.0, "reusable_count": 1.0},
        "u": None,
    }
    diagnostics, summary = analyze_semantic_records(
        records,
        # Surface spelling "devo" cannot make gold "devāḥ" seen. The other
        # inflected forms remain unseen despite sharing the deva lemma/stem.
        training_gold_wordforms=frozenset({"devam", "devo"}),
        piece_values=piece_values,
    )

    audit = summary["wrong_host_coalition_audit"]
    assert audit["evaluable_occurrences"] == 4
    assert audit["correct_host_occurrences"] == 1
    assert audit["wrong_host_occurrences"] == 3
    deva = next(row for row in audit["top_coalition_candidates"] if row["piece"] == "deva")
    assert deva["wrong_target_occurrences"] == 3
    assert deva["distinct_wrong_predicted_host_forms"] == 2
    assert deva["wrong_predicted_host_forms"] == ["devas", "devau"]
    assert deva["correct_target_occurrences"] == 1
    assert (deva["raw_expected_count"], deva["max_host_expected_usage"], deva["reusable_count"]) == (10, 4, 6)
    repeated_host_piece = next(
        row for row in audit["all_wrong_prediction_pieces"] if row["piece"] == "s"
    )
    assert repeated_host_piece["wrong_target_occurrences"] == 2
    assert repeated_host_piece["distinct_wrong_predicted_host_forms"] == 1

    strata = summary["unseen_exact_wordform_generalization"]
    seen = strata["seen_exact_gold_wordform_in_training"]
    unseen = strata["unseen_exact_gold_wordform_in_training"]
    assert (seen["target_occurrences"], seen["evaluable_occurrences"]) == (2, 1)
    assert (seen["top1_lexical_recovery_numerator"], seen["top1_lexical_recovery_denominator"]) == (1, 1)
    assert (unseen["target_occurrences"], unseen["evaluable_occurrences"]) == (3, 3)
    assert (unseen["top1_lexical_recovery_numerator"], unseen["top1_lexical_recovery_denominator"]) == (0, 3)
    assert seen["unscorable_reasons"] == {
        "dcs_component_factor_alignment_ambiguous": 1
    }
    assert diagnostics[2]["training_gold_wordform_stratum"] == (
        "unseen_exact_gold_wordform_in_training"
    )
    assert diagnostics[4]["top1_classification"] == "unscorable"
    assert diagnostics[0]["metric_semantics"]["wrong_host_audit"] == (
        "held_out_top1_descriptive_not_exact_posterior"
    )


def test_training_inventory_uses_dcs_unsandhied_and_accepts_gold_equivalent_duplicates(
    tmp_path: Path,
) -> None:
    dcs = tmp_path / "dcs"
    dcs.mkdir()
    text = "devo 'pi"
    block = (
        "# text = devo 'pi\n# sent_id = {sent}\n"
        "1\tdevo\tdeva\tNOUN\t_\t_\t_\t_\t_\tOccId={occ}a|Unsandhied=devaḥ\n"
        "2\t'pi\tapi\tPART\t_\t_\t_\t_\t_\tOccId={occ}b|Unsandhied=api\n\n"
    )
    (dcs / "sample.conllu").write_text(
        block.format(sent="one", occ="1") + block.format(sent="two", occ="2"),
        encoding="utf-8",
    )
    corpus = tmp_path / "corpus.txt"
    corpus.write_text(text + "\n", encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(
        json.dumps({"text": text, "source_file": "sample.conllu"}) + "\n",
        encoding="utf-8",
    )

    payload = build_training_gold_inventory(
        corpus=corpus, selection=selection, dcs_root=dcs
    )

    assert payload["gold_wordforms"] == ["api", "devaḥ"]
    assert "devo" not in payload["gold_wordforms"]
    assert payload["mapping_status_counts"] == {
        "gold_equivalent_multiple_dcs_sentences": 1
    }
    identities = payload["records"][0]["candidate_sentence_identities"]
    assert [item["sent_id"] for item in identities] == ["one", "two"]


def test_piece_values_are_read_only_and_query_only(tmp_path: Path) -> None:
    database = tmp_path / "learner.sqlite"
    piece = parse_iast_form("deva")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE piece_lexicon(form_key TEXT PRIMARY KEY, "
            "raw_expected_count REAL NOT NULL, max_host_expected_usage REAL NOT NULL, "
            "reusable_count REAL NOT NULL)"
        )
        connection.execute("INSERT INTO piece_lexicon VALUES (?, 9, 5, 4)", (piece.key,))
    before = _file_sha256(database)

    values, query_only = read_piece_lexicon_values(database, ["deva", "ti"])

    assert query_only is True
    assert values["deva"] == {
        "raw_expected_count": 9.0,
        "max_host_expected_usage": 5.0,
        "reusable_count": 4.0,
    }
    assert values["ti"] is None
    assert _file_sha256(database) == before
    assert not Path(str(database) + "-wal").exists()
    assert not Path(str(database) + "-shm").exists()


def test_v3_moments_role_pooling_and_semantic_adaptation_are_read_only(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v3.sqlite"
    deva = parse_iast_form("deva")
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
        connection.execute(
            "INSERT INTO metadata VALUES ('piece_objective_model', ?)",
            (S1M2_REUSABLE_PIECES_V3,),
        )
        connection.execute(
            "CREATE TABLE piece_lexicon(form_key TEXT PRIMARY KEY, "
            "raw_expected_count REAL NOT NULL, sum_host_support_squared REAL NOT NULL, "
            "max_host_expected_usage REAL NOT NULL, reusable_count REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO piece_lexicon VALUES (?, 10, 50, 5, 5)", (deva.key,)
        )
        connection.execute(
            "CREATE TABLE piece_role_diagnostics("
            "form_key TEXT, role TEXT, raw_expected_count REAL, "
            "sum_host_support_squared REAL, reusable_count REAL, "
            "PRIMARY KEY(form_key, role))"
        )
        connection.executemany(
            "INSERT INTO piece_role_diagnostics VALUES (?, ?, ?, ?, ?)",
            [
                (deva.key, "WHOLE", 4.0, 16.0, 0.0),
                (deva.key, "LEFT", 6.0, 26.0, 5 / 3),
            ],
        )
    before = _file_sha256(database)
    values, query_only = read_piece_lexicon_values(
        database, ["deva"], objective_model=S1M2_REUSABLE_PIECES_V3
    )
    roles, role_query_only = read_role_pooling_diagnostics(
        database, objective_model=S1M2_REUSABLE_PIECES_V3
    )
    assert query_only is True and role_query_only is True
    assert values["deva"] == {
        "raw_expected_count": 10.0,
        "sum_host_support_squared": 50.0,
        "max_host_expected_usage": 5.0,
        "reusable_count": 5.0,
    }
    assert roles[0]["role_raw_count_total"] == pytest.approx(10)
    assert roles[0]["role_separated_reusable_count"] == pytest.approx(5 / 3)
    assert roles[0]["role_pooling_gain"] == pytest.approx(10 / 3)

    records = [
        _record(
            sentence_index=0,
            gold="devam",
            predicted="devas",
            pieces=["deva"],
            recovered=False,
        ),
        _record(
            sentence_index=1,
            gold="devina",
            predicted="devau",
            pieces=["deva"],
            recovered=False,
            surface_form="devena",
        ),
    ]
    diagnostics, summary = analyze_semantic_records(
        records,
        training_gold_wordforms=frozenset({"devam"}),
        piece_values=values,
        objective_model=S1M2_REUSABLE_PIECES_V3,
        role_pooling_rows=roles,
    )
    coalition = summary["wrong_host_coalition_audit"]["top_coalition_candidates"][0]
    assert coalition["sum_host_support_squared"] == 50
    assert coalition["distinct_wrong_predicted_host_forms"] == 2
    assert "do not establish" in summary["metric_semantics"]["wrong_host_audit"]
    assert summary["role_source_pooling_diagnostic"]["reported_pieces"] == 1
    strata = summary["unseen_exact_wordform_generalization"]
    assert strata["seen_exact_gold_wordform_in_training"]["target_occurrences"] == 1
    assert strata["unseen_exact_gold_wordform_in_training"]["target_occurrences"] == 1
    assert diagnostics[1]["training_gold_wordform_stratum"].startswith("unseen")
    assert _file_sha256(database) == before

def test_end_to_end_reevaluation_does_not_invoke_trainer_or_overwrite_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("rāmaḥ\n", encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(
        json.dumps({"text": "rāmaḥ", "source_file": "unused.conllu"}) + "\n",
        encoding="utf-8",
    )
    challenge = tmp_path / "challenge.jsonl"
    challenge.write_text(json.dumps({"text": "devam"}) + "\n", encoding="utf-8")
    config = TrainingConfig(
        model=S1M2_MODEL, passes=1, output_root=tmp_path, run_id="synthetic"
    )
    (run_dir / "config.json").write_text(
        json.dumps(config.payload(), indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "provenance.json").write_text(
        json.dumps(
            {
                "source_kind": "diagnostic_s1m2_lexeme_probe",
                "config_signature": _config_signature(config),
                "training_git_commit": "synthetic-training-commit",
                "corpus": corpus.as_posix(),
                "corpus_sha256": _file_sha256(corpus),
                "challenge": challenge.as_posix(),
                "challenge_sha256": _file_sha256(challenge),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"completed_passes": 1, "active_pass": None}) + "\n",
        encoding="utf-8",
    )
    records = [
        _record(
            sentence_index=0, gold="devam", predicted="devam",
            pieces=["deva", "m"], recovered=True,
        )
    ]
    (run_dir / "challenge_analyses.jsonl").write_text(
        json.dumps(records[0], ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "challenge_summary.json").write_text("{}\n", encoding="utf-8")
    with sqlite3.connect(run_dir / "learner.sqlite") as connection:
        connection.execute(
            "CREATE TABLE piece_lexicon(form_key TEXT PRIMARY KEY, "
            "raw_expected_count REAL NOT NULL, max_host_expected_usage REAL NOT NULL, "
            "reusable_count REAL NOT NULL)"
        )
        for form, values in (("deva", (4, 2, 2)), ("m", (3, 2, 1))):
            connection.execute(
                "INSERT INTO piece_lexicon VALUES (?, ?, ?, ?)",
                (parse_iast_form(form).key, *values),
            )
    sidecar = tmp_path / "training_gold_wordforms.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_sha256": _file_sha256(corpus),
                "selection_sha256": _file_sha256(selection),
                "dcs_source_files_sha256": {},
                "gold_wordforms": ["devam"],
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    protected = {
        path.name: _file_sha256(path)
        for path in run_dir.iterdir()
        if path.is_file()
    }

    monkeypatch.setattr(
        training,
        "run_training",
        lambda *args, **kwargs: pytest.fail("trainer must not be invoked"),
    )
    summary = run_semantic_diagnostics(
        run_dir=run_dir,
        training_selection=selection,
        training_gold_sidecar=sidecar,
        dcs_root=tmp_path,
        repo_root=Path("."),
    )

    assert summary["wrong_host_coalition_audit"]["correct_host_occurrences"] == 1
    assert (run_dir / ANALYSES_NAME).is_file()
    assert (run_dir / SUMMARY_NAME).is_file()
    provenance = json.loads((run_dir / PROVENANCE_NAME).read_text(encoding="utf-8"))
    assert provenance["trainer_invoked"] is False
    assert provenance["inference_invoked"] is False
    assert provenance["sqlite_open_mode"] == "mode=ro"
    assert provenance["sqlite_query_only_enforced"] is True
    assert provenance["protected_run_artifacts_unchanged"] is True
    assert {
        path.name: _file_sha256(path)
        for path in run_dir.iterdir()
        if path.name in protected
    } == protected


def test_v3_end_to_end_uses_v4_artifacts_and_preserves_v2_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "v3-run"
    run_dir.mkdir()
    corpus = tmp_path / "corpus-v3.txt"
    corpus.write_text("rāmaḥ\n", encoding="utf-8")
    selection = tmp_path / "selection-v3.jsonl"
    selection.write_text(
        json.dumps({"text": "rāmaḥ", "source_file": "unused.conllu"}) + "\n",
        encoding="utf-8",
    )
    challenge = tmp_path / "challenge-v3.jsonl"
    challenge.write_text(json.dumps({"text": "devam"}) + "\n", encoding="utf-8")
    config = TrainingConfig(
        model=S1M2_REUSABLE_PIECES_V3,
        piece_role_diagnostics=True,
        passes=1,
        output_root=tmp_path,
        run_id="synthetic-v3",
    )
    (run_dir / "config.json").write_text(
        json.dumps(config.payload(), indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "provenance.json").write_text(
        json.dumps(
            {
                "source_kind": "diagnostic_s1m2_lexeme_probe",
                "config_signature": _config_signature(config),
                "training_git_commit": "synthetic-v3-training-commit",
                "corpus": corpus.as_posix(),
                "corpus_sha256": _file_sha256(corpus),
                "challenge": challenge.as_posix(),
                "challenge_sha256": _file_sha256(challenge),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"completed_passes": 1, "active_pass": None}) + "\n",
        encoding="utf-8",
    )
    record = _record(
        sentence_index=0,
        gold="devam",
        predicted="devas",
        pieces=["deva"],
        recovered=False,
    )
    (run_dir / "challenge_analyses.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "challenge_summary.json").write_text("{}\n", encoding="utf-8")
    deva = parse_iast_form("deva")
    with sqlite3.connect(run_dir / "learner.sqlite") as connection:
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
        connection.execute(
            "INSERT INTO metadata VALUES ('piece_objective_model', ?)",
            (S1M2_REUSABLE_PIECES_V3,),
        )
        connection.execute(
            "CREATE TABLE piece_lexicon(form_key TEXT PRIMARY KEY, "
            "raw_expected_count REAL, sum_host_support_squared REAL, "
            "max_host_expected_usage REAL, reusable_count REAL)"
        )
        connection.execute(
            "INSERT INTO piece_lexicon VALUES (?, 10, 50, 5, 5)", (deva.key,)
        )
        connection.execute(
            "CREATE TABLE piece_role_diagnostics("
            "form_key TEXT, role TEXT, raw_expected_count REAL, "
            "sum_host_support_squared REAL, reusable_count REAL, "
            "PRIMARY KEY(form_key, role))"
        )
        connection.execute(
            "INSERT INTO piece_role_diagnostics VALUES (?, 'LEFT', 10, 100, 0)",
            (deva.key,),
        )
    sidecar = tmp_path / "training_gold_wordforms-v3.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_sha256": _file_sha256(corpus),
                "selection_sha256": _file_sha256(selection),
                "dcs_source_files_sha256": {},
                "gold_wordforms": ["devam"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    sentinels = {}
    for name in (ANALYSES_NAME, SUMMARY_NAME, PROVENANCE_NAME):
        path = run_dir / name
        path.write_text(f"historical {name}\n", encoding="utf-8")
        sentinels[name] = _file_sha256(path)

    monkeypatch.setattr(
        training,
        "run_training",
        lambda *args, **kwargs: pytest.fail("trainer must not be invoked"),
    )
    summary = run_semantic_diagnostics(
        run_dir=run_dir,
        training_selection=selection,
        training_gold_sidecar=sidecar,
        dcs_root=tmp_path,
        repo_root=Path("."),
    )

    assert summary["objective_model"] == S1M2_REUSABLE_PIECES_V3
    assert (run_dir / V3_ANALYSES_NAME).is_file()
    assert (run_dir / V3_SUMMARY_NAME).is_file()
    provenance = json.loads((run_dir / V3_PROVENANCE_NAME).read_text("utf-8"))
    assert provenance["trainer_invoked"] is False
    assert provenance["inference_invoked"] is False
    assert provenance["sqlite_query_only_enforced"] is True
    assert {
        name: _file_sha256(run_dir / name) for name in sentinels
    } == sentinels
    assert not Path(str(run_dir / "learner.sqlite") + "-wal").exists()
    assert not Path(str(run_dir / "learner.sqlite") + "-shm").exists()

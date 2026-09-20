from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import sktlm.experiments.training.s1m2_lexeme_probe as probe
from sktlm.experiments.training.s1m2_lexeme_alignment import (
    locate_dcs_occurrences,
    top_factor_groups,
)
from sktlm.latent.candidates import LexicalBoundary
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.phonology import parse_iast_form
from sktlm.latent.training import DiagnosticCorpusSource, S1M2_MODEL, TrainingConfig
from sktlm.pieces.composed import ComposedAnalysisPosterior


def _write_dcs(
    tmp_path: Path,
    *,
    text: str,
    lines: list[str],
) -> tuple[Path, dict]:
    root = tmp_path / "dcs"
    root.mkdir()
    path = root / "sample.conllu"
    path.write_text(
        "# text = " + text + "\n# sent_id = tiny\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return root, {
        "text": text,
        "sent_id": "tiny",
        "source_file": "sample.conllu",
        "target_id": "noun_high_deva",
    }


def _token(identifier: int, form: str, occ_id: str) -> str:
    return (
        f"{identifier}\t{form}\tdeva\tNOUN\t_\t_\t_\t_\t_\t"
        f"LemmaId=86559|OccId={occ_id}"
    )


def _analysis(
    forms: tuple[str, ...],
    boundaries: tuple[LexicalBoundary, ...],
) -> ComposedAnalysisPosterior:
    words = tuple(parse_iast_form(form) for form in forms)
    return ComposedAnalysisPosterior(
        words=words,
        piece_segmentations=tuple((word,) for word in words),
        probability=0.75,
        log_score=0.0,
        rule_ids=(),
        boundaries=boundaries,
    )


def _evaluate_synthetic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    row: dict,
    analysis: ComposedAnalysisPosterior,
    dcs_root: Path,
) -> tuple[dict, list[dict]]:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with sqlite3.connect(run_dir / "learner.sqlite") as connection:
        connection.execute(
            "CREATE TABLE piece_lexicon (form_key TEXT PRIMARY KEY, expected_count REAL)"
        )
    corpus = tmp_path / "corpus.txt"
    challenge = tmp_path / "challenge.jsonl"
    corpus.write_text("rāmaḥ\n", encoding="utf-8")
    challenge.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    source = DiagnosticCorpusSource(
        corpus=corpus,
        corpus_sha256=probe._file_sha256(corpus),
        challenge=challenge,
        challenge_sha256=probe._file_sha256(challenge),
        target_id="noun_high_deva",
        level="E000",
    )
    monkeypatch.setattr(probe, "build_lazy_candidate_graph", lambda segment, *a, **k: segment)
    monkeypatch.setattr(
        probe,
        "infer_composed_segment",
        lambda *a, **k: SimpleNamespace(
            top_analyses=(analysis,), expected_transformed_sandhi_events=0.0
        ),
    )
    summary = probe.evaluate_challenge(
        config=TrainingConfig(model=S1M2_MODEL),
        run_dir=run_dir,
        source=source,
        challenge_rows=[row],
        dcs_root=dcs_root,
    )
    records = [
        json.loads(line)
        for line in (run_dir / "challenge_analyses.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    return summary, records


def test_legacy_one_to_one_location_and_pieces_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path,
        text="devaḥ api",
        lines=[_token(1, "devaḥ", "o1"), _token(2, "api", "o2")],
    )
    row["matches"] = [
        {"id": 1, "occ_id": "o1", "form": "devaḥ", "unsandhied": "devaḥ"}
    ]
    segment = tuple(iter_observed_segments(row["text"]))[0]
    left, right = segment.tokens
    boundary = LexicalBoundary("visible:1", "space", left.source_end, right.source_start)
    analysis = _analysis(("devaḥ", "api"), (boundary,))
    groups, error = top_factor_groups(segment, analysis)
    assert error is None and groups == ((0,), (1,))
    summary, records = _evaluate_synthetic(
        tmp_path, monkeypatch, row=row, analysis=analysis, dcs_root=root
    )
    assert summary["evaluable_target_occurrences"] == 1
    assert records[0]["target_top_analysis"] == {
        "lexical_form": "devaḥ",
        "pieces": ["devaḥ"],
        "piece_count": 1,
        "whole_form": True,
    }


def test_repeated_same_target_uses_dcs_id_and_occ_id_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path,
        text="devaḥ devaḥ",
        lines=[_token(1, "devaḥ", "o1"), _token(2, "devaḥ", "o2")],
    )
    row["matches"] = [
        {"id": 1, "occ_id": "o1", "form": "devaḥ", "unsandhied": "devaḥ"},
        {"id": 2, "occ_id": "o2", "form": "devaḥ", "unsandhied": "devaḥ"},
    ]
    segment = tuple(iter_observed_segments(row["text"]))[0]
    left, right = segment.tokens
    analysis = _analysis(
        ("devaḥ", "devaḥ"),
        (LexicalBoundary("visible:1", "space", left.source_end, right.source_start),),
    )
    summary, records = _evaluate_synthetic(
        tmp_path, monkeypatch, row=row, analysis=analysis, dcs_root=root
    )
    assert summary["evaluable_target_occurrences"] == 2
    assert summary["top1_lexical_recovery_rate"] == 1.0
    assert [r["gold_surface_location"]["token_index"] for r in records] == [0, 1]


def test_transformed_multiword_range_aligns_by_structure_not_gold_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path,
        text="devāñjigāti",
        lines=[
            "1-2\tdevāñjigāti\t_\t_\t_\t_\t_\t_\t_\t_",
            _token(1, "devān", "o1"),
            _token(2, "jigāti", "o2"),
        ],
    )
    row["matches"] = [
        {"id": 1, "occ_id": "o1", "form": "devān", "unsandhied": "devān"}
    ]
    assert "devān" not in row["text"]
    analysis = _analysis(
        ("devān", "jigāti"),
        (LexicalBoundary("internal:4:5", "unmarked", 4, 5),),
    )
    summary, records = _evaluate_synthetic(
        tmp_path, monkeypatch, row=row, analysis=analysis, dcs_root=root
    )
    assert summary["evaluable_target_occurrences"] == 1
    assert records[0]["target_top_analysis"]["lexical_form"] == "devān"
    assert records[0]["gold_surface_location"]["component_index"] == 0
    assert records[0]["gold_surface_location"]["component_count"] == 2


def test_unsplit_transformed_range_is_a_scorable_nonrecovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path,
        text="devāñjigāti",
        lines=[
            "1-2\tdevāñjigāti\t_\t_\t_\t_\t_\t_\t_\t_",
            _token(1, "devān", "o1"),
            _token(2, "jigāti", "o2"),
        ],
    )
    row["matches"] = [
        {"id": 1, "occ_id": "o1", "form": "devān", "unsandhied": "devān"}
    ]
    summary, records = _evaluate_synthetic(
        tmp_path,
        monkeypatch,
        row=row,
        analysis=_analysis(("devāñjigāti",), ()),
        dcs_root=root,
    )
    assert summary["evaluable_target_occurrences"] == 1
    assert summary["top1_lexical_recovery_rate"] == 0.0
    assert records[0]["target_top_analysis"]["alignment_kind"] == (
        "merged_gold_components"
    )


def test_analytical_underscore_form_is_located_by_dcs_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path,
        text="yānti deva vratāḥ devān",
        lines=[
            _token(1, "yānti", "o1"),
            _token(2, "_", "o2"),
            _token(3, "_", "o3"),
            _token(4, "devān", "o4"),
        ],
    )
    row["matches"] = [
        {"id": 2, "occ_id": "o2", "form": "_", "unsandhied": "deva"}
    ]
    segment = tuple(iter_observed_segments(row["text"]))[0]
    boundaries = tuple(
        LexicalBoundary(
            f"visible:{index}", "space",
            segment.tokens[index - 1].source_end,
            segment.tokens[index].source_start,
        )
        for index in range(1, len(segment.tokens))
    )
    analysis = _analysis(("yānti", "deva", "vratāḥ", "devān"), boundaries)
    summary, records = _evaluate_synthetic(
        tmp_path, monkeypatch, row=row, analysis=analysis, dcs_root=root
    )
    assert summary["evaluable_target_occurrences"] == 1
    assert records[0]["gold_surface_location"]["token_index"] == 1
    assert records[0]["target_top_analysis"]["lexical_form"] == "deva"


def test_mismatched_multiword_component_count_is_explicitly_unscorable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path,
        text="devāñjigāti",
        lines=[
            "1-3\tdevāñjigāti\t_\t_\t_\t_\t_\t_\t_\t_",
            _token(1, "devān", "o1"),
            _token(2, "ji", "o2"),
            _token(3, "gāti", "o3"),
        ],
    )
    row["matches"] = [
        {"id": 1, "occ_id": "o1", "form": "devān", "unsandhied": "devān"}
    ]
    analysis = _analysis(
        ("devān", "jigāti"),
        (LexicalBoundary("internal:4:5", "unmarked", 4, 5),),
    )
    summary, records = _evaluate_synthetic(
        tmp_path, monkeypatch, row=row, analysis=analysis, dcs_root=root
    )
    assert summary["unscorable_reasons"] == {
        "dcs_component_factor_alignment_ambiguous": 1
    }
    assert records[0]["target_top_analysis"] is None


def test_split_gold_surface_token_is_scored_as_nonrecovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path, text="devaḥ", lines=[_token(1, "devaḥ", "o1")]
    )
    row["matches"] = [
        {"id": 1, "occ_id": "o1", "form": "devaḥ", "unsandhied": "devaḥ"}
    ]
    analysis = _analysis(
        ("de", "vaḥ"),
        (LexicalBoundary("internal:2:2", "unmarked", 2, 2),),
    )
    summary, records = _evaluate_synthetic(
        tmp_path, monkeypatch, row=row, analysis=analysis, dcs_root=root
    )
    assert summary["evaluable_target_occurrences"] == 1
    assert summary["top1_lexical_recovery_rate"] == 0.0
    assert summary["target_top1_piece_metric_denominator"] == 0
    assert records[0]["target_top_analysis"]["alignment_kind"] == "fragmented_gold_token"


def test_dcs_occ_id_mismatch_is_unscorable_not_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, row = _write_dcs(
        tmp_path, text="devaḥ", lines=[_token(1, "devaḥ", "o1")]
    )
    row["matches"] = [
        {"id": 1, "occ_id": "wrong", "form": "devaḥ", "unsandhied": "devaḥ"}
    ]
    summary, records = _evaluate_synthetic(
        tmp_path,
        monkeypatch,
        row=row,
        analysis=_analysis(("devaḥ",), ()),
        dcs_root=root,
    )
    assert summary["evaluable_target_occurrences"] == 0
    assert summary["unscorable_reasons"] == {"dcs_occ_id_mismatch": 1}
    assert records[0]["target_top_analysis"] is None

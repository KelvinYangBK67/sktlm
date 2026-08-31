from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from sktlm.latent.candidates import build_candidate_graph
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import NeutralFormScorer, infer_segment
from sktlm.latent.phonology import Phoneme, PhonologicalForm
from sktlm.latent.store import LexiconStore
from sktlm.latent.training import EXPECTED_FREEZE_ID, TrainingConfig, run_training
from sktlm.latent.vocabulary import (
    BASE_FORMS,
    BASE_UNIT_COUNT,
    FrozenVocabulary,
    ProjectedFormScorer,
    VocabularyEntry,
    allowed_key_sha256,
)


def _form(*symbols: Phoneme) -> PhonologicalForm:
    return PhonologicalForm(symbols)


def _base_only_vocabulary() -> FrozenVocabulary:
    entries = tuple(
        VocabularyEntry(rank, "base", form, 0.0)
        for rank, form in enumerate(BASE_FORMS, 1)
    )
    return FrozenVocabulary(
        total_budget=BASE_UNIT_COUNT,
        entries=entries,
        allowed_sha256=allowed_key_sha256(entry.form.key for entry in entries),
    )


def test_selection_counts_latent_identities_and_projects_pruned_mass(
    tmp_path: Path,
) -> None:
    base_a = _form(Phoneme.A)
    base_u = _form(Phoneme.U)
    tied_first = _form(Phoneme.A, Phoneme.I)
    tied_second = _form(Phoneme.A, Phoneme.U)
    repeated_base = _form(Phoneme.A, Phoneme.A)
    store = LexiconStore(tmp_path / "learner.sqlite")
    try:
        store.begin_count_pass(resume=False, checkpoint={})
        store.add_counts(
            (
                (base_a, 1.0),
                (tied_first, 4.0),
                (tied_second, 4.0),
                (repeated_base, 2.0),
            )
        )

        vocabulary = store.select_and_freeze_vocabulary(BASE_UNIT_COUNT + 1)
        counts = {
            str(row[0]): float(row[1])
            for row in store.connection.execute(
                "SELECT form_key, expected_count FROM counts_next"
            )
        }

        assert vocabulary.actual_size == BASE_UNIT_COUNT + 1
        assert vocabulary.entries[-1].form == tied_first
        assert vocabulary.entries[-1].rank == BASE_UNIT_COUNT + 1
        assert tied_second.key not in vocabulary.allowed_keys
        assert repeated_base.key not in vocabulary.allowed_keys
        assert counts[tied_first.key] == 4.0
        assert counts[base_a.key] == 9.0
        assert counts[base_u.key] == 4.0
        assert sum(counts.values()) == 17.0
        assert set(counts) == vocabulary.allowed_keys

        store.begin_inspection()
        store.add_usage(
            surfaces=(
                (tied_first.key, "surface-one", 0.6),
                (tied_first.key, "surface-two", 0.4),
            )
        )
        assert store.load_frozen_vocabulary() == vocabulary
        assert store.load_frozen_vocabulary().actual_size == BASE_UNIT_COUNT + 1
    finally:
        store.close()


def test_oov_score_and_identity_project_to_base_units() -> None:
    vocabulary = _base_only_vocabulary()
    oov = _form(Phoneme.A, Phoneme.I, Phoneme.A)

    class BaseScorer:
        def __init__(self) -> None:
            self.calls: list[PhonologicalForm] = []

        def score(self, form: PhonologicalForm) -> float:
            assert len(form.symbols) == 1
            self.calls.append(form)
            return {Phoneme.A: -1.0, Phoneme.I: -2.0}[form.symbols[0]]

    base_scorer = BaseScorer()
    scorer = ProjectedFormScorer(base_scorer, vocabulary)

    assert vocabulary.project(oov) == (
        _form(Phoneme.A),
        _form(Phoneme.I),
        _form(Phoneme.A),
    )
    assert scorer.score(oov) == -4.0
    assert base_scorer.calls == [_form(Phoneme.A), _form(Phoneme.I)]


def test_none_preserves_unrestricted_inference() -> None:
    segment = next(iter_observed_segments("api ca"))
    graph = build_candidate_graph(
        segment,
        StructuredSandhiGrammar.from_default_inventory(),
    )
    implicit = infer_segment(
        graph,
        NeutralFormScorer(),
        whitespace_merge_penalty=8.0,
        top_k=4,
    )
    explicit = infer_segment(
        graph,
        NeutralFormScorer(),
        whitespace_merge_penalty=8.0,
        top_k=4,
        vocabulary=None,
    )

    assert implicit == explicit
    assert "vocab_budget" not in TrainingConfig().payload()


def test_constrained_run_outputs_and_resume_reuse_frozen_vocabulary(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "surface.txt"
    corpus.write_text("api ca\n", encoding="utf-8")
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
                "representation_path": str(corpus),
            }
        )
    common = dict(
        manifest=manifest,
        output_root=tmp_path / "artifacts",
        run_id="budget-resume",
        passes=2,
        vocab_budget=BASE_UNIT_COUNT,
        analysis_top_k=4,
    )
    first = run_training(TrainingConfig(**common), repo_root=Path("."))
    preserved = {
        name: (first.run_dir / name).read_bytes()
        for name in (
            "vocabulary_budget.json",
            "vocabulary.tsv",
            "latent_lexicon.tsv",
            "analyses.jsonl",
            "summary.json",
        )
    }
    resumed = run_training(
        TrainingConfig(**common, resume=True),
        repo_root=Path("."),
    )

    assert resumed.run_dir == first.run_dir
    assert all(
        (resumed.run_dir / name).read_bytes() == content
        for name, content in preserved.items()
    )
    budget = json.loads(
        (resumed.run_dir / "vocabulary_budget.json").read_text(encoding="utf-8")
    )
    assert budget["actual_vocabulary_size"] == BASE_UNIT_COUNT
    assert budget["surface_realizations_consume_slots"] is False
    checkpoint = json.loads(
        (resumed.run_dir / "checkpoint.json").read_text(encoding="utf-8")
    )
    assert (
        checkpoint["vocabulary_budget"]["allowed_key_sha256"]
        == budget["allowed_key_sha256"]
    )
    with sqlite3.connect(resumed.run_dir / "learner.sqlite") as connection:
        lexicon_keys = {
            str(row[0]) for row in connection.execute("SELECT form_key FROM lexicon")
        }
    assert lexicon_keys == {form.key for form in BASE_FORMS}
    for line in (resumed.run_dir / "analyses.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        row = json.loads(line)
        for analysis in row["top_analyses"]:
            assert all(
                len(unit["phoneme_ids"]) == 1
                for unit in analysis["latent_units"]
            )

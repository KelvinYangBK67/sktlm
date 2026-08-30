from __future__ import annotations

import math

import pytest

from sktlm.experiments.models.ngram import (
    BOS,
    EOS,
    UNK,
    CharNGramLM,
)


def test_fit_builds_vocabulary() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.1,
    ).fit(
        [
            "devaḥ#api",
            "rāmaḥ#api",
        ]
    )

    assert "d" in lm.vocabulary
    assert "#" in lm.vocabulary
    assert EOS in lm.vocabulary
    assert UNK in lm.vocabulary


def test_start_context_has_order_minus_one_bos_symbols() -> None:
    lm = CharNGramLM(
        order=4,
        alpha=0.1,
    ).fit(["abc"])

    assert lm.start_context() == (
        BOS,
        BOS,
        BOS,
    )


def test_seen_sequence_has_finite_score() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.1,
    ).fit(["devaḥ#api"])

    score = lm.score_sequence(
        "devaḥ#api",
    )

    assert math.isfinite(score)


def test_unknown_character_is_scored_via_unk() -> None:
    lm = CharNGramLM(
        order=2,
        alpha=0.1,
    ).fit(["abc"])

    score = lm.score_sequence("☃")

    assert math.isfinite(score)


def test_repeated_training_pattern_scores_better_than_unseen_pattern() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.1,
    ).fit(
        ["devaḥ#api"] * 20
        + ["xyz"]
    )

    seen = lm.score_sequence(
        "devaḥ#api",
    )
    unseen = lm.score_sequence(
        "devaḥ#xyz",
    )

    assert seen > unseen


def test_invalid_order_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="order must be >= 1",
    ):
        CharNGramLM(order=0)


def test_empty_training_corpus_is_rejected() -> None:
    lm = CharNGramLM()

    with pytest.raises(
        ValueError,
        match="empty corpus",
    ):
        lm.fit([])

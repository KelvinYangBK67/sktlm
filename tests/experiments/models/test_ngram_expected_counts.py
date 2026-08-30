from __future__ import annotations

import math

import pytest

from sktlm.experiments.models.ngram import (
    EOS,
    CharNGramLM,
)


def test_fit_can_reserve_candidate_symbols_without_counts() -> None:
    lm = CharNGramLM(
        order=2,
        alpha=0.1,
    ).fit(
        ["abc"],
        extra_symbols={"#", "ḥ"},
    )

    assert "#" in lm.vocabulary
    assert "ḥ" in lm.vocabulary
    assert math.isfinite(
        lm.score_sequence("aḥ#")
    )


def test_replace_counts_accepts_fractional_counts() -> None:
    lm = CharNGramLM(
        order=1,
        alpha=0.1,
    ).fit(["a"])

    lm.replace_counts(
        ngram_counts={
            ("a",): 0.75,
            (EOS,): 1.0,
        },
        context_counts={
            (): 1.75,
        },
        vocabulary={"a"},
    )

    assert lm.ngram_counts[("a",)] == pytest.approx(
        0.75
    )
    assert math.isfinite(
        lm.score_sequence("a")
    )


def test_replace_counts_rejects_negative_counts() -> None:
    lm = CharNGramLM(
        order=1,
        alpha=0.1,
    ).fit(["a"])

    with pytest.raises(
        ValueError,
        match="non-negative",
    ):
        lm.replace_counts(
            ngram_counts={
                ("a",): -1.0,
            },
            context_counts={
                (): 1.0,
            },
            vocabulary={"a"},
        )

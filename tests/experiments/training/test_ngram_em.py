from __future__ import annotations

import math

import pytest

from sktlm.experiments.models.ngram import (
    CharNGramLM,
)
from sktlm.experiments.training.ngram_em import (
    candidate_latent_alphabet,
    expected_counts_for_lattice,
    initialize_surface_ngram,
    train_surface_ngram_expected_counts,
)
from sktlm.sandhi.lattice import (
    build_external_sandhi_lattice,
)


def test_surface_initializer_needs_no_latent_gold() -> None:
    surfaces = (
        "devo'pi",
        "rāmo'pi",
    )

    lm = initialize_surface_ngram(
        surfaces,
        order=3,
        alpha=0.1,
    )

    assert "#" in lm.vocabulary
    assert "ḥ" in lm.vocabulary


def test_candidate_alphabet_contains_latent_boundary_symbol() -> None:
    alphabet = candidate_latent_alphabet(
        ("devo'pi",),
    )

    assert "#" in alphabet


def test_expected_counts_include_fractional_latent_boundary_mass() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.01,
    ).fit(
        ["devaḥ#api"] * 100
        + ["devo'pi"],
    )

    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    expected = expected_counts_for_lattice(
        lattice,
        lm,
    )

    boundary_mass = sum(
        value
        for ngram, value in expected.ngram_counts.items()
        if ngram[-1] == "#"
    )

    assert boundary_mass > 0.0
    assert math.isfinite(
        expected.log_partition
    )


def test_expected_ngram_and_context_totals_match() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.1,
    ).fit(
        ["devaḥ#api", "devo'pi"],
    )

    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    expected = expected_counts_for_lattice(
        lattice,
        lm,
    )

    assert sum(
        expected.ngram_counts.values()
    ) == pytest.approx(
        sum(
            expected.context_counts.values()
        )
    )


def test_surface_only_training_runs_multiple_iterations() -> None:
    surfaces = (
        "devo'pi",
        "rāmo'pi",
        "aśvo'pi",
    )

    result = train_surface_ngram_expected_counts(
        surfaces,
        order=3,
        alpha=0.1,
        iterations=2,
    )

    assert len(
        result.log_partitions
    ) == 3
    assert all(
        math.isfinite(value)
        for value in result.log_partitions
    )
    assert "#" in result.model.vocabulary


def test_zero_iterations_returns_initialized_model() -> None:
    result = train_surface_ngram_expected_counts(
        ("devo'pi",),
        iterations=0,
    )

    assert len(
        result.log_partitions
    ) == 1


def test_negative_iterations_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="iterations",
    ):
        train_surface_ngram_expected_counts(
            ("devo'pi",),
            iterations=-1,
        )

from __future__ import annotations

import pytest

from sktlm.experiments.models.ngram import CharNGramLM
from sktlm.sandhi.lattice import build_external_sandhi_lattice
from sktlm.sandhi.ngram_posterior import (
    expected_sandhi_edges,
    ngram_edge_posteriors,
    ngram_rule_posteriors,
)


def _latent_preferring_lm() -> CharNGramLM:
    return CharNGramLM(
        order=3,
        alpha=0.01,
    ).fit(
        ["devaḥ#api"] * 100
        + ["rāmaḥ#api"] * 50
        + ["devo'pi"]
    )


def test_edge_posteriors_are_valid_probabilities() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )
    lm = _latent_preferring_lm()

    posteriors = ngram_edge_posteriors(
        lattice,
        lm,
    )

    assert posteriors
    assert all(
        0.0 <= item.probability <= 1.0
        for item in posteriors
    )


def test_deva_visarga_api_edge_gets_high_posterior_when_lm_prefers_it() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )
    lm = _latent_preferring_lm()

    item = next(
        item
        for item in ngram_edge_posteriors(
            lattice,
            lm,
        )
        if item.edge.kind == "sandhi"
        and item.edge.left_underlying == "aḥ"
        and item.edge.right_underlying == "a"
        and item.edge.surface == "o'"
    )

    assert item.probability > 0.5


def test_rule_posteriors_include_deva_visarga_api_rule() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )
    lm = _latent_preferring_lm()

    edge_item = next(
        item
        for item in ngram_edge_posteriors(
            lattice,
            lm,
        )
        if item.edge.kind == "sandhi"
        and item.edge.left_underlying == "aḥ"
        and item.edge.right_underlying == "a"
        and item.edge.surface == "o'"
    )

    rules = {
        item.rule_id: item.probability
        for item in ngram_rule_posteriors(
            lattice,
            lm,
        )
    }

    assert edge_item.edge.rule_id in rules
    assert (
        rules[edge_item.edge.rule_id]
        >= edge_item.probability
    )


def test_expected_sandhi_count_is_positive_for_devo_pi() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )
    lm = _latent_preferring_lm()

    expected = expected_sandhi_edges(
        lattice,
        lm,
    )

    assert expected > 0.0


def test_identity_only_surface_has_zero_expected_sandhi_edges() -> None:
    lattice = build_external_sandhi_lattice(
        "☃",
    )
    lm = CharNGramLM(
        order=2,
        alpha=0.1,
    ).fit(["abc"])

    assert expected_sandhi_edges(
        lattice,
        lm,
    ) == pytest.approx(0.0)


def test_identity_only_path_edges_have_posterior_one() -> None:
    lattice = build_external_sandhi_lattice(
        "☃",
    )
    lm = CharNGramLM(
        order=2,
        alpha=0.1,
    ).fit(["abc"])

    posteriors = ngram_edge_posteriors(
        lattice,
        lm,
    )

    assert len(posteriors) == 1
    assert posteriors[0].edge.kind == "identity"
    assert posteriors[0].probability == pytest.approx(1.0)

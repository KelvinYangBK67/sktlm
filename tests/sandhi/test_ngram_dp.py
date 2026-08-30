from __future__ import annotations

import math

from sktlm.experiments.models.ngram import (
    CharNGramLM,
)
from sktlm.sandhi.lattice import (
    build_external_sandhi_lattice,
)
from sktlm.sandhi.ngram_dp import (
    edge_latent_text,
    lattice_ngram_log_partition,
    lattice_ngram_viterbi,
)


def test_identity_edge_scores_surface_character() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    edge = lattice.identity_edges()[0]

    assert edge_latent_text(edge) == "d"


def test_sandhi_edge_scores_underlying_material() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    edge = next(
        edge
        for edge in lattice.sandhi_edges()
        if edge.surface == "o'"
        and edge.left_underlying == "aḥ"
        and edge.right_underlying == "a"
    )

    assert edge_latent_text(edge) == "aḥ#a"


def test_lattice_partition_is_finite() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.1,
    ).fit(
        [
            "devaḥ#api",
            "rāmaḥ#api",
            "devo'pi",
        ]
    )

    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    log_z = lattice_ngram_log_partition(
        lattice,
        lm,
    )

    assert math.isfinite(log_z)


def test_viterbi_can_prefer_underlying_deva_visarga_api() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.01,
    ).fit(
        ["devaḥ#api"] * 100
        + ["devo'pi"]
    )

    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    _, path = lattice_ngram_viterbi(
        lattice,
        lm,
    )

    assert any(
        edge.kind == "sandhi"
        and edge.left_underlying == "aḥ"
        and edge.right_underlying == "a"
        for edge in path
    )


def test_marginal_score_is_at_least_viterbi_score() -> None:
    lm = CharNGramLM(
        order=3,
        alpha=0.1,
    ).fit(
        [
            "devaḥ#api",
            "devo'pi",
            "rāmaḥ#api",
        ]
    )

    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    log_z = lattice_ngram_log_partition(
        lattice,
        lm,
    )

    best_score, _ = lattice_ngram_viterbi(
        lattice,
        lm,
    )

    assert log_z >= best_score

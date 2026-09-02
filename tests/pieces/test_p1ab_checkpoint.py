from __future__ import annotations

import math

import pytest

from sktlm.latent.candidates import (
    build_candidate_graph,
    candidate_graph_fingerprint,
    candidate_graph_statistics,
)
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.lazy_candidates import (
    build_lazy_candidate_graph,
    lazy_candidate_graph_statistics,
    materialize_lazy_candidate_graph,
)
from sktlm.latent.phonology import Phoneme, parse_iast_form
from sktlm.pieces import (
    BaseMeasurePieceScorer,
    GeometricPhonemeBaseMeasure,
    ProductionPieceConfig,
    fit_production_piece_model,
    select_reusable_inventory,
)


def test_geometric_base_measure_is_normalized_and_scores_unseen_pieces() -> None:
    base = GeometricPhonemeBaseMeasure(stop_probability=0.4)
    assert base.alphabet_size == len(Phoneme)
    assert sum(base.length_mass(length) for length in range(1, 200)) == (
        pytest.approx(1.0)
    )
    unseen = parse_iast_form("batani")
    scorer = BaseMeasurePieceScorer(
        {},
        alpha=0.2,
        lambda_=0.5,
        kappa=1.0,
        beta=0.25,
        tau=1.0,
        base_measure=base,
    )
    assert scorer.probability(unseen) == pytest.approx(base.probability(unseen))
    assert math.isfinite(scorer.score(unseen))
    assert scorer.inactive_misses == 1


def test_fixed_pass_inventory_persists_only_singletons_and_reused_pieces() -> None:
    singleton = parse_iast_form("a")
    reused = parse_iast_form("ani")
    one_off = parse_iast_form("dakani")
    selected = select_reusable_inventory(
        {singleton: 1.0, reused: 2.0, one_off: 0.5},
        {singleton: 1, reused: 2, one_off: 1},
        min_reuse_occurrences=2,
    )
    assert selected == {singleton: 1.0, reused: 2.0}

    occurrences = [
        parse_iast_form(text)
        for text in ("dakani", "batani", "ramani", "dakatu", "batatu", "ramatu")
    ]
    result = fit_production_piece_model(
        occurrences,
        passes=2,
        config=ProductionPieceConfig(),
    )
    assert len(result.history) == 2
    assert result.history[0].neutral
    assert not result.history[1].neutral
    assert result.active_piece_counts
    assert all(
        len(piece.symbols) == 1
        or result.history[-1].occurrence_support[piece] >= 2
        for piece in result.active_piece_counts
    )


@pytest.mark.parametrize("surface", ("devo'pi", "devas ca"))
def test_lazy_candidate_membership_matches_materialized_m1(surface: str) -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments(surface))
    materialized = build_candidate_graph(segment, grammar)
    lazy = build_lazy_candidate_graph(segment, grammar)
    comparator = materialize_lazy_candidate_graph(lazy)

    assert candidate_graph_fingerprint(comparator) == candidate_graph_fingerprint(
        materialized
    )
    materialized_stats = candidate_graph_statistics(materialized)
    lazy_stats = lazy_candidate_graph_statistics(lazy)
    assert lazy_stats["lexical_span_hypotheses"] == materialized_stats[
        "lexical_edges"
    ]
    assert lazy_stats["lattice_nodes"] == materialized_stats["lattice_nodes"]
    assert all(
        factor.lattice is None or not hasattr(factor.lattice, "edges")
        for factor in lazy.factors
    )

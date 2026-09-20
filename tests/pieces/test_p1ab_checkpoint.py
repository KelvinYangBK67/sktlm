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
    PieceIdentity,
    PieceModel,
    PieceRole,
    ProductionPieceConfig,
    build_piece_lattice,
    fit_production_piece_model,
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


def test_fixed_pass_inventory_uses_cross_host_reusable_count() -> None:
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
    assert all(count > 0 for count in result.active_piece_counts.values())
    assert result.active_piece_counts == {
        piece: count for piece, count in result.history[-1].reusable_counts.items()
        if count > 0
    }


def test_repeated_whole_form_does_not_create_cross_type_reuse() -> None:
    form = parse_iast_form("mahābhārata")
    result = fit_production_piece_model((form,) * 4, passes=1)

    assert result.history[0].raw_expected_counts[form] > 0
    assert result.history[0].reusable_counts[form] == pytest.approx(0)
    assert form not in result.active_piece_counts


def test_distinct_hosts_use_posterior_piece_usage() -> None:
    forms = tuple(parse_iast_form(text) for text in ("devam", "devasya"))
    prefix = PieceIdentity(parse_iast_form("deva"), PieceRole.LEFT)
    model = PieceModel.neutral()
    usages = tuple(
        model.evaluate(form).expected_piece_counts[prefix] for form in forms
    )

    low_support = fit_production_piece_model(forms, passes=1)
    assert all(0.0 < usage < 1.0 for usage in usages)
    assert low_support.history[0].reusable_counts[prefix.piece] > 0

    repeated = tuple(
        form
        for form, usage in zip(forms, usages)
        for _ in range(math.ceil((1.0 + 1e-9) / usage))
    )
    enough_support = fit_production_piece_model(repeated, passes=1)

    assert enough_support.history[0].reusable_counts[prefix.piece] > (
        low_support.history[0].reusable_counts[prefix.piece]
    )


def test_positional_roles_share_learned_key() -> None:
    forms = tuple(
        parse_iast_form(text) for text in ("devam", "phalam", "rūpam", "mat")
    )
    right = PieceIdentity(parse_iast_form("m"), PieceRole.RIGHT)
    left = PieceIdentity(parse_iast_form("m"), PieceRole.LEFT)
    model = PieceModel.neutral()
    repeated_right_hosts = tuple(
        form
        for form in forms[:3]
        for _ in range(
            math.ceil(
                (1.0 + 1e-9)
                / model.evaluate(form).expected_piece_counts[right]
            )
        )
    )
    result = fit_production_piece_model(
        repeated_right_hosts + (forms[3],), passes=1
    )
    learned = result.history[0]

    assert right.key == left.key
    assert learned.raw_expected_counts[right.piece] > 0
    assert learned.reusable_counts[right.piece] > 0


def test_whole_form_fallback_remains_legal_past_piece_length_bound() -> None:
    form = parse_iast_form("mahābhārata")
    lattice = build_piece_lattice(form, max_piece_length=3)

    assert any(
        edge.start == 0
        and edge.end == len(form.symbols)
        and edge.piece == form
        and edge.role is PieceRole.WHOLE
        for edge in lattice.edges
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

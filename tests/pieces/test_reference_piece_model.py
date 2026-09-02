from __future__ import annotations

import math
from collections import Counter, defaultdict

import pytest

from sktlm.latent.candidates import (
    build_candidate_graph,
    candidate_graph_fingerprint,
)
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import NeutralFormScorer, infer_training_segment
from sktlm.latent.phonology import PhonologicalForm, parse_iast_form
from sktlm.pieces import (
    ExpectedCountPieceScorer,
    NeutralPieceScorer,
    PieceModel,
    PieceModelConfig,
    build_piece_lattice,
    evaluate_piece_lattice,
    fit_reference_piece_model,
    raw_prior_edge_score,
)


def _paths(lattice, position: int = 0):
    if position == len(lattice.form.symbols):
        yield ()
        return
    for edge in lattice.outgoing_edges[position]:
        for suffix in _paths(lattice, edge.end):
            yield (edge, *suffix)


def _logsumexp(values: list[float]) -> float:
    maximum = max(values)
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


class _TableScorer:
    def __init__(self, scores: dict[PhonologicalForm, float]) -> None:
        self.scores = scores

    def score(self, piece: PhonologicalForm) -> float:
        return self.scores.get(piece, -0.37 * len(piece.symbols))


def test_lattice_paths_concatenate_exactly_and_keep_both_extremes() -> None:
    form = parse_iast_form("dakani")
    lattice = build_piece_lattice(form, max_piece_length=3)
    paths = tuple(_paths(lattice))

    assert paths
    assert any(len(path) == 1 and path[0].piece == form for path in paths)
    assert any(all(edge.end - edge.start == 1 for edge in path) for path in paths)
    for path in paths:
        concatenated = tuple(
            symbol for edge in path for symbol in edge.piece.symbols
        )
        assert concatenated == form.symbols
        assert all(
            edge.end - edge.start <= 3 or (edge.start, edge.end) == (0, 6)
            for edge in path
        )


@pytest.mark.parametrize(
    ("text", "max_piece_length"),
    (("a", 1), ("bata", 2), ("dakani", 3), ("ramatu", 8)),
)
def test_normalized_prior_makes_every_neutral_form_score_zero(
    text: str,
    max_piece_length: int,
) -> None:
    lattice = build_piece_lattice(
        parse_iast_form(text),
        max_piece_length=max_piece_length,
    )
    evaluation = evaluate_piece_lattice(
        lattice,
        NeutralPieceScorer(),
        rho=0.31,
        top_k=10_000,
    )

    assert evaluation.log_score == pytest.approx(0.0, abs=1e-12)
    assert sum(item.probability for item in evaluation.top_segmentations) == (
        pytest.approx(1.0, abs=1e-12)
    )


def test_forward_backward_matches_brute_force_partition_and_counts() -> None:
    form = parse_iast_form("bata")
    lattice = build_piece_lattice(form, max_piece_length=2)
    scores = {
        parse_iast_form("ba"): 0.7,
        parse_iast_form("ta"): 0.4,
        parse_iast_form("bata"): -0.9,
        parse_iast_form("a"): -0.2,
    }
    scorer = _TableScorer(scores)
    rho = 0.37
    paths = tuple(_paths(lattice))
    raw_prior = [
        sum(raw_prior_edge_score(edge, rho=rho) for edge in path)
        for path in paths
    ]
    raw_scores = [
        prior + sum(scorer.score(edge.piece) for edge in path)
        for prior, path in zip(raw_prior, paths)
    ]
    prior_log_z = _logsumexp(raw_prior)
    raw_log_z = _logsumexp(raw_scores)
    probabilities = [math.exp(value - raw_log_z) for value in raw_scores]
    brute_counts: dict[PhonologicalForm, float] = defaultdict(float)
    for path, probability in zip(paths, probabilities):
        for edge in path:
            brute_counts[edge.piece] += probability

    evaluation = evaluate_piece_lattice(
        lattice,
        scorer,
        rho=rho,
        top_k=100,
    )

    assert evaluation.prior_log_normalizer == pytest.approx(prior_log_z)
    assert evaluation.log_score == pytest.approx(raw_log_z - prior_log_z)
    assert evaluation.expected_piece_counts == pytest.approx(brute_counts)
    brute_probabilities = {
        tuple(edge.piece for edge in path): probability
        for path, probability in zip(paths, probabilities)
    }
    assert {
        item.pieces: item.probability for item in evaluation.top_segmentations
    } == pytest.approx(brute_probabilities)


def test_declared_score_has_probability_and_length_aware_complexity_terms() -> None:
    short = parse_iast_form("ba")
    long = parse_iast_form("batani")
    scorer = ExpectedCountPieceScorer(
        {short: 8.0, long: 1.0},
        alpha=0.1,
        lambda_=0.7,
        kappa=1.2,
        beta=0.4,
        tau=1.0,
    )
    expected = math.log((1.0 + 0.1) / (9.0 + 0.2)) - (
        0.7
        * (1.2 + 0.4 * len(long.symbols))
        * math.log1p(1.0 / (1.0 + 1.0))
    )

    assert scorer.score(long) == pytest.approx(expected)
    assert scorer.complexity_increment(long) > scorer.complexity_increment(short)


def test_tiny_multi_pass_loop_accumulates_cross_form_reuse() -> None:
    forms = tuple(
        parse_iast_form(text)
        for text in (
            "dakani",
            "batani",
            "ramani",
            "dakatu",
            "batatu",
            "ramatu",
        )
    )
    result = fit_reference_piece_model(
        Counter(forms),
        passes=2,
        config=PieceModelConfig(max_piece_length=3, top_k=16),
    )
    pass_one = result.history[0]
    whole_counts = [pass_one.expected_piece_counts[form] for form in forms]

    assert len(result.history) == 2
    assert result.history[0].neutral
    assert not result.history[1].neutral
    assert pass_one.expected_piece_counts[parse_iast_form("ani")] > max(whole_counts)
    assert pass_one.expected_piece_counts[parse_iast_form("atu")] > max(whole_counts)
    assert result.model.score(forms[0]) == result.model.evaluate(forms[0]).log_score


def test_economy_score_does_not_unconditionally_choose_whole_or_singletons() -> None:
    form = parse_iast_form("bata")
    config = PieceModelConfig(max_piece_length=2, rho=0.5, top_k=32)
    reusable_model = PieceModel.from_expected_counts(
        {
            parse_iast_form("ba"): 100.0,
            parse_iast_form("ta"): 100.0,
            form: 0.01,
        },
        config,
    )
    memorizing_model = PieceModel.from_expected_counts(
        {
            form: 100.0,
            parse_iast_form("b"): 1.0,
            parse_iast_form("a"): 1.0,
            parse_iast_form("t"): 1.0,
        },
        config,
    )

    assert reusable_model.evaluate(form).top_segmentations[0].pieces == (
        parse_iast_form("ba"),
        parse_iast_form("ta"),
    )
    assert memorizing_model.evaluate(form).top_segmentations[0].pieces == (form,)


def test_piece_model_replaces_outer_scorer_and_composes_exact_counts() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi"))
    graph = build_candidate_graph(segment, grammar)
    graph_before = candidate_graph_fingerprint(graph)
    model = PieceModel.neutral(PieceModelConfig(max_piece_length=3, top_k=8))

    outer = infer_training_segment(
        graph,
        model,
        whitespace_merge_penalty=8.0,
    )
    baseline = infer_training_segment(
        graph,
        NeutralFormScorer(),
        whitespace_merge_penalty=8.0,
    )
    piece_counts = model.expected_counts_from_outer(outer.expected_counts)
    manual: dict[PhonologicalForm, float] = defaultdict(float)
    for form, outer_mass in outer.expected_counts.items():
        if outer_mass <= 0.0:
            continue
        for piece, inner_count in model.evaluate(form).expected_piece_counts.items():
            manual[piece] += outer_mass * inner_count

    assert candidate_graph_fingerprint(graph) == graph_before
    assert outer.log_partition == pytest.approx(baseline.log_partition)
    assert outer.expected_counts == pytest.approx(baseline.expected_counts)
    assert outer.identity_mass + outer.latent_mass == pytest.approx(1.0)
    assert piece_counts == pytest.approx(manual)
    assert model.cache_hits > 0

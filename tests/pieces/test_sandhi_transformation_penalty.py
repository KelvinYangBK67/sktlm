from __future__ import annotations

import math
from dataclasses import replace

import pytest

import sktlm.pieces.composed as composed_module
from sktlm.experiments.training.latent_lexicon import build_arg_parser
from sktlm.latent.candidates import CandidateConfig
from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import infer_segment
from sktlm.latent.lazy_candidates import (
    build_lazy_candidate_graph,
    materialize_lazy_candidate_graph,
)
from sktlm.latent.phonology import PhonologicalForm, parse_iast_form
from sktlm.latent.training import S1M2_MODEL, TrainingConfig, _config_signature
from sktlm.pieces import (
    ComposedCacheConfig,
    ComposedPieceInference,
    PieceModel,
    PieceModelConfig,
    compile_composed_segment_topology,
    infer_composed_segment,
)
from sktlm.sandhi.rules import SandhiRule


class _ZeroScorer:
    def score(self, _piece: PhonologicalForm) -> float:
        return 0.0


def _internal_ve_grammar(*, duplicate_rule_ids: bool = False):
    rules = [SandhiRule("TEST_VE_1", "ū", "e", "ve", 1, "active")]
    if duplicate_rule_ids:
        rules.append(
            SandhiRule("TEST_VE_2", "ū", "e", "ve", 2, "active")
        )
    return StructuredSandhiGrammar(rules)


def _run_composed(
    surface: str,
    grammar: StructuredSandhiGrammar,
    gamma: float,
    route: str,
):
    graph = build_lazy_candidate_graph(
        next(iter_observed_segments(surface)),
        grammar,
        CandidateConfig(allow_whitespace_merge=False),
    )
    cache_config = ComposedCacheConfig(
        shared_token_marginals=route != "legacy"
    )
    engine = ComposedPieceInference(
        _ZeroScorer(),
        model_config=PieceModelConfig(max_piece_length=4),
        cache_config=cache_config,
        inspection_top_k=512,
    )
    topology = None
    if route == "shared":
        topology = compile_composed_segment_topology(graph, engine)
    return infer_composed_segment(
        graph,
        engine,
        whitespace_merge_penalty=8.0,
        sandhi_transformation_penalty=gamma,
        topology=topology,
    )


def _best_analysis_score(result, words: tuple[str, ...]) -> float:
    scores = [
        analysis.log_score
        for analysis in result.top_analyses
        if tuple(word.iast for word in analysis.words) == words
    ]
    assert scores, words
    return max(scores)


def test_gamma_zero_matches_existing_materialized_scoring() -> None:
    grammar = _internal_ve_grammar()
    graph = build_lazy_candidate_graph(
        next(iter_observed_segments("ve")),
        grammar,
        CandidateConfig(allow_whitespace_merge=False),
    )
    model_config = PieceModelConfig(max_piece_length=4)
    reference_model = PieceModel(model_config, scorer=_ZeroScorer())
    reference = infer_segment(
        materialize_lazy_candidate_graph(graph),
        reference_model,
        whitespace_merge_penalty=8.0,
        top_k=512,
    )
    observed = infer_composed_segment(
        graph,
        ComposedPieceInference(
            _ZeroScorer(),
            model_config=model_config,
            inspection_top_k=512,
        ),
        whitespace_merge_penalty=8.0,
        sandhi_transformation_penalty=0.0,
    )

    assert observed.log_partition.hex() == reference.log_partition.hex()
    assert observed.lexical_expected_counts == reference.expected_counts
    assert observed.rule_usage == reference.rule_usage


@pytest.mark.parametrize("route", ("compact", "shared", "legacy"))
def test_internal_penalty_counts_events_not_rule_ids(route: str) -> None:
    gamma = 1.75
    grammar = _internal_ve_grammar(duplicate_rule_ids=True)

    one_zero = _run_composed("ve", grammar, 0.0, route)
    one_penalized = _run_composed("ve", grammar, gamma, route)
    one_transformed_zero = _best_analysis_score(one_zero, ("ū", "e"))
    one_transformed_penalized = _best_analysis_score(
        one_penalized, ("ū", "e")
    )
    one_direct_zero = _best_analysis_score(one_zero, ("ve",))
    one_direct_penalized = _best_analysis_score(one_penalized, ("ve",))

    assert one_direct_penalized == one_direct_zero
    assert one_transformed_penalized == pytest.approx(
        one_transformed_zero - gamma, abs=1e-12
    )
    target = next(
        analysis
        for analysis in one_penalized.top_analyses
        if tuple(word.iast for word in analysis.words) == ("ū", "e")
    )
    assert target.rule_ids == ("TEST_VE_1", "TEST_VE_2")

    two_zero = _run_composed("veve", grammar, 0.0, route)
    two_penalized = _run_composed("veve", grammar, gamma, route)
    two_words = ("ū", "eū", "e")
    assert _best_analysis_score(two_penalized, two_words) == pytest.approx(
        _best_analysis_score(two_zero, two_words) - 2.0 * gamma,
        abs=1e-12,
    )


def test_visible_transformation_is_legal_and_charged_on_outgoing_factor() -> None:
    gamma = 2.25
    grammar = StructuredSandhiGrammar.from_default_inventory()
    graph = build_lazy_candidate_graph(
        next(iter_observed_segments("svayaṃbhv ekam")),
        grammar,
        CandidateConfig(allow_whitespace_merge=False),
    )
    option = next(
        option
        for option in graph.boundary_options[1]
        if "EXT_0219" in option.rule_ids
        and option.left_underlying == parse_iast_form("ū").symbols
        and option.right_underlying == parse_iast_form("e").symbols
    )
    left = next(
        factor
        for factor in graph.factors
        if factor.start_token == 0 and factor.outgoing == option
    )
    right = next(
        factor
        for factor in graph.factors
        if factor.start_token == 1 and factor.incoming == option
    )
    assert left.lattice is not None
    assert right.lattice is not None
    assert left.lattice.span(0, len(left.lattice.nodes) - 1).word == (
        parse_iast_form("svayaṃbhū")
    )
    assert right.lattice.span(0, len(right.lattice.nodes) - 1).word == (
        parse_iast_form("ekam")
    )

    engine = ComposedPieceInference(
        _ZeroScorer(), model_config=PieceModelConfig(max_piece_length=4)
    )
    left_zero = composed_module._score_factor(
        left,
        engine,
        whitespace_merge_penalty=8.0,
        support_epsilon=0.0,
        sandhi_transformation_penalty=0.0,
    )
    left_penalized = composed_module._score_factor(
        left,
        engine,
        whitespace_merge_penalty=8.0,
        support_epsilon=0.0,
        sandhi_transformation_penalty=gamma,
    )
    right_zero = composed_module._score_factor(
        right,
        engine,
        whitespace_merge_penalty=8.0,
        support_epsilon=0.0,
        sandhi_transformation_penalty=0.0,
    )
    right_penalized = composed_module._score_factor(
        right,
        engine,
        whitespace_merge_penalty=8.0,
        support_epsilon=0.0,
        sandhi_transformation_penalty=gamma,
    )
    left_inner_penalized, _ = composed_module._score_lazy_token(
        left.lattice,
        engine,
        support_epsilon=0.0,
        sandhi_transformation_penalty=gamma,
    )
    right_inner_penalized, _ = composed_module._score_lazy_token(
        right.lattice,
        engine,
        support_epsilon=0.0,
        sandhi_transformation_penalty=gamma,
    )

    assert option.transformed
    assert left_penalized.log_score == pytest.approx(
        left_inner_penalized - gamma, abs=1e-12
    )
    assert right_penalized.log_score == right_inner_penalized
    assert left_zero.log_score > left_penalized.log_score
    assert right_zero.log_score == right_penalized.log_score


def test_direct_visible_boundaries_keep_raja_n_dha_complete() -> None:
    graph = build_lazy_candidate_graph(
        next(iter_observed_segments("rāja n dha")),
        StructuredSandhiGrammar.from_default_inventory(),
        CandidateConfig(allow_whitespace_merge=False),
    )
    result = infer_composed_segment(
        graph,
        ComposedPieceInference(
            _ZeroScorer(), model_config=PieceModelConfig(max_piece_length=4)
        ),
        whitespace_merge_penalty=8.0,
        sandhi_transformation_penalty=3.0,
    )

    assert math.isfinite(result.log_partition)
    assert not any(factor.is_merge for factor in graph.factors)
    assert all(
        any(option.direct and not option.transformed for option in options)
        for options in graph.boundary_options[1:-1]
    )


def test_gamma_is_cli_config_and_s1m2_signature_state() -> None:
    base = TrainingConfig(model=S1M2_MODEL)
    changed = replace(base, sandhi_transformation_penalty=0.75)
    parsed = build_arg_parser().parse_args(
        ["--sandhi-transformation-penalty", "0.75"]
    )

    assert base.payload()["sandhi_transformation_penalty"] == 0.0
    assert changed.payload()["sandhi_transformation_penalty"] == 0.75
    assert _config_signature(base) != _config_signature(changed)
    assert parsed.sandhi_transformation_penalty == 0.75
    assert "sandhi_transformation_penalty" not in TrainingConfig().payload()
    with pytest.raises(ValueError, match="must be >= 0"):
        TrainingConfig(
            model=S1M2_MODEL,
            sandhi_transformation_penalty=-0.1,
        )

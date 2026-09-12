from __future__ import annotations

from dataclasses import replace
import math
import sqlite3

import pytest

import sktlm.pieces.composed as composed_module
from sktlm.latent.candidates import CandidateBuildProfile, CandidateConfig
from sktlm.latent.frontend import iter_observed_segments, parse_surface
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import infer_segment
from sktlm.latent.lazy_candidates import (
    build_lazy_candidate_graph,
    materialize_lazy_candidate_graph,
)
from sktlm.latent.phonology import Phoneme, PhonologicalForm, parse_iast_form
from sktlm.latent.store import PieceStoreScorer
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.pieces import (
    BaseMeasurePieceScorer,
    ComposedCacheConfig,
    ComposedPieceInference,
    PieceModel,
    PieceModelConfig,
    build_piece_lattice,
    compile_composed_segment_topology,
    evaluate_piece_lattice,
    infer_composed_segment,
)
from sktlm.representations.devanagari import transliterate_iast_to_devanagari
from sktlm.representations.m0_prime import (
    transliterate_devanagari_to_m0_prime_iast,
)
from sktlm.representations.spacing import continuous_spacing


class _TableScorer:
    def score(self, piece: PhonologicalForm) -> float:
        return -0.17 * len(piece.symbols) + (0.31 if piece.iast == "ani" else 0.0)


def _production_scorer() -> BaseMeasurePieceScorer:
    return BaseMeasurePieceScorer(
        {
            parse_iast_form("a"): 7.0,
            parse_iast_form("i"): 5.0,
            parse_iast_form("devaḥ"): 2.5,
            parse_iast_form("api"): 4.0,
            parse_iast_form("ani"): 3.0,
        },
        alpha=0.1,
        lambda_=0.5,
        kappa=1.0,
        beta=0.25,
        tau=1.0,
    )


@pytest.mark.parametrize(
    "text",
    ("a", "bata", "dakani", "dakaniyat"),
)
def test_direct_form_dp_matches_p0_without_piece_lattice(text: str) -> None:
    form = parse_iast_form(text)
    config = PieceModelConfig(max_piece_length=3, rho=0.37)
    reference = evaluate_piece_lattice(
        build_piece_lattice(form, max_piece_length=config.max_piece_length),
        _TableScorer(),
        rho=config.rho,
        top_k=None,
    )
    engine = ComposedPieceInference(_TableScorer(), model_config=config)

    composed = engine.evaluate_form(form)

    assert composed.prior_log_normalizer == pytest.approx(
        reference.prior_log_normalizer, rel=1e-10, abs=1e-12
    )
    assert composed.log_score == pytest.approx(
        reference.log_score, rel=1e-10, abs=1e-12
    )
    assert composed.expected_piece_counts == pytest.approx(
        reference.expected_piece_counts, rel=1e-10, abs=1e-12
    )
    assert composed.whole_form_mass > 0.0
    assert composed.singleton_path_mass > 0.0
    assert composed.multi_piece_mass == pytest.approx(1.0 - composed.whole_form_mass)


def test_batched_inner_top_k_matches_p0_order_and_weights() -> None:
    form = parse_iast_form("dakaniyat")
    config = PieceModelConfig(max_piece_length=3, rho=0.37)
    top_k = 5
    reference = evaluate_piece_lattice(
        build_piece_lattice(form, max_piece_length=config.max_piece_length),
        _TableScorer(),
        rho=config.rho,
        top_k=top_k,
    )
    engine = ComposedPieceInference(
        _TableScorer(),
        model_config=config,
        inspection_top_k=top_k,
    )

    composed = engine.evaluate_form(form)

    assert tuple(
        tuple(piece.key for piece in item.pieces)
        for item in composed.top_segmentations
    ) == tuple(
        tuple(piece.key for piece in item.pieces)
        for item in reference.top_segmentations
    )
    assert tuple(item.log_weight for item in composed.top_segmentations) == pytest.approx(
        tuple(item.log_weight for item in reference.top_segmentations),
        rel=1e-10,
        abs=1e-12,
    )
    assert tuple(item.probability for item in composed.top_segmentations) == pytest.approx(
        tuple(item.probability for item in reference.top_segmentations),
        rel=1e-10,
        abs=1e-12,
    )


def test_shared_piece_and_form_caches_are_bounded_and_counted() -> None:
    cache = ComposedCacheConfig(
        piece_score_entries=3,
        piece_score_bytes=1_000_000,
        form_entries=2,
        form_bytes=1_000_000,
    )
    scorer = _production_scorer()
    engine = ComposedPieceInference(
        scorer,
        model_config=PieceModelConfig(max_piece_length=3),
        cache_config=cache,
    )
    forms = tuple(
        parse_iast_form(text) for text in ("dakani", "batani", "ramani")
    )
    for form in forms:
        engine.evaluate_form(form)
    engine.evaluate_form(PhonologicalForm(forms[-1].symbols))
    counters = engine.counter_snapshot()

    assert counters.form_cache_entries <= cache.form_entries
    assert counters.form_cache_estimated_bytes <= cache.form_bytes
    assert counters.piece_score_cache_entries <= cache.piece_score_entries
    assert counters.piece_score_cache_estimated_bytes <= cache.piece_score_bytes
    assert counters.form_cache_misses == 3
    assert counters.form_cache_hits == 1
    assert counters.form_cache_evictions >= 1
    assert counters.piece_score_cache_misses > 0
    assert counters.piece_score_calls == (
        counters.piece_score_cache_hits + counters.piece_score_cache_misses
    )
    assert counters.store_lookups == scorer.store_lookups


def test_candidate_build_profiling_does_not_change_lazy_graph() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi api ca"))
    plain = build_lazy_candidate_graph(segment, grammar)
    profile = CandidateBuildProfile()
    observed = build_lazy_candidate_graph(segment, grammar, profile=profile)

    assert observed == plain
    assert profile.internal_match_calls > 0
    assert profile.unfiltered_internal_matches > 0
    assert profile.factor_combinations_attempted >= len(observed.factors)
    assert profile.factor_construction_seconds >= profile.grammar_match_seconds

    first_factor = next(factor for factor in observed.factors if factor.lattice)
    first_span = next(first_factor.lattice.iter_spans())
    assert first_span.word is first_span.word
    assert first_span.symbols == first_span.word.symbols


def test_inspection_top_paths_are_bounded_and_keep_exact_concatenation() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi"))
    graph = build_lazy_candidate_graph(segment, grammar)
    engine = ComposedPieceInference(
        _production_scorer(),
        model_config=PieceModelConfig(max_piece_length=3),
        inspection_top_k=5,
    )

    inference = infer_composed_segment(
        graph,
        engine,
        whitespace_merge_penalty=8.0,
    )

    assert 0 < len(inference.top_analyses) <= 5
    assert inference.top_analysis_mass <= 1.0 + 1e-12
    assert inference.piece_occurrence_support
    for analysis in inference.top_analyses:
        assert len(analysis.words) == len(analysis.piece_segmentations)
        for word, pieces in zip(analysis.words, analysis.piece_segmentations):
            assert tuple(
                symbol for piece in pieces for symbol in piece.symbols
            ) == word.symbols


def _compare_outer(surface: str, *, script: str = "iast") -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments(surface, script=script))
    lazy = build_lazy_candidate_graph(segment, grammar)
    materialized = materialize_lazy_candidate_graph(lazy)
    config = PieceModelConfig(max_piece_length=3, rho=0.41)
    reference_model = PieceModel(config, scorer=_production_scorer())
    reference = infer_segment(
        materialized,
        reference_model,
        whitespace_merge_penalty=8.0,
        top_k=64,
    )
    expected_piece_counts = reference_model.expected_counts_from_outer(
        reference.expected_counts
    )
    engine = ComposedPieceInference(
        _production_scorer(),
        model_config=config,
        cache_config=ComposedCacheConfig(
            piece_score_entries=512,
            piece_score_bytes=2_000_000,
            form_entries=256,
            form_bytes=4_000_000,
        ),
    )

    composed = infer_composed_segment(
        lazy,
        engine,
        whitespace_merge_penalty=8.0,
    )

    assert composed.top_analyses == ()
    assert composed.log_partition == pytest.approx(
        reference.log_partition, rel=1e-10, abs=1e-12
    )
    assert composed.lexical_expected_counts == pytest.approx(
        reference.expected_counts, rel=1e-10, abs=1e-12
    )
    assert composed.piece_expected_counts == pytest.approx(
        expected_piece_counts, rel=1e-10, abs=1e-12
    )
    assert composed.identity_mass == pytest.approx(
        reference.identity_mass, rel=1e-10, abs=1e-12
    )
    assert composed.latent_mass == pytest.approx(
        reference.latent_mass, rel=1e-10, abs=1e-12
    )
    assert composed.expected_lexical_tokens == pytest.approx(
        reference.expected_lexical_tokens, rel=1e-10, abs=1e-12
    )
    assert composed.rule_usage == pytest.approx(
        reference.rule_usage, rel=1e-10, abs=1e-12
    )
    reference_boundaries = {
        item.boundary_id: item.probability for item in reference.boundary_posteriors
    }
    composed_boundaries = {
        item.boundary_id: item.probability for item in composed.boundary_posteriors
    }
    assert composed_boundaries == pytest.approx(
        reference_boundaries, rel=1e-10, abs=1e-12
    )
    assert composed.total_posterior_mass == pytest.approx(1.0, abs=1e-12)
    assert composed.counters.candidate_factors == len(lazy.factors)
    assert composed.counters.candidate_nodes > 0
    assert composed.counters.candidate_span_hypotheses > 0
    assert composed.counters.lazy_span_traversals >= (
        composed.counters.candidate_span_hypotheses
    )
    assert composed.counters.composed_state_count > 0
    assert composed.counters.composed_transition_count > 0
    assert composed.timings.piece_composition_seconds > 0.0
    assert composed.timings.inner_piece_evaluation_seconds > 0.0
    assert composed.timings.inner_piece_transition_build_seconds > 0.0
    assert composed.timings.inner_piece_forward_seconds > 0.0
    assert composed.timings.inner_piece_backward_seconds > 0.0
    assert composed.timings.inner_piece_posterior_seconds > 0.0
    assert composed.timings.lazy_token_forward_seconds > 0.0
    assert composed.timings.lazy_token_backward_seconds > 0.0
    assert composed.timings.lazy_token_posterior_seconds > 0.0
    assert composed.timings.outer_forward_seconds > 0.0
    assert composed.timings.outer_backward_seconds > 0.0
    assert composed.timings.outer_posterior_seconds > 0.0
    assert composed.timings.outer_identity_seconds > 0.0
    assert composed.timings.inner_piece_top_k_seconds == 0.0
    assert composed.timings.lazy_token_top_k_seconds == 0.0
    assert composed.timings.outer_top_k_seconds == 0.0


@pytest.mark.parametrize(
    "surface",
    (
        "devo'pi",  # sandhi ambiguity and avagraha
        "devas ca",  # visible-space evidence
        "devaśca",  # legacy/joined-like spelling
        "tattvamasi",  # continuous-like no-space span
    ),
)
def test_opt18_lazy_composed_outer_matches_materialized_oracle(surface: str) -> None:
    _compare_outer(surface)


@pytest.mark.parametrize("surface", ("devo'pi", "devaśca", "tattvamasi"))
def test_shared_token_marginals_match_legacy_exact_path(surface: str) -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments(surface))
    graph = build_lazy_candidate_graph(segment, grammar)
    config = PieceModelConfig(max_piece_length=3, rho=0.41)

    def run(*, shared: bool):
        return infer_composed_segment(
            graph,
            ComposedPieceInference(
                _production_scorer(),
                model_config=config,
                cache_config=ComposedCacheConfig(
                    shared_token_marginals=shared,
                ),
            ),
            whitespace_merge_penalty=8.0,
        )

    observed = run(shared=True)
    reference = run(shared=False)

    for name in (
        "log_partition",
        "entropy",
        "identity_mass",
        "latent_mass",
        "expected_lexical_tokens",
        "expected_piece_tokens",
        "piece_segmentation_entropy",
        "expected_whole_form_uses",
        "expected_singleton_path_uses",
        "expected_multi_piece_uses",
        "top_analysis_mass",
        "total_posterior_mass",
    ):
        assert getattr(observed, name) == pytest.approx(
            getattr(reference, name),
            rel=1e-10,
            abs=1e-12,
        )
    assert observed.lexical_expected_counts == pytest.approx(
        reference.lexical_expected_counts,
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.piece_expected_counts == pytest.approx(
        reference.piece_expected_counts,
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.rule_usage == pytest.approx(
        reference.rule_usage,
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.piece_occurrence_support == reference.piece_occurrence_support
    assert {
        item.boundary_id: item.probability
        for item in observed.boundary_posteriors
    } == pytest.approx(
        {
            item.boundary_id: item.probability
            for item in reference.boundary_posteriors
        },
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.top_analyses == reference.top_analyses == ()
    assert observed.counters.lazy_span_traversals < (
        reference.counters.lazy_span_traversals
    )
    assert observed.counters.composed_transition_count < (
        reference.counters.composed_transition_count
    )


def test_shared_zero_epsilon_occurrences_stay_structurally_compact() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments('tattvamasi'))
    graph = build_lazy_candidate_graph(segment, grammar)
    factor = next(item for item in graph.factors if item.lattice is not None)
    summary = composed_module._evaluate_lazy_token_shared(
        factor.lattice,
        ComposedPieceInference(
            _production_scorer(),
            model_config=PieceModelConfig(max_piece_length=3),
        ),
    )

    assert summary is not None
    assert summary.piece_occurrences == {}
    assert summary.shared_occurrences == ()
    assert summary.compact_occurrences is not None
    support = summary.compact_occurrences
    stored_occurrences = sum(
        len(endpoint.occurrence_ids) for endpoint in support.endpoints
    )
    assert stored_occurrences > 0
    assert len(support.root_nodes) == len(support.root_piece_ids)
    assert support.root_nodes
    assert all(
        isinstance(occurrence_id, int)
        for endpoint in support.endpoints
        for occurrence_id in endpoint.occurrence_ids
    )


def test_compact_structural_trie_does_not_fall_back_to_span_materialization() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devaśca"))
    graph = build_lazy_candidate_graph(segment, grammar)
    result = infer_composed_segment(
        graph,
        ComposedPieceInference(
            _production_scorer(),
            model_config=PieceModelConfig(max_piece_length=3),
            cache_config=ComposedCacheConfig(shared_prefix_nodes=1),
        ),
        whitespace_merge_penalty=8.0,
    )

    assert result.total_posterior_mass == pytest.approx(1.0, abs=1e-12)
    assert result.counters.compact_trie_compiles > 0
    assert result.counters.shared_batch_fallbacks == 0
    assert result.counters.form_cache_misses == 0


def test_compiled_topology_reweights_changed_piece_parameters_exactly() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi"))
    graph = build_lazy_candidate_graph(segment, grammar)
    config = PieceModelConfig(max_piece_length=3, rho=0.41)
    topology = compile_composed_segment_topology(
        graph,
        ComposedPieceInference(_TableScorer(), model_config=config),
    )
    topology = replace(topology, reused=True)

    reference = infer_composed_segment(
        graph,
        ComposedPieceInference(
            _production_scorer(),
            model_config=config,
            inspection_top_k=5,
        ),
        whitespace_merge_penalty=8.0,
    )
    observed = infer_composed_segment(
        graph,
        ComposedPieceInference(
            _production_scorer(),
            model_config=config,
            inspection_top_k=5,
        ),
        whitespace_merge_penalty=8.0,
        topology=topology,
    )

    for name in (
        "log_partition",
        "entropy",
        "identity_mass",
        "latent_mass",
        "expected_lexical_tokens",
        "expected_piece_tokens",
        "piece_segmentation_entropy",
        "expected_whole_form_uses",
        "expected_singleton_path_uses",
        "expected_multi_piece_uses",
        "top_analysis_mass",
        "total_posterior_mass",
    ):
        assert getattr(observed, name) == pytest.approx(
            getattr(reference, name), rel=1e-10, abs=1e-12
        )
    assert observed.lexical_expected_counts == pytest.approx(
        reference.lexical_expected_counts, rel=1e-10, abs=1e-12
    )
    assert observed.piece_expected_counts == pytest.approx(
        reference.piece_expected_counts, rel=1e-10, abs=1e-12
    )
    assert observed.rule_usage == pytest.approx(
        reference.rule_usage, rel=1e-10, abs=1e-12
    )
    assert observed.boundary_posteriors == reference.boundary_posteriors
    assert observed.top_analyses == reference.top_analyses
    assert observed.piece_occurrence_support == reference.piece_occurrence_support
    assert observed.counters.topology_reuses == sum(
        factor is not None for factor in topology.factors
    )


@pytest.mark.parametrize("surface", ("devo'pi", "tattvamasi"))
def test_opt18_shared_inspection_paths_match_legacy_exact_path(surface: str) -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments(surface))
    graph = build_lazy_candidate_graph(segment, grammar)
    config = PieceModelConfig(max_piece_length=3, rho=0.41)

    def run(*, shared: bool):
        return infer_composed_segment(
            graph,
            ComposedPieceInference(
                _production_scorer(),
                model_config=config,
                cache_config=ComposedCacheConfig(
                    shared_token_marginals=shared,
                ),
                inspection_top_k=5,
            ),
            whitespace_merge_penalty=8.0,
        )

    observed = run(shared=True)
    reference = run(shared=False)

    assert observed.log_partition == pytest.approx(
        reference.log_partition,
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.lexical_expected_counts == pytest.approx(
        reference.lexical_expected_counts,
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.piece_expected_counts == pytest.approx(
        reference.piece_expected_counts,
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.piece_occurrence_support == reference.piece_occurrence_support
    assert len(observed.top_analyses) == len(reference.top_analyses)
    for actual, expected in zip(observed.top_analyses, reference.top_analyses):
        assert tuple(form.key for form in actual.words) == tuple(
            form.key for form in expected.words
        )
        assert tuple(
            tuple(piece.key for piece in segmentation)
            for segmentation in actual.piece_segmentations
        ) == tuple(
            tuple(piece.key for piece in segmentation)
            for segmentation in expected.piece_segmentations
        )
        assert actual.rule_ids == expected.rule_ids
        assert actual.boundaries == expected.boundaries
        assert actual.log_score == pytest.approx(
            expected.log_score,
            rel=1e-10,
            abs=1e-12,
        )
        assert actual.probability == pytest.approx(
            expected.probability,
            rel=1e-10,
            abs=1e-12,
        )
    assert observed.top_analysis_mass == pytest.approx(
        reference.top_analysis_mass,
        rel=1e-10,
        abs=1e-12,
    )
    assert observed.counters.composed_transition_count < (
        reference.counters.composed_transition_count
    )
    assert observed.counters.form_cache_misses == 0
    assert observed.counters.shared_top_k_states > 0
    assert observed.counters.shared_top_k_paths >= (
        observed.counters.shared_top_k_states
    )


def test_opt18_shared_top_k_retains_compact_exact_backpointers() -> None:
    forms = tuple(
        parse_iast_form(text)
        for text in ("dakani", "dakaniva", "dakanitara")
    )
    config = PieceModelConfig(max_piece_length=3, rho=0.41)
    engine = ComposedPieceInference(
        _production_scorer(),
        model_config=config,
        inspection_top_k=5,
    )
    batch = engine._build_shared_form_batch(forms)

    assert batch is not None
    assert batch.top_paths is not None
    assert all(
        path.piece is None or isinstance(path.piece, PhonologicalForm)
        for paths in batch.top_paths
        for path in paths
    )
    assert any(
        path.parent is not None and path.parent.piece is not None
        for paths in batch.top_paths
        for path in paths
    )
    for form in forms:
        shared = engine._shared_top_segmentations(batch, batch.forms[form.key])
        reference = engine.evaluate_form(form).top_segmentations
        assert tuple(
            tuple(piece.key for piece in item.pieces) for item in shared
        ) == tuple(
            tuple(piece.key for piece in item.pieces) for item in reference
        )
        assert tuple(item.log_weight for item in shared) == pytest.approx(
            tuple(item.log_weight for item in reference),
            rel=1e-10,
            abs=1e-12,
        )


def test_opt19_adaptive_factor_retention_is_exact_and_cumulatively_bounded() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi api ca"))
    graph = build_lazy_candidate_graph(segment, grammar)
    config = PieceModelConfig(max_piece_length=3, rho=0.41)
    topology = compile_composed_segment_topology(
        graph,
        ComposedPieceInference(_production_scorer(), model_config=config),
    )
    estimator = ComposedPieceInference(
        _production_scorer(),
        model_config=config,
        inspection_top_k=5,
    )
    estimates = tuple(
        composed_module._factor_retention_estimate(
            factor,
            factor_topology,
            estimator,
            support_epsilon=0.0,
        )
        for factor, factor_topology in zip(graph.factors, topology.factors)
    )
    assert all(item is not None for item in estimates)
    full_budget = sum(item.retained_bytes for item in estimates if item is not None)

    def run(budget: int):
        return infer_composed_segment(
            graph,
            ComposedPieceInference(
                _production_scorer(),
                model_config=config,
                cache_config=ComposedCacheConfig(
                    inspection_retained_factor_bytes=budget,
                ),
                inspection_top_k=5,
            ),
            whitespace_merge_penalty=8.0,
            topology=topology,
        )

    one_pass = run(full_budget)
    two_pass = run(1)

    for name in (
        "log_partition",
        "entropy",
        "identity_mass",
        "latent_mass",
        "expected_lexical_tokens",
        "expected_piece_tokens",
        "piece_segmentation_entropy",
        "expected_whole_form_uses",
        "expected_singleton_path_uses",
        "expected_multi_piece_uses",
        "lexical_expected_counts",
        "piece_expected_counts",
        "rule_usage",
        "boundary_posteriors",
        "top_analyses",
        "top_analysis_mass",
        "piece_occurrence_support",
        "total_posterior_mass",
    ):
        assert getattr(one_pass, name) == getattr(two_pass, name)
    assert one_pass.counters.fast_path_factors == len(graph.factors)
    assert one_pass.counters.two_pass_factors == 0
    assert one_pass.counters.recomputed_factors == 0
    assert one_pass.counters.retained_budget_peak_bytes == full_budget
    assert two_pass.counters.fast_path_factors == 0
    assert two_pass.counters.two_pass_factors == len(graph.factors)
    assert two_pass.counters.recomputed_factors == len(graph.factors)
    assert two_pass.counters.retained_budget_peak_bytes == 0
    nonmerged_index = next(
        index for index, factor in enumerate(graph.factors) if factor.lattice is not None
    )
    compact_estimate = composed_module._factor_retention_estimate(
        graph.factors[nonmerged_index],
        None,
        estimator,
        support_epsilon=0.0,
    )
    assert compact_estimate is not None
    assert compact_estimate.retained_bytes > 0


@pytest.mark.parametrize("surface", ("devo'pi", "tattvamasi"))
def test_compact_structural_trie_matches_legacy_shared_oracle(surface: str) -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments(surface))
    graph = build_lazy_candidate_graph(segment, grammar)
    config = PieceModelConfig(max_piece_length=2, rho=0.41)
    topology = compile_composed_segment_topology(
        graph,
        ComposedPieceInference(_production_scorer(), model_config=config),
    )

    def run(*, legacy: bool):
        return infer_composed_segment(
            graph,
            ComposedPieceInference(
                _production_scorer(),
                model_config=config,
                inspection_top_k=5,
            ),
            whitespace_merge_penalty=8.0,
            topology=topology if legacy else None,
        )

    compact = run(legacy=False)
    legacy = run(legacy=True)
    for name in (
        "log_partition",
        "entropy",
        "identity_mass",
        "latent_mass",
        "expected_lexical_tokens",
        "expected_piece_tokens",
        "piece_segmentation_entropy",
        "expected_whole_form_uses",
        "expected_singleton_path_uses",
        "expected_multi_piece_uses",
        "top_analysis_mass",
        "total_posterior_mass",
    ):
        assert getattr(compact, name) == pytest.approx(
            getattr(legacy, name), rel=1e-10, abs=1e-12
        )
    assert compact.lexical_expected_counts == pytest.approx(
        legacy.lexical_expected_counts, rel=1e-10, abs=1e-12
    )
    assert compact.piece_expected_counts == pytest.approx(
        legacy.piece_expected_counts, rel=1e-10, abs=1e-12
    )
    assert compact.rule_usage == pytest.approx(
        legacy.rule_usage, rel=1e-10, abs=1e-12
    )
    assert compact.boundary_posteriors == legacy.boundary_posteriors
    assert compact.top_analyses == legacy.top_analyses
    assert compact.piece_occurrence_support == legacy.piece_occurrence_support
    assert compact.counters.compact_trie_compiles > 0
    assert compact.counters.support_truncation_tokens == 0


def test_compact_route_does_not_materialize_forms_per_span(monkeypatch) -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("tattvamasi"))
    graph = build_lazy_candidate_graph(segment, grammar)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy per-span form construction was used")

    monkeypatch.setattr(composed_module.LazyTokenLattice, "span", forbidden)
    monkeypatch.setattr(
        composed_module.LazyTokenLattice, "iter_spans_from", forbidden
    )
    monkeypatch.setattr(
        composed_module.ComposedPieceInference, "_legal_pieces", forbidden
    )
    result = infer_composed_segment(
        graph,
        ComposedPieceInference(
            _production_scorer(),
            model_config=PieceModelConfig(max_piece_length=2),
        ),
        whitespace_merge_penalty=8.0,
    )

    assert result.total_posterior_mass == pytest.approx(1.0, abs=1e-12)
    assert result.counters.compact_endpoint_occurrences > 0


def test_compact_occurrence_support_deduplicates_and_keeps_long_whole_form() -> None:
    grammar = StructuredSandhiGrammar(())
    config = CandidateConfig(allow_whitespace_merge=False)
    model_config = PieceModelConfig(max_piece_length=2)

    repeated_graph = build_lazy_candidate_graph(
        next(iter_observed_segments("aaaa")), grammar, config
    )
    repeated = infer_composed_segment(
        repeated_graph,
        ComposedPieceInference(
            _production_scorer(), model_config=model_config
        ),
        whitespace_merge_penalty=8.0,
    )
    repeated_legacy = infer_composed_segment(
        repeated_graph,
        ComposedPieceInference(
            _production_scorer(), model_config=model_config
        ),
        whitespace_merge_penalty=8.0,
        topology=compile_composed_segment_topology(
            repeated_graph,
            ComposedPieceInference(
                _production_scorer(), model_config=model_config
            ),
        ),
    )
    singleton = parse_iast_form("a")
    long_whole = parse_iast_form("aaaa")
    assert repeated.piece_occurrence_support[singleton] == 1
    assert repeated.piece_occurrence_support[long_whole] == 1
    assert (
        repeated.piece_occurrence_support
        == repeated_legacy.piece_occurrence_support
    )

    twice_graph = build_lazy_candidate_graph(
        next(iter_observed_segments("a a")), grammar, config
    )
    twice = infer_composed_segment(
        twice_graph,
        ComposedPieceInference(
            _production_scorer(), model_config=model_config
        ),
        whitespace_merge_penalty=8.0,
    )
    assert twice.piece_occurrence_support[singleton] == 2


def test_compact_candidates_keep_matches_beyond_legacy_pressure_limit() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("tattvamasi"))
    config = CandidateConfig(max_internal_matches=1)
    compact = build_lazy_candidate_graph(segment, grammar, config)
    legacy = build_lazy_candidate_graph(
        segment,
        grammar,
        config,
        exact_internal_matches=False,
    )

    assert compact.overflowed_tokens == 0
    assert compact.historical_match_pressure_tokens > 0
    assert any(
        lattice.retained_internal_matches > 1
        for factor in compact.factors
        if (lattice := factor.lattice) is not None
    )
    assert legacy.overflowed_tokens > 0


def test_piece_store_flat_counts_preserve_exact_scoring_equation() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE piece_lexicon (form_key TEXT PRIMARY KEY, "
        "expected_count REAL NOT NULL)"
    )
    active = parse_iast_form("ani")
    connection.execute(
        "INSERT INTO piece_lexicon VALUES (?, ?)", (active.key, 3.25)
    )
    scorer = PieceStoreScorer(
        connection,
        alpha=0.1,
        complexity_weight=0.5,
        complexity_kappa=1.0,
        complexity_beta=0.25,
        complexity_tau=1.0,
        base_stop_probability=0.5,
        cache_size=8,
        telemetry=RuntimeTelemetry(),
    )

    for piece, count in ((active, 3.25), (parse_iast_form("api"), 0.0)):
        amplitude = scorer.complexity_weight * (
            scorer.complexity_kappa
            + scorer.complexity_beta * len(piece.symbols)
        )
        expected = math.log(max(scorer.probability(piece, count), 1e-300)) - (
            amplitude
            * math.log1p(1.0 / (scorer.complexity_tau + count))
        )
        assert scorer.score(piece) == expected
        assert scorer._lookup(piece.key) == count
    assert scorer.sqlite_selects == 1


def test_shared_inspection_piece_reference_bound_falls_back() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi"))
    graph = build_lazy_candidate_graph(segment, grammar)
    topology = compile_composed_segment_topology(
        graph,
        ComposedPieceInference(
            _production_scorer(),
            model_config=PieceModelConfig(max_piece_length=3),
        ),
    )
    result = infer_composed_segment(
        graph,
        ComposedPieceInference(
            _production_scorer(),
            model_config=PieceModelConfig(max_piece_length=3),
            cache_config=ComposedCacheConfig(
                shared_top_k_piece_references=1,
            ),
            inspection_top_k=5,
        ),
        whitespace_merge_penalty=8.0,
        topology=topology,
    )

    assert result.top_analyses
    assert result.counters.shared_batch_fallbacks > 0
    assert result.counters.form_cache_misses > 0


def test_identity_only_outer_case_matches_materialized_oracle() -> None:
    grammar = StructuredSandhiGrammar(())
    segment = next(iter_observed_segments("rama"))
    lazy = build_lazy_candidate_graph(segment, grammar)
    materialized = materialize_lazy_candidate_graph(lazy)
    config = PieceModelConfig(max_piece_length=2)
    reference_model = PieceModel(config, scorer=_production_scorer())
    reference = infer_segment(
        materialized,
        reference_model,
        whitespace_merge_penalty=8.0,
    )
    composed = infer_composed_segment(
        lazy,
        ComposedPieceInference(_production_scorer(), model_config=config),
        whitespace_merge_penalty=8.0,
    )

    assert composed.log_partition == pytest.approx(reference.log_partition)
    assert composed.identity_mass == pytest.approx(1.0)
    assert composed.latent_mass == pytest.approx(0.0)


def test_m0_prime_distinctions_and_devanagari_phonology_are_composed_identically() -> None:
    devanagari = continuous_spacing(
        transliterate_iast_to_devanagari("rama iti rama uta maitra pautra"),
        "devanagari",
    ) + "धद्ह"
    m0_prime = transliterate_devanagari_to_m0_prime_iast(devanagari)
    m0_phonemes = parse_surface(devanagari, script="devanagari").phonemes
    prime_phonemes = parse_surface(m0_prime, script="iast_m0_prime").phonemes

    assert prime_phonemes == m0_phonemes
    assert Phoneme.AI in prime_phonemes
    assert any(
        prime_phonemes[index : index + 2] == (Phoneme.A, Phoneme.I)
        for index in range(len(prime_phonemes) - 1)
    )
    assert Phoneme.DH in prime_phonemes
    assert any(
        prime_phonemes[index : index + 2] == (Phoneme.D, Phoneme.H)
        for index in range(len(prime_phonemes) - 1)
    )

    grammar = StructuredSandhiGrammar(())
    config = PieceModelConfig(max_piece_length=3)
    results = []
    for written, script in (
        (m0_prime, "iast_m0_prime"),
        (devanagari, "devanagari"),
    ):
        segment = next(iter_observed_segments(written, script=script))
        graph = build_lazy_candidate_graph(segment, grammar)
        results.append(
            infer_composed_segment(
                graph,
                ComposedPieceInference(_production_scorer(), model_config=config),
                whitespace_merge_penalty=8.0,
            )
        )
    prime, deva = results
    assert prime.log_partition == pytest.approx(deva.log_partition, abs=1e-12)
    assert prime.lexical_expected_counts == pytest.approx(
        deva.lexical_expected_counts, abs=1e-12
    )
    assert prime.piece_expected_counts == pytest.approx(
        deva.piece_expected_counts, abs=1e-12
    )

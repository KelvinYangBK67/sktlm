from __future__ import annotations

import pytest

from sktlm.latent.candidates import CandidateBuildProfile
from sktlm.latent.frontend import iter_observed_segments, parse_surface
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.inference import infer_segment
from sktlm.latent.lazy_candidates import (
    build_lazy_candidate_graph,
    materialize_lazy_candidate_graph,
)
from sktlm.latent.phonology import Phoneme, PhonologicalForm, parse_iast_form
from sktlm.pieces import (
    BaseMeasurePieceScorer,
    ComposedCacheConfig,
    ComposedPieceInference,
    PieceModel,
    PieceModelConfig,
    build_piece_lattice,
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
    engine.evaluate_form(forms[-1])
    counters = engine.counter_snapshot()

    assert counters.form_cache_entries <= cache.form_entries
    assert counters.form_cache_estimated_bytes <= cache.form_bytes
    assert counters.piece_score_cache_entries <= cache.piece_score_entries
    assert counters.piece_score_cache_estimated_bytes <= cache.piece_score_bytes
    assert counters.form_cache_misses == 3
    assert counters.form_cache_hits == 1
    assert counters.form_cache_evictions >= 1
    assert counters.piece_score_cache_hits > 0
    assert counters.piece_score_cache_misses > 0
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
def test_lazy_composed_outer_matches_materialized_oracle(surface: str) -> None:
    _compare_outer(surface)


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

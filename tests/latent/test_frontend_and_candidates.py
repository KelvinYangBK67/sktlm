from __future__ import annotations

import pytest

from sktlm.latent.candidates import CandidateConfig, build_candidate_graph
from sktlm.latent.frontend import CueKind, iter_observed_segments, parse_iast_surface
from sktlm.latent.grammar import RealizationKind, StructuredSandhiGrammar
from sktlm.latent.inference import NeutralFormScorer, infer_segment
from sktlm.latent.phonology import parse_iast_form
from sktlm.latent.training import S1M2_MODEL, TrainingConfig


def test_iast_frontend_separates_phonology_from_observed_cues() -> None:
    parsed = parse_iast_surface("devo'pi ca |")

    assert tuple(cue.kind for cue in parsed.cues) == (
        CueKind.AVAGRAHA,
        CueKind.SPACE,
        CueKind.SPACE,
        CueKind.PUNCTUATION,
    )
    assert all(symbol.value not in {"#", "'", " "} for symbol in parsed.phonemes)


def test_frozen_boundary_notation_becomes_a_structural_atom() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()

    boundary_rules = [
        rule for rule in grammar.rules if rule.boundary_index is not None
    ]

    assert boundary_rules
    assert any(
        atom.kind == RealizationKind.BOUNDARY
        for rule in boundary_rules
        for atom in rule.surface
    )
    assert all(
        "#" not in symbol.value
        for rule in grammar.rules
        for symbol in rule.left.symbols + rule.right.symbols
    )


def test_devo_pi_uses_complete_lexical_units_and_exact_fixed_rule() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("devo'pi"))
    graph = build_candidate_graph(segment, grammar)
    inference = infer_segment(
        graph,
        NeutralFormScorer(),
        whitespace_merge_penalty=4.0,
        top_k=64,
    )
    target = (parse_iast_form("devaḥ"), parse_iast_form("api"))

    assert any(analysis.words == target for analysis in inference.top_analyses)
    assert all(
        edge.word.symbols
        for factor in graph.factors
        if factor.lattice is not None
        for edge in factor.lattice.edges
    )
    target_analysis = next(
        analysis for analysis in inference.top_analyses if analysis.words == target
    )
    assert "EXT_0805" in target_analysis.rule_ids
    assert any(boundary.cue_kind == "avagraha" for boundary in target_analysis.boundaries)


def test_observed_whitespace_is_a_hard_lexical_fence() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("api ca"))
    graph = build_candidate_graph(
        segment,
        grammar,
        CandidateConfig(allow_whitespace_merge=False),
    )

    assert not any(factor.is_merge for factor in graph.factors)
    assert any(
        factor.end_token == 1
        for factor in graph.factors
        if not factor.is_merge
    )
    assert TrainingConfig().payload()["allow_whitespace_merge"] is True
    assert TrainingConfig(model=S1M2_MODEL).allow_whitespace_merge is False
    with pytest.raises(ValueError, match="forbids lexical factors"):
        TrainingConfig(model=S1M2_MODEL, allow_whitespace_merge=True)


def test_short_token_between_visible_fences_keeps_direct_complete_path() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("rāja n dha"))
    graph = build_candidate_graph(
        segment,
        grammar,
        CandidateConfig(allow_whitespace_merge=False),
    )

    assert all(
        any(
            option.direct
            and option.left_consumed == 0
            and option.right_consumed == 0
            for option in graph.boundary_options[boundary_index]
        )
        for boundary_index in (1, 2)
    )
    assert all(
        any(option.rule_ids for option in graph.boundary_options[boundary_index])
        for boundary_index in (1, 2)
    )
    inference = infer_segment(
        graph,
        NeutralFormScorer(),
        whitespace_merge_penalty=8.0,
    )

    assert inference.identity_mass + inference.latent_mass == pytest.approx(1.0)
    assert not any(factor.is_merge for factor in graph.factors)


def test_written_space_can_split_a_joined_grammar_realization() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("namo 'tharvavedāya"))
    graph = build_candidate_graph(segment, grammar)

    assert any(
        option.rule_ids
        and option.left_underlying == parse_iast_form("aḥ").symbols
        and option.right_underlying == parse_iast_form("a").symbols
        for option in graph.boundary_options[1]
    )


def test_joined_ve_keeps_internal_uu_e_inverse_candidate() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("ve"))
    graph = build_candidate_graph(segment, grammar)
    inference = infer_segment(
        graph,
        NeutralFormScorer(),
        whitespace_merge_penalty=8.0,
        top_k=64,
    )

    assert any(
        analysis.words == (parse_iast_form("ū"), parse_iast_form("e"))
        for analysis in inference.top_analyses
    )


def test_visible_fence_can_split_joined_ve_realization() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("svayaṃbhv ekam"))
    graph = build_candidate_graph(segment, grammar)
    target_rule = "EXT_0219"

    option = next(
        option
        for option in graph.boundary_options[1]
        if target_rule in option.rule_ids
        and option.left_underlying == parse_iast_form("ū").symbols
        and option.right_underlying == parse_iast_form("e").symbols
    )
    assert option.left_consumed == 1
    assert option.right_consumed == 1
    assert any(
        factor.start_token == 0
        and factor.outgoing == option
        and factor.lattice is not None
        and any(
            edge.start == 0
            and edge.end == len(factor.lattice.nodes) - 1
            and edge.word == parse_iast_form("svayaṃbhū")
            for edge in factor.lattice.edges
        )
        for factor in graph.factors
    )
    assert any(
        factor.start_token == 1
        and factor.incoming == option
        and factor.lattice is not None
        and any(
            edge.start == 0
            and edge.end == len(factor.lattice.nodes) - 1
            and edge.word == parse_iast_form("ekam")
            for edge in factor.lattice.edges
        )
        for factor in graph.factors
    )

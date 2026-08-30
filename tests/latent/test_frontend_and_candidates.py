from __future__ import annotations

from sktlm.latent.candidates import build_candidate_graph
from sktlm.latent.frontend import CueKind, iter_observed_segments, parse_iast_surface
from sktlm.latent.grammar import RealizationKind, StructuredSandhiGrammar
from sktlm.latent.inference import NeutralFormScorer, infer_segment
from sktlm.latent.phonology import parse_iast_form


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


def test_whitespace_is_evidence_but_not_a_gold_boundary() -> None:
    grammar = StructuredSandhiGrammar.from_default_inventory()
    segment = next(iter_observed_segments("api ca"))
    graph = build_candidate_graph(segment, grammar)

    assert any(factor.is_merge for factor in graph.factors)
    assert any(
        factor.end_token == 1
        for factor in graph.factors
        if not factor.is_merge
    )


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

from __future__ import annotations

import pytest

from sktlm.sandhi.inverse import (
    analyze_external_surface,
    analyze_external_surface_pairs,
)
from sktlm.sandhi.rules import load_external_sandhi_rules


def test_devo_pi_contains_deva_visarga_plus_api_analysis() -> None:
    rules = load_external_sandhi_rules()

    candidates = analyze_external_surface(
        "devo'pi",
        rules=rules,
    )

    assert any(
        candidate.left_word == "devaḥ"
        and candidate.right_word == "api"
        and candidate.rule_surface == "o'"
        for candidate in candidates
    )


def test_devo_pi_preserves_surface_ambiguity() -> None:
    rules = load_external_sandhi_rules()

    pairs = analyze_external_surface_pairs(
        "devo'pi",
        rules=rules,
    )

    assert ("devaḥ", "api") in pairs
    assert ("devo", "api") in pairs


def test_surviving_boundary_can_be_inverted() -> None:
    rules = load_external_sandhi_rules()

    pairs = analyze_external_surface_pairs(
        "deva kim",
        rules=rules,
    )

    assert ("deva", "kim") in pairs


def test_custom_boundary_separator_can_be_inverted() -> None:
    rules = load_external_sandhi_rules()

    pairs = analyze_external_surface_pairs(
        "deva#kim",
        rules=rules,
        boundary_separator="#",
    )

    assert ("deva", "kim") in pairs


def test_candidate_records_surface_span() -> None:
    rules = load_external_sandhi_rules()

    candidates = analyze_external_surface(
        "devo'pi",
        rules=rules,
    )

    candidate = next(
        candidate
        for candidate in candidates
        if candidate.left_word == "devaḥ"
        and candidate.right_word == "api"
    )

    assert candidate.matched_surface == "o'"
    assert "devo'pi"[candidate.span_start:candidate.span_end] == "o'"


def test_candidate_preserves_rule_provenance() -> None:
    rules = load_external_sandhi_rules()

    candidates = analyze_external_surface(
        "devo'pi",
        rules=rules,
    )

    candidate = next(
        candidate
        for candidate in candidates
        if candidate.left_word == "devaḥ"
        and candidate.right_word == "api"
    )

    assert candidate.rule_id
    assert candidate.variant >= 1
    assert candidate.left_underlying == "aḥ"
    assert candidate.right_underlying == "a"
    assert candidate.rule_surface == "o'"


def test_pair_wrapper_deduplicates_identical_pairs() -> None:
    rules = load_external_sandhi_rules()

    pairs = analyze_external_surface_pairs(
        "devo'pi",
        rules=rules,
    )

    assert len(pairs) == len(set(pairs))


def test_no_match_returns_empty_tuple() -> None:
    rules = load_external_sandhi_rules()

    candidates = analyze_external_surface(
        "☃",
        rules=rules,
    )

    assert candidates == ()


def test_empty_surface_is_rejected() -> None:
    rules = load_external_sandhi_rules()

    with pytest.raises(
        ValueError,
        match="surface must be non-empty",
    ):
        analyze_external_surface(
            "",
            rules=rules,
        )

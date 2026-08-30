from __future__ import annotations

import pytest

from sktlm.sandhi.boundary import (
    realize_external_boundary,
    realize_external_boundary_surfaces,
)
from sktlm.sandhi.rules import load_external_sandhi_rules


def test_deva_visarga_plus_api_realizes_devo_pi() -> None:
    rules = load_external_sandhi_rules()

    surfaces = realize_external_boundary_surfaces(
        "devaḥ",
        "api",
        rules=rules,
    )

    assert "devo'pi" in surfaces


def test_surviving_boundary_is_rendered_as_space() -> None:
    rules = load_external_sandhi_rules()

    surfaces = realize_external_boundary_surfaces(
        "deva",
        "kim",
        rules=rules,
    )

    assert "deva kim" in surfaces


def test_boundary_separator_can_be_changed() -> None:
    rules = load_external_sandhi_rules()

    surfaces = realize_external_boundary_surfaces(
        "deva",
        "kim",
        rules=rules,
        boundary_separator="#",
    )

    assert "deva#kim" in surfaces


def test_longest_right_prefix_wins() -> None:
    rules = load_external_sandhi_rules()

    results = realize_external_boundary(
        "deva",
        "aindraḥ",
        rules=rules,
    )

    assert results
    assert all(result.right_match == "ai" for result in results)
    assert "devaindraḥ" in tuple(
        result.surface
        for result in results
    )


def test_longest_left_suffix_wins() -> None:
    rules = load_external_sandhi_rules()

    results = realize_external_boundary(
        "rājan",
        "asti",
        rules=rules,
    )

    assert results
    assert all(result.left_match == "an" for result in results)


def test_all_variants_at_longest_match_are_preserved() -> None:
    rules = load_external_sandhi_rules()

    pair_counts: dict[tuple[str, str], int] = {}
    for rule in rules:
        key = (rule.left, rule.right)
        pair_counts[key] = pair_counts.get(key, 0) + 1

    pair = next(
        pair
        for pair, count in pair_counts.items()
        if count > 1
    )

    left, right = pair

    results = realize_external_boundary(
        left,
        right,
        rules=rules,
        boundary_separator="#",
    )

    assert len(results) == pair_counts[pair]
    assert all(result.left_match == left for result in results)
    assert all(result.right_match == right for result in results)


def test_rule_provenance_is_preserved() -> None:
    rules = load_external_sandhi_rules()

    results = realize_external_boundary(
        "devaḥ",
        "api",
        rules=rules,
    )

    assert results

    result = next(
        item
        for item in results
        if item.rule_surface == "o'"
    )

    assert result.rule_id
    assert result.variant >= 1
    assert result.left_match == "aḥ"
    assert result.right_match == "a"


def test_unknown_boundary_returns_empty_tuple() -> None:
    rules = load_external_sandhi_rules()

    results = realize_external_boundary(
        "__LEFT__",
        "__RIGHT__",
        rules=rules,
    )

    assert results == ()


def test_surface_wrapper_matches_full_results() -> None:
    rules = load_external_sandhi_rules()

    full = realize_external_boundary(
        "devaḥ",
        "api",
        rules=rules,
    )

    surfaces = realize_external_boundary_surfaces(
        "devaḥ",
        "api",
        rules=rules,
    )

    assert surfaces == tuple(
        result.surface
        for result in full
    )


def test_empty_left_word_is_rejected() -> None:
    rules = load_external_sandhi_rules()

    with pytest.raises(
        ValueError,
        match="left_word must be non-empty",
    ):
        realize_external_boundary(
            "",
            "api",
            rules=rules,
        )


def test_empty_right_word_is_rejected() -> None:
    rules = load_external_sandhi_rules()

    with pytest.raises(
        ValueError,
        match="right_word must be non-empty",
    ):
        realize_external_boundary(
            "devaḥ",
            "",
            rules=rules,
        )

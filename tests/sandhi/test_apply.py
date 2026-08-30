from __future__ import annotations

from sktlm.sandhi.apply import (
    apply_external_sandhi,
    apply_external_sandhi_surfaces,
)
from sktlm.sandhi.rules import load_external_sandhi_rules


def test_apply_returns_results_for_existing_rule() -> None:
    rules = load_external_sandhi_rules()
    first = rules[0]

    results = apply_external_sandhi(
        first.left,
        first.right,
        rules=rules,
    )

    assert results
    assert all(result.left == first.left for result in results)
    assert all(result.right == first.right for result in results)


def test_apply_returns_all_variants() -> None:
    rules = load_external_sandhi_rules()

    counts: dict[tuple[str, str], int] = {}

    for rule in rules:
        key = (rule.left, rule.right)
        counts[key] = counts.get(key, 0) + 1

    pair = next(
        pair
        for pair, count in counts.items()
        if count > 1
    )

    results = apply_external_sandhi(
        *pair,
        rules=rules,
    )

    assert len(results) == counts[pair]


def test_surface_wrapper_matches_full_results() -> None:
    rules = load_external_sandhi_rules()
    first = rules[0]

    full = apply_external_sandhi(
        first.left,
        first.right,
        rules=rules,
    )

    surfaces = apply_external_sandhi_surfaces(
        first.left,
        first.right,
        rules=rules,
    )

    assert surfaces == tuple(
        result.surface
        for result in full
    )


def test_unknown_pair_returns_empty_tuple() -> None:
    rules = load_external_sandhi_rules()

    results = apply_external_sandhi(
        "__NO_LEFT__",
        "__NO_RIGHT__",
        rules=rules,
    )

    assert results == ()


def test_application_preserves_rule_provenance() -> None:
    rules = load_external_sandhi_rules()
    first = rules[0]

    results = apply_external_sandhi(
        first.left,
        first.right,
        rules=rules,
    )

    matching = next(
        result
        for result in results
        if result.rule_id == first.rule_id
    )

    assert matching.surface == first.surface
    assert matching.variant == first.variant
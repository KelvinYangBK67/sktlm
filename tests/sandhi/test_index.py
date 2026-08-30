from __future__ import annotations

from sktlm.sandhi.index import (
    SandhiRuleIndex,
    get_default_rule_index,
)
from sktlm.sandhi.rules import load_external_sandhi_rules


def test_pair_lookup_matches_inventory() -> None:
    rules = load_external_sandhi_rules()
    index = SandhiRuleIndex(rules)
    first = rules[0]

    expected = tuple(
        r for r in rules
        if r.left == first.left and r.right == first.right
    )

    assert index.lookup_pair(first.left, first.right) == expected


def test_boundary_index_uses_longest_match() -> None:
    index = get_default_rule_index()

    results = index.match_boundary(
        "devaḥ",
        "api",
    )

    assert results
    max_span = max(len(r.left) + len(r.right) for r in results)

    assert all(
        len(r.left) + len(r.right) == max_span
        for r in results
    )


def test_surface_trie_finds_devo_pi_rule() -> None:
    index = get_default_rule_index()

    matches = tuple(
        index.iter_surface_matches("devo'pi")
    )

    assert any(
        m.rendered_surface == "o'"
        and m.rule.left == "aḥ"
        and m.rule.right == "a"
        for m in matches
    )


def test_default_index_is_cached() -> None:
    assert get_default_rule_index() is get_default_rule_index()

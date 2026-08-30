from __future__ import annotations

import csv

import pytest

from sktlm.sandhi.rules import (
    DEFAULT_EXTERNAL_SANDHI_PATH,
    SandhiRule,
    load_external_sandhi_rules,
    lookup,
    lookup_surfaces,
    validate_rules,
)


RULE_PATH = DEFAULT_EXTERNAL_SANDHI_PATH


def test_external_sandhi_rule_file_exists() -> None:
    assert RULE_PATH.is_file(), f"Missing rule file: {RULE_PATH}"


def test_external_sandhi_inventory_loads() -> None:
    rules = load_external_sandhi_rules(RULE_PATH)
    assert rules


def test_external_sandhi_inventory_has_expected_size() -> None:
    rules = load_external_sandhi_rules(RULE_PATH)
    assert len(rules) == 1218


def test_rule_ids_are_unique() -> None:
    rules = load_external_sandhi_rules(RULE_PATH)

    ids = [rule.rule_id for rule in rules]

    assert len(ids) == len(set(ids))


def test_no_unexpanded_short_vowel_placeholder_remains() -> None:
    rules = load_external_sandhi_rules(RULE_PATH)

    for rule in rules:
        assert "V̆" not in rule.left
        assert "V̆" not in rule.right
        assert "V̆" not in rule.surface


def test_no_pipe_alternative_syntax_remains_in_surface() -> None:
    rules = load_external_sandhi_rules(RULE_PATH)

    for rule in rules:
        assert "|" not in rule.surface


def test_lookup_returns_all_variants_for_pair() -> None:
    rules = load_external_sandhi_rules(RULE_PATH)

    counts: dict[tuple[str, str], int] = {}

    for rule in rules:
        key = (rule.left, rule.right)
        counts[key] = counts.get(key, 0) + 1

    multi = next(
        (pair for pair, count in counts.items() if count > 1),
        None,
    )

    assert multi is not None, (
        "Expected at least one left/right pair with multiple variants."
    )

    found = lookup(rules, *multi)

    assert len(found) == counts[multi]
    assert all(rule.left == multi[0] for rule in found)
    assert all(rule.right == multi[1] for rule in found)


def test_lookup_surfaces_matches_lookup() -> None:
    rules = load_external_sandhi_rules(RULE_PATH)

    first = rules[0]

    expected = tuple(
        rule.surface
        for rule in lookup(rules, first.left, first.right)
    )

    assert lookup_surfaces(
        rules,
        first.left,
        first.right,
    ) == expected


def test_validator_rejects_duplicate_rule_id() -> None:
    rules = (
        SandhiRule(
            rule_id="EXT_TEST",
            left="a",
            right="i",
            surface="e",
            variant=1,
            status="active",
        ),
        SandhiRule(
            rule_id="EXT_TEST",
            left="a",
            right="u",
            surface="o",
            variant=1,
            status="active",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Duplicate rule_id",
    ):
        validate_rules(rules)


def test_validator_rejects_duplicate_transition() -> None:
    rules = (
        SandhiRule(
            rule_id="EXT_TEST_1",
            left="a",
            right="i",
            surface="e",
            variant=1,
            status="active",
        ),
        SandhiRule(
            rule_id="EXT_TEST_2",
            left="a",
            right="i",
            surface="e",
            variant=2,
            status="active",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Duplicate left/right/surface transition",
    ):
        validate_rules(rules)


def test_validator_rejects_unexpanded_placeholder() -> None:
    rules = (
        SandhiRule(
            rule_id="EXT_TEST",
            left="V̆n",
            right="a",
            surface="V̆ṇa",
            variant=1,
            status="active",
        ),
    )

    with pytest.raises(
        ValueError,
        match="unexpanded V̆ placeholder",
    ):
        validate_rules(rules)


def test_tsv_header_is_exactly_supported_schema() -> None:
    with RULE_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.reader(
            handle,
            delimiter="\t",
        )
        header = next(reader)

    assert header == [
        "rule_id",
        "left",
        "right",
        "surface",
        "variant",
        "status",
    ]
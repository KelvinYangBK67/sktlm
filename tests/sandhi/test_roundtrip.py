from __future__ import annotations

from sktlm.sandhi.boundary import (
    realize_external_boundary,
)
from sktlm.sandhi.inverse import (
    analyze_external_surface,
)
from sktlm.sandhi.rules import (
    SandhiRule,
    load_external_sandhi_rules,
)


def _forward_for_rule(
    rule: SandhiRule,
    *,
    left_prefix: str = "",
    right_suffix: str = "",
):
    """
    Forward-realize one tracked rule inside optional untouched context.

    The exact rule pair is used as the word boundary material so that
    longest-match selection cannot prefer a longer competing rule.
    """
    left_word = left_prefix + rule.left
    right_word = rule.right + right_suffix

    results = realize_external_boundary(
        left_word,
        right_word,
    )

    return left_word, right_word, results


def test_every_tracked_rule_is_forward_reachable() -> None:
    rules = load_external_sandhi_rules()

    for rule in rules:
        left_word, right_word, results = _forward_for_rule(rule)

        assert any(
            result.rule_id == rule.rule_id
            for result in results
        ), (
            f"{rule.rule_id} is not forward reachable: "
            f"{left_word!r} + {right_word!r} "
            f"-> expected rule surface {rule.surface!r}"
        )


def test_every_tracked_rule_round_trips_to_original_pair() -> None:
    rules = load_external_sandhi_rules()

    for rule in rules:
        left_word, right_word, results = _forward_for_rule(rule)

        forward = next(
            result
            for result in results
            if result.rule_id == rule.rule_id
        )

        inverse = analyze_external_surface(
            forward.surface,
        )

        assert any(
            candidate.left_word == left_word
            and candidate.right_word == right_word
            and candidate.rule_id == rule.rule_id
            for candidate in inverse
        ), (
            f"{rule.rule_id} failed round trip: "
            f"{left_word!r} + {right_word!r} "
            f"-> {forward.surface!r} "
            f"-> original pair/rule not recovered"
        )


def test_every_tracked_rule_round_trips_with_untouched_context() -> None:
    rules = load_external_sandhi_rules()

    left_prefix = "x"
    right_suffix = "y"

    for rule in rules:
        left_word, right_word, results = _forward_for_rule(
            rule,
            left_prefix=left_prefix,
            right_suffix=right_suffix,
        )

        forward = next(
            result
            for result in results
            if result.rule_id == rule.rule_id
        )

        inverse = analyze_external_surface(
            forward.surface,
        )

        assert any(
            candidate.left_word == left_word
            and candidate.right_word == right_word
            and candidate.rule_id == rule.rule_id
            for candidate in inverse
        ), (
            f"{rule.rule_id} failed contextual round trip: "
            f"{left_word!r} + {right_word!r} "
            f"-> {forward.surface!r}"
        )


def test_devo_pi_round_trip_recovers_deva_visarga_api() -> None:
    forward = realize_external_boundary(
        "devaḥ",
        "api",
    )

    devo_pi = next(
        result
        for result in forward
        if result.surface == "devo'pi"
    )

    inverse = analyze_external_surface(
        devo_pi.surface,
    )

    assert any(
        candidate.left_word == "devaḥ"
        and candidate.right_word == "api"
        for candidate in inverse
    )


def test_round_trip_does_not_require_unique_inverse() -> None:
    forward = realize_external_boundary(
        "devaḥ",
        "api",
    )

    devo_pi = next(
        result
        for result in forward
        if result.surface == "devo'pi"
    )

    inverse = analyze_external_surface(
        devo_pi.surface,
    )

    # The contract is recoverability, not uniqueness.
    assert len(inverse) >= 1
    assert any(
        candidate.left_word == "devaḥ"
        and candidate.right_word == "api"
        for candidate in inverse
    )

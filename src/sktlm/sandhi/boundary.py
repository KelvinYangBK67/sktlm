from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sktlm.sandhi.index import (
    SandhiRuleIndex,
    get_default_rule_index,
)
from sktlm.sandhi.rules import SandhiRule


@dataclass(frozen=True, slots=True)
class BoundaryRealization:
    left_word: str
    right_word: str
    left_match: str
    right_match: str
    rule_surface: str
    surface: str
    rule_id: str
    variant: int


def realize_external_boundary(
    left_word: str,
    right_word: str,
    *,
    rules: Iterable[SandhiRule] | None = None,
    index: SandhiRuleIndex | None = None,
    boundary_separator: str = " ",
) -> tuple[BoundaryRealization, ...]:
    """
    Realize one external-sandhi boundary between two complete IAST words.

    '#' in rule.surface is rendered as boundary_separator.

    All variants at the longest applicable boundary match are preserved.

    `rules` and `index` are mutually exclusive. With neither supplied,
    the cached default rule index is used.
    """
    if not left_word:
        raise ValueError("left_word must be non-empty.")
    if not right_word:
        raise ValueError("right_word must be non-empty.")

    if rules is not None and index is not None:
        raise ValueError("Pass either rules or index, not both.")

    if index is None:
        if rules is None:
            index = get_default_rule_index(
                boundary_separator,
            )
        else:
            index = SandhiRuleIndex(
                rules,
                boundary_separator=boundary_separator,
            )

    matched = index.match_boundary(
        left_word,
        right_word,
    )

    realizations: list[BoundaryRealization] = []

    for rule in matched:
        left_stem = left_word[:-len(rule.left)]
        right_rest = right_word[len(rule.right):]

        rendered_rule_surface = rule.surface.replace(
            "#",
            boundary_separator,
        )

        realizations.append(
            BoundaryRealization(
                left_word=left_word,
                right_word=right_word,
                left_match=rule.left,
                right_match=rule.right,
                rule_surface=rule.surface,
                surface=(
                    left_stem
                    + rendered_rule_surface
                    + right_rest
                ),
                rule_id=rule.rule_id,
                variant=rule.variant,
            )
        )

    return tuple(realizations)


def realize_external_boundary_surfaces(
    left_word: str,
    right_word: str,
    *,
    rules: Iterable[SandhiRule] | None = None,
    index: SandhiRuleIndex | None = None,
    boundary_separator: str = " ",
) -> tuple[str, ...]:
    return tuple(
        result.surface
        for result in realize_external_boundary(
            left_word,
            right_word,
            rules=rules,
            index=index,
            boundary_separator=boundary_separator,
        )
    )

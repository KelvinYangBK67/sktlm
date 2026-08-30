from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sktlm.sandhi.index import (
    SandhiRuleIndex,
    get_default_rule_index,
)
from sktlm.sandhi.rules import SandhiRule


@dataclass(frozen=True, slots=True)
class InverseBoundaryCandidate:
    surface: str
    span_start: int
    span_end: int
    matched_surface: str
    left_word: str
    right_word: str
    left_underlying: str
    right_underlying: str
    rule_surface: str
    rule_id: str
    variant: int


def analyze_external_surface(
    surface: str,
    *,
    rules: Iterable[SandhiRule] | None = None,
    index: SandhiRuleIndex | None = None,
    boundary_separator: str = " ",
) -> tuple[InverseBoundaryCandidate, ...]:
    """
    Enumerate all one-boundary inverse analyses licensed by the rule inventory.

    No candidate is ranked or selected.
    """
    if not surface:
        raise ValueError("surface must be non-empty.")

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

    candidates: list[InverseBoundaryCandidate] = []

    for match in index.iter_surface_matches(surface):
        rule = match.rule

        candidates.append(
            InverseBoundaryCandidate(
                surface=surface,
                span_start=match.start,
                span_end=match.end,
                matched_surface=match.rendered_surface,
                left_word=surface[:match.start] + rule.left,
                right_word=rule.right + surface[match.end:],
                left_underlying=rule.left,
                right_underlying=rule.right,
                rule_surface=rule.surface,
                rule_id=rule.rule_id,
                variant=rule.variant,
            )
        )

    return tuple(candidates)


def analyze_external_surface_pairs(
    surface: str,
    *,
    rules: Iterable[SandhiRule] | None = None,
    index: SandhiRuleIndex | None = None,
    boundary_separator: str = " ",
) -> tuple[tuple[str, str], ...]:
    candidates = analyze_external_surface(
        surface,
        rules=rules,
        index=index,
        boundary_separator=boundary_separator,
    )

    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []

    for candidate in candidates:
        pair = (
            candidate.left_word,
            candidate.right_word,
        )

        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)

    return tuple(pairs)

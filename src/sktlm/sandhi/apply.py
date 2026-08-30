from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sktlm.sandhi.rules import (
    SandhiRule,
    load_external_sandhi_rules,
    lookup,
)


@dataclass(frozen=True, slots=True)
class SandhiApplication:
    left: str
    right: str
    surface: str
    rule_id: str
    variant: int


def apply_external_sandhi(
    left: str,
    right: str,
    *,
    rules: Iterable[SandhiRule] | None = None,
) -> tuple[SandhiApplication, ...]:
    """
    Apply the tracked external-sandhi inventory to one literal
    left/right boundary pair.

    Returns every licensed surface realization.

    This function performs only rule lookup. It does not:
    - segment words,
    - infer boundaries,
    - apply rules inside longer strings,
    - rank variants,
    - perform inverse analysis.
    """
    if rules is None:
        rules = load_external_sandhi_rules()

    matched = lookup(rules, left, right)

    return tuple(
        SandhiApplication(
            left=rule.left,
            right=rule.right,
            surface=rule.surface,
            rule_id=rule.rule_id,
            variant=rule.variant,
        )
        for rule in matched
    )


def apply_external_sandhi_surfaces(
    left: str,
    right: str,
    *,
    rules: Iterable[SandhiRule] | None = None,
) -> tuple[str, ...]:
    """
    Convenience wrapper returning only surface strings.
    """
    return tuple(
        result.surface
        for result in apply_external_sandhi(
            left,
            right,
            rules=rules,
        )
    )
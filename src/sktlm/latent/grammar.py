"""Structured runtime adapter for the frozen external-sandhi TSV."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Iterator

from sktlm.latent.frontend import SurfaceUnit
from sktlm.latent.phonology import (
    Phoneme,
    PhonologicalForm,
    match_iast_phoneme,
    normalize_iast,
    parse_iast_form,
)
from sktlm.sandhi.rules import SandhiRule, load_external_sandhi_rules


class RealizationKind(str, Enum):
    PHONEME = "phoneme"
    BOUNDARY = "lexical_boundary"
    AVAGRAHA = "avagraha"


@dataclass(frozen=True, slots=True)
class RealizationAtom:
    kind: RealizationKind
    phoneme: Phoneme | None = None

    @property
    def match_key(self) -> tuple[str, str]:
        return (self.kind.value, self.phoneme.value if self.phoneme else "")


@dataclass(frozen=True, slots=True)
class StructuredSandhiRule:
    rule_id: str
    left: PhonologicalForm
    right: PhonologicalForm
    surface: tuple[RealizationAtom, ...]
    variant: int

    @property
    def boundary_index(self) -> int | None:
        positions = [
            index
            for index, atom in enumerate(self.surface)
            if atom.kind == RealizationKind.BOUNDARY
        ]
        if not positions:
            return None
        if len(positions) != 1:
            raise ValueError(f"{self.rule_id}: expected at most one boundary marker")
        return positions[0]


@dataclass(frozen=True, slots=True)
class InternalRuleMatch:
    start: int
    end: int
    left_underlying: PhonologicalForm
    right_underlying: PhonologicalForm
    rule_ids: tuple[str, ...]
    variants: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BoundaryRuleMatch:
    left_consumed: int
    right_consumed: int
    left_underlying: PhonologicalForm
    right_underlying: PhonologicalForm
    rule_ids: tuple[str, ...]
    variants: tuple[int, ...]
    transformed: bool


@dataclass(slots=True)
class _TrieNode:
    children: dict[tuple[str, str], "_TrieNode"] = field(default_factory=dict)
    rules: list[StructuredSandhiRule] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _BoundaryRendering:
    rule: StructuredSandhiRule
    left_surface: tuple[RealizationAtom, ...]
    right_surface: tuple[RealizationAtom, ...]


def _parse_surface(text: str) -> tuple[RealizationAtom, ...]:
    normalized = normalize_iast(text)
    atoms: list[RealizationAtom] = []
    position = 0
    while position < len(normalized):
        character = normalized[position]
        if character == "#":
            atoms.append(RealizationAtom(RealizationKind.BOUNDARY))
            position += 1
        elif character in {"'", "’", "ʼ"}:
            atoms.append(RealizationAtom(RealizationKind.AVAGRAHA))
            position += 1
        else:
            matched = match_iast_phoneme(normalized, position)
            if matched is None:
                raise ValueError(
                    f"Unsupported sandhi surface notation at offset {position}: {text!r}"
                )
            phoneme, position = matched
            atoms.append(RealizationAtom(RealizationKind.PHONEME, phoneme))
    return tuple(atoms)


def _unit_keys(units: Iterable[SurfaceUnit]) -> tuple[tuple[str, str], ...]:
    return tuple(unit.match_key for unit in units)


class StructuredSandhiGrammar:
    """Indexed, script-neutral view of the fixed external grammar."""

    def __init__(self, rules: Iterable[SandhiRule]) -> None:
        self.rules = tuple(
            StructuredSandhiRule(
                rule.rule_id,
                parse_iast_form(rule.left),
                parse_iast_form(rule.right),
                _parse_surface(rule.surface),
                rule.variant,
            )
            for rule in rules
        )
        self._rules_by_id = {rule.rule_id: rule for rule in self.rules}
        self._internal_root = _TrieNode()
        boundary_buckets: dict[
            tuple[tuple[str, str] | None, tuple[str, str] | None],
            list[_BoundaryRendering],
        ] = {}
        for rule in self.rules:
            boundary_index = rule.boundary_index
            if boundary_index is None:
                node = self._internal_root
                for atom in rule.surface:
                    node = node.children.setdefault(atom.match_key, _TrieNode())
                node.rules.append(rule)
                # In surface_word, an otherwise joined realization stays in
                # one orthographic token. The attested exception is optional
                # spacing immediately beside written avagraha, e.g. o' ->
                # "o '". This is an observable frontend constraint, not a
                # learned sandhi preference.
                splits = tuple(
                    split
                    for split in range(1, len(rule.surface))
                    if rule.surface[split - 1].kind == RealizationKind.AVAGRAHA
                    or rule.surface[split].kind == RealizationKind.AVAGRAHA
                )
            else:
                splits = (boundary_index,)
            for split in splits:
                if boundary_index is None:
                    left = rule.surface[:split]
                    right = rule.surface[split:]
                else:
                    left = rule.surface[:split]
                    right = rule.surface[split + 1 :]
                key = (
                    left[-1].match_key if left else None,
                    right[0].match_key if right else None,
                )
                boundary_buckets.setdefault(key, []).append(
                    _BoundaryRendering(rule, left, right)
                )
        self._boundary_buckets = {
            key: tuple(value) for key, value in boundary_buckets.items()
        }

    @classmethod
    def from_default_inventory(cls) -> "StructuredSandhiGrammar":
        return cls(load_external_sandhi_rules())

    def iter_internal_matches(
        self,
        units: tuple[SurfaceUnit, ...],
    ) -> Iterator[InternalRuleMatch]:
        keys = _unit_keys(units)
        grouped: dict[
            tuple[int, int, PhonologicalForm, PhonologicalForm],
            list[StructuredSandhiRule],
        ] = {}
        for start in range(len(keys)):
            node = self._internal_root
            position = start
            while position < len(keys):
                node = node.children.get(keys[position])
                if node is None:
                    break
                position += 1
                for rule in node.rules:
                    grouped.setdefault(
                        (start, position, rule.left, rule.right),
                        [],
                    ).append(rule)
        for (start, end, left, right), rules in sorted(
            grouped.items(),
            key=lambda item: (item[0][0], item[0][1], item[1][0].rule_id),
        ):
            match = InternalRuleMatch(
                start,
                end,
                left,
                right,
                tuple(rule.rule_id for rule in rules),
                tuple(rule.variant for rule in rules),
            )
            if self.reconstruct_internal(match) != keys[start:end]:
                raise RuntimeError("Structured inverse candidate failed exact reconstruction.")
            yield match

    def match_visible_boundary(
        self,
        left_units: tuple[SurfaceUnit, ...],
        right_units: tuple[SurfaceUnit, ...],
    ) -> tuple[BoundaryRuleMatch, ...]:
        left_keys = _unit_keys(left_units)
        right_keys = _unit_keys(right_units)
        last = left_keys[-1] if left_keys else None
        first = right_keys[0] if right_keys else None
        candidates: list[_BoundaryRendering] = []
        for key in ((last, first), (None, first), (last, None), (None, None)):
            candidates.extend(self._boundary_buckets.get(key, ()))
        grouped: dict[
            tuple[int, int, PhonologicalForm, PhonologicalForm, bool],
            list[StructuredSandhiRule],
        ] = {}
        for candidate in candidates:
            rule = candidate.rule
            left_surface = candidate.left_surface
            right_surface = candidate.right_surface
            left_pattern = tuple(atom.match_key for atom in left_surface)
            right_pattern = tuple(atom.match_key for atom in right_surface)
            if len(left_pattern) > len(left_keys) or len(right_pattern) > len(right_keys):
                continue
            if left_pattern and left_keys[-len(left_pattern) :] != left_pattern:
                continue
            if right_pattern and right_keys[: len(right_pattern)] != right_pattern:
                continue
            surface_left = tuple(
                atom.phoneme for atom in left_surface if atom.phoneme is not None
            )
            surface_right = tuple(
                atom.phoneme for atom in right_surface if atom.phoneme is not None
            )
            transformed = (
                surface_left != rule.left.symbols
                or surface_right != rule.right.symbols
                or any(
                    atom.kind == RealizationKind.AVAGRAHA
                    for atom in left_surface + right_surface
                )
            )
            grouped.setdefault(
                (
                    len(left_pattern),
                    len(right_pattern),
                    rule.left,
                    rule.right,
                    transformed,
                ),
                [],
            ).append(rule)
        matches = [
            BoundaryRuleMatch(
                key[0],
                key[1],
                key[2],
                key[3],
                tuple(rule.rule_id for rule in rules),
                tuple(rule.variant for rule in rules),
                key[4],
            )
            for key, rules in grouped.items()
        ]
        return tuple(
            sorted(
                matches,
                key=lambda item: (
                    item.left_consumed,
                    item.right_consumed,
                    item.rule_ids,
                ),
            )
        )

    def reconstruct_internal(
        self,
        match: InternalRuleMatch,
    ) -> tuple[tuple[str, str], ...]:
        """Forward-reconstruct the matched surface from its frozen rule."""

        rule = self._rules_by_id[match.rule_ids[0]]
        if rule.left != match.left_underlying or rule.right != match.right_underlying:
            raise ValueError("Inverse match does not agree with its structured rule.")
        return tuple(atom.match_key for atom in rule.surface)

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Iterator

from sktlm.sandhi.rules import (
    SandhiRule,
    load_external_sandhi_rules,
)


@dataclass(slots=True)
class _TrieNode:
    children: dict[str, "_TrieNode"] = field(default_factory=dict)
    rules: list[SandhiRule] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SurfaceMatch:
    start: int
    end: int
    rendered_surface: str
    rule: SandhiRule


class SandhiRuleIndex:
    """
    Search index for the tracked external-sandhi inventory.

    Supports:
    - direct underlying-pair lookup;
    - indexed suffix/prefix boundary matching;
    - trie-based surface matching for inverse analysis.
    """

    def __init__(
        self,
        rules: Iterable[SandhiRule],
        *,
        boundary_separator: str = " ",
    ) -> None:
        self.rules = tuple(rules)
        self.boundary_separator = boundary_separator

        pair_map: dict[tuple[str, str], list[SandhiRule]] = {}
        boundary_buckets: dict[tuple[str, str], list[SandhiRule]] = {}
        root = _TrieNode()

        for rule in self.rules:
            pair_map.setdefault(
                (rule.left, rule.right),
                [],
            ).append(rule)

            boundary_buckets.setdefault(
                (rule.left[-1], rule.right[0]),
                [],
            ).append(rule)

            rendered = rule.surface.replace(
                "#",
                boundary_separator,
            )

            if not rendered:
                continue

            node = root
            for char in rendered:
                node = node.children.setdefault(
                    char,
                    _TrieNode(),
                )
            node.rules.append(rule)

        self._pair_map = {
            key: tuple(value)
            for key, value in pair_map.items()
        }
        self._boundary_buckets = {
            key: tuple(value)
            for key, value in boundary_buckets.items()
        }
        self._surface_root = root

    def lookup_pair(
        self,
        left: str,
        right: str,
    ) -> tuple[SandhiRule, ...]:
        return self._pair_map.get(
            (left, right),
            (),
        )

    def match_boundary(
        self,
        left_word: str,
        right_word: str,
    ) -> tuple[SandhiRule, ...]:
        """
        Return the most specific rules matching one complete word boundary.

        Specificity is total matched span length:
            len(rule.left) + len(rule.right)

        All variants tied at the maximal span are preserved.
        """
        if not left_word or not right_word:
            return ()

        bucket = self._boundary_buckets.get(
            (left_word[-1], right_word[0]),
            (),
        )

        matches = tuple(
            rule
            for rule in bucket
            if left_word.endswith(rule.left)
            and right_word.startswith(rule.right)
        )

        if not matches:
            return ()

        max_span = max(
            len(rule.left) + len(rule.right)
            for rule in matches
        )

        return tuple(
            rule
            for rule in matches
            if len(rule.left) + len(rule.right) == max_span
        )

    def iter_surface_matches(
        self,
        text: str,
    ) -> Iterator[SurfaceMatch]:
        """
        Yield every tracked rule-surface match in text.

        Overlapping matches are preserved.
        """
        for start in range(len(text)):
            node = self._surface_root
            pos = start

            while pos < len(text):
                node = node.children.get(text[pos])

                if node is None:
                    break

                pos += 1

                if node.rules:
                    rendered = text[start:pos]

                    for rule in node.rules:
                        yield SurfaceMatch(
                            start=start,
                            end=pos,
                            rendered_surface=rendered,
                            rule=rule,
                        )


@lru_cache(maxsize=None)
def get_default_rule_index(
    boundary_separator: str = " ",
) -> SandhiRuleIndex:
    """
    Build the default tracked rule index once per boundary separator.
    """
    return SandhiRuleIndex(
        load_external_sandhi_rules(),
        boundary_separator=boundary_separator,
    )

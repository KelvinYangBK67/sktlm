"""Compact lexical candidate graphs constrained by observable cues."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sktlm.latent.frontend import ObservedSegment, ObservedToken, SurfaceUnit
from sktlm.latent.grammar import (
    BoundaryRuleMatch,
    InternalRuleMatch,
    StructuredSandhiGrammar,
)
from sktlm.latent.phonology import Phoneme, PhonologicalForm


@dataclass(frozen=True, slots=True)
class LexicalBoundary:
    """A structural boundary hypothesis, never a literal text character."""

    boundary_id: str
    cue_kind: str
    source_start: int
    source_end: int


@dataclass(frozen=True, slots=True)
class BoundaryOption:
    key: str
    left_consumed: int
    right_consumed: int
    left_underlying: tuple[Phoneme, ...]
    right_underlying: tuple[Phoneme, ...]
    rule_ids: tuple[str, ...]
    transformed: bool
    direct: bool = False


@dataclass(frozen=True, slots=True)
class InternalBoundaryNode:
    surface_start: int
    surface_end: int
    left_underlying: tuple[Phoneme, ...]
    right_underlying: tuple[Phoneme, ...]
    rule_ids: tuple[str, ...]
    source_start: int
    source_end: int
    is_start: bool = False
    is_end: bool = False


@dataclass(frozen=True, slots=True)
class LexicalEdge:
    start: int
    end: int
    word: PhonologicalForm
    boundary: LexicalBoundary | None
    rule_ids: tuple[str, ...]
    identity_edge: bool


@dataclass(frozen=True, slots=True)
class TokenLattice:
    token: ObservedToken
    incoming: BoundaryOption
    outgoing: BoundaryOption
    nodes: tuple[InternalBoundaryNode, ...]
    edges: tuple[LexicalEdge, ...]
    overflowed: bool = False

    @property
    def outgoing_edges(self) -> tuple[tuple[LexicalEdge, ...], ...]:
        grouped: list[list[LexicalEdge]] = [[] for _ in self.nodes]
        for edge in self.edges:
            grouped[edge.start].append(edge)
        return tuple(tuple(items) for items in grouped)

    @property
    def incoming_edges(self) -> tuple[tuple[LexicalEdge, ...], ...]:
        grouped: list[list[LexicalEdge]] = [[] for _ in self.nodes]
        for edge in self.edges:
            grouped[edge.end].append(edge)
        return tuple(tuple(items) for items in grouped)


@dataclass(frozen=True, slots=True)
class SegmentFactor:
    factor_id: str
    start_token: int
    end_token: int
    incoming: BoundaryOption
    outgoing: BoundaryOption
    lattice: TokenLattice | None
    merged_word: PhonologicalForm | None
    ignored_whitespace: int

    @property
    def is_merge(self) -> bool:
        return self.merged_word is not None


@dataclass(frozen=True, slots=True)
class CandidateGraph:
    segment: ObservedSegment
    boundary_options: tuple[tuple[BoundaryOption, ...], ...]
    factors: tuple[SegmentFactor, ...]
    overflowed_tokens: int


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    max_internal_matches: int = 512
    allow_whitespace_merge: bool = True
    whitespace_merge_penalty: float = 8.0

    def __post_init__(self) -> None:
        if self.max_internal_matches < 1:
            raise ValueError("max_internal_matches must be >= 1")
        if self.whitespace_merge_penalty < 0.0:
            raise ValueError("whitespace_merge_penalty must be >= 0")


def candidate_graph_statistics(graph: CandidateGraph) -> dict[str, int]:
    lattices = [
        factor.lattice for factor in graph.factors if factor.lattice is not None
    ]
    return {
        "boundary_options": sum(len(options) for options in graph.boundary_options),
        "factors": len(graph.factors),
        "merged_factors": sum(factor.is_merge for factor in graph.factors),
        "token_lattices": len(lattices),
        "lattice_nodes": sum(len(lattice.nodes) for lattice in lattices),
        "lexical_edges": sum(len(lattice.edges) for lattice in lattices),
        "overflowed_tokens": graph.overflowed_tokens,
    }


def candidate_graph_fingerprint(graph: CandidateGraph) -> str:
    """Hash every inference-relevant candidate field in deterministic order."""

    digest = hashlib.sha256()

    def add(*parts: object) -> None:
        for part in parts:
            digest.update(str(part).encode("utf-8"))
            digest.update(b"\0")

    add("segment", graph.segment.written, len(graph.segment.tokens))
    for options in graph.boundary_options:
        add("boundary-options", len(options))
        for option in options:
            add(
                option.key,
                option.left_consumed,
                option.right_consumed,
                ".".join(symbol.value for symbol in option.left_underlying),
                ".".join(symbol.value for symbol in option.right_underlying),
                ",".join(option.rule_ids),
                int(option.transformed),
                int(option.direct),
            )
    for factor in graph.factors:
        add(
            "factor",
            factor.factor_id,
            factor.start_token,
            factor.end_token,
            factor.incoming.key,
            factor.outgoing.key,
            factor.merged_word.key if factor.merged_word is not None else "",
            factor.ignored_whitespace,
        )
        if factor.lattice is None:
            continue
        for node in factor.lattice.nodes:
            add(
                "node",
                node.surface_start,
                node.surface_end,
                ".".join(symbol.value for symbol in node.left_underlying),
                ".".join(symbol.value for symbol in node.right_underlying),
                ",".join(node.rule_ids),
                node.source_start,
                node.source_end,
                int(node.is_start),
                int(node.is_end),
            )
        for edge in factor.lattice.edges:
            boundary = edge.boundary
            add(
                "edge",
                edge.start,
                edge.end,
                edge.word.key,
                ",".join(edge.rule_ids),
                int(edge.identity_edge),
                boundary.boundary_id if boundary is not None else "",
                boundary.cue_kind if boundary is not None else "",
                boundary.source_start if boundary is not None else "",
                boundary.source_end if boundary is not None else "",
            )
    return digest.hexdigest()


def _phonemes(units: tuple[SurfaceUnit, ...]) -> tuple[Phoneme, ...]:
    return tuple(unit.phoneme for unit in units if unit.phoneme is not None)


def _contains_avagraha(units: tuple[SurfaceUnit, ...]) -> bool:
    return any(unit.kind == "avagraha" for unit in units)


def _boundary_option_from_match(match: BoundaryRuleMatch) -> BoundaryOption:
    rule_part = ",".join(match.rule_ids)
    key = (
        f"grammar:{rule_part}:{match.left_consumed}:{match.right_consumed}:"
        f"{match.left_underlying.key}:{match.right_underlying.key}"
    )
    return BoundaryOption(
        key=key,
        left_consumed=match.left_consumed,
        right_consumed=match.right_consumed,
        left_underlying=match.left_underlying.symbols,
        right_underlying=match.right_underlying.symbols,
        rule_ids=match.rule_ids,
        transformed=match.transformed,
    )


def _visible_boundary_options(
    left: ObservedToken,
    right: ObservedToken,
    grammar: StructuredSandhiGrammar,
    boundary_index: int,
) -> tuple[BoundaryOption, ...]:
    matches = grammar.match_visible_boundary(left.units, right.units)
    if left.units and left.units[-1].kind == "avagraha":
        matches = tuple(match for match in matches if match.left_consumed > 0)
    if right.units and right.units[0].kind == "avagraha":
        matches = tuple(match for match in matches if match.right_consumed > 0)
    options = [_boundary_option_from_match(match) for match in matches]
    if not any(not match.transformed for match in matches):
        options.append(
            BoundaryOption(
                key=f"direct:{boundary_index}",
                left_consumed=0,
                right_consumed=0,
                left_underlying=(),
                right_underlying=(),
                rule_ids=(),
                transformed=False,
                direct=True,
            )
        )
    deduplicated = {option.key: option for option in options}
    return tuple(deduplicated[key] for key in sorted(deduplicated))


def _internal_nodes(
    token: ObservedToken,
    grammar: StructuredSandhiGrammar,
    incoming: BoundaryOption,
    outgoing: BoundaryOption,
    max_internal_matches: int,
) -> tuple[tuple[InternalBoundaryNode, ...], bool]:
    prefix_end = incoming.right_consumed
    suffix_start = len(token.units) - outgoing.left_consumed
    if prefix_end > suffix_start:
        return (), False
    matches = [
        match
        for match in grammar.iter_internal_matches(token.units)
        if match.start >= prefix_end and match.end <= suffix_start
    ]
    overflowed = len(matches) > max_internal_matches
    if overflowed:
        matches = []
    start = InternalBoundaryNode(
        surface_start=prefix_end,
        surface_end=prefix_end,
        left_underlying=(),
        right_underlying=incoming.right_underlying,
        rule_ids=(),
        source_start=token.source_start,
        source_end=token.source_start,
        is_start=True,
    )
    end = InternalBoundaryNode(
        surface_start=suffix_start,
        surface_end=suffix_start,
        left_underlying=outgoing.left_underlying,
        right_underlying=(),
        rule_ids=(),
        source_start=token.source_end,
        source_end=token.source_end,
        is_end=True,
    )
    internal = [
        InternalBoundaryNode(
            surface_start=match.start,
            surface_end=match.end,
            left_underlying=match.left_underlying.symbols,
            right_underlying=match.right_underlying.symbols,
            rule_ids=match.rule_ids,
            source_start=token.units[match.start].source_start,
            source_end=token.units[match.end - 1].source_end,
        )
        for match in matches
    ]
    internal.sort(
        key=lambda node: (
            node.surface_start,
            node.surface_end,
            node.rule_ids,
        )
    )
    return (start, *internal, end), overflowed


def build_token_lattice(
    token: ObservedToken,
    grammar: StructuredSandhiGrammar,
    incoming: BoundaryOption,
    outgoing: BoundaryOption,
    *,
    max_internal_matches: int,
) -> TokenLattice | None:
    """Build a DAG whose edges emit complete lexical forms."""

    nodes, overflowed = _internal_nodes(
        token,
        grammar,
        incoming,
        outgoing,
        max_internal_matches,
    )
    if not nodes:
        return None
    edges: list[LexicalEdge] = []
    for left_index, left in enumerate(nodes[:-1]):
        for right_index in range(left_index + 1, len(nodes)):
            right = nodes[right_index]
            if left.surface_end > right.surface_start:
                continue
            gap = token.units[left.surface_end : right.surface_start]
            identity_edge = left.is_start and right.is_end
            if _contains_avagraha(gap) and not identity_edge:
                continue
            symbols = left.right_underlying + _phonemes(gap) + right.left_underlying
            if not symbols:
                continue
            word = PhonologicalForm(symbols)
            if not identity_edge and not word.has_vowel():
                continue
            boundary = None
            if not right.is_end:
                boundary = LexicalBoundary(
                    boundary_id=(
                        f"internal:{right.source_start}:{right.source_end}:"
                        f"{','.join(right.rule_ids)}"
                    ),
                    cue_kind=(
                        "avagraha"
                        if _contains_avagraha(
                            token.units[right.surface_start : right.surface_end]
                        )
                        else "unmarked"
                    ),
                    source_start=right.source_start,
                    source_end=right.source_end,
                )
            edges.append(
                LexicalEdge(
                    start=left_index,
                    end=right_index,
                    word=word,
                    boundary=boundary,
                    rule_ids=right.rule_ids if not right.is_end else (),
                    identity_edge=identity_edge,
                )
            )
    if not any(edge.start == 0 for edge in edges):
        return None
    return TokenLattice(
        token=token,
        incoming=incoming,
        outgoing=outgoing,
        nodes=nodes,
        edges=tuple(edges),
        overflowed=overflowed,
    )


def _merged_word(
    first: ObservedToken,
    second: ObservedToken,
    incoming: BoundaryOption,
    outgoing: BoundaryOption,
) -> PhonologicalForm | None:
    if first.has_avagraha or second.has_avagraha:
        return None
    first_start = incoming.right_consumed
    second_end = len(second.units) - outgoing.left_consumed
    if first_start > len(first.units) or second_end < 0:
        return None
    symbols = (
        incoming.right_underlying
        + _phonemes(first.units[first_start:])
        + _phonemes(second.units[:second_end])
        + outgoing.left_underlying
    )
    if not symbols:
        return None
    word = PhonologicalForm(symbols)
    return word if word.has_vowel() else None


def build_candidate_graph(
    segment: ObservedSegment,
    grammar: StructuredSandhiGrammar,
    config: CandidateConfig = CandidateConfig(),
) -> CandidateGraph:
    """Build a bounded line graph without enumerating complete analyses."""

    token_count = len(segment.tokens)
    if token_count == 0:
        raise ValueError("Cannot build a candidate graph for an empty segment.")
    start = BoundaryOption("START", 0, 0, (), (), (), False, True)
    end = BoundaryOption("END", 0, 0, (), (), (), False, True)
    boundaries: list[tuple[BoundaryOption, ...]] = [(start,)]
    for index in range(1, token_count):
        boundaries.append(
            _visible_boundary_options(
                segment.tokens[index - 1],
                segment.tokens[index],
                grammar,
                index,
            )
        )
    boundaries.append((end,))

    factors: list[SegmentFactor] = []
    overflowed_tokens: set[int] = set()
    for index, token in enumerate(segment.tokens):
        for incoming in boundaries[index]:
            for outgoing in boundaries[index + 1]:
                lattice = build_token_lattice(
                    token,
                    grammar,
                    incoming,
                    outgoing,
                    max_internal_matches=config.max_internal_matches,
                )
                if lattice is None:
                    continue
                if lattice.overflowed:
                    overflowed_tokens.add(index)
                factors.append(
                    SegmentFactor(
                        factor_id=f"token:{index}:{incoming.key}:{outgoing.key}",
                        start_token=index,
                        end_token=index + 1,
                        incoming=incoming,
                        outgoing=outgoing,
                        lattice=lattice,
                        merged_word=None,
                        ignored_whitespace=0,
                    )
                )
        if not config.allow_whitespace_merge or index + 1 >= token_count:
            continue
        for incoming in boundaries[index]:
            for outgoing in boundaries[index + 2]:
                word = _merged_word(
                    token,
                    segment.tokens[index + 1],
                    incoming,
                    outgoing,
                )
                if word is None:
                    continue
                factors.append(
                    SegmentFactor(
                        factor_id=f"merge:{index}:{incoming.key}:{outgoing.key}",
                        start_token=index,
                        end_token=index + 2,
                        incoming=incoming,
                        outgoing=outgoing,
                        lattice=None,
                        merged_word=word,
                        ignored_whitespace=1,
                    )
                )
    factors.sort(
        key=lambda factor: (
            factor.start_token,
            factor.end_token,
            factor.incoming.key,
            factor.outgoing.key,
            factor.factor_id,
        )
    )
    return CandidateGraph(
        segment=segment,
        boundary_options=tuple(boundaries),
        factors=tuple(factors),
        overflowed_tokens=len(overflowed_tokens),
    )

"""Lazy lexical-span candidates with exact M1 membership semantics.

The graph stores boundary options and internal nodes but no persistent
LexicalEdge(word) row for every node pair. Span words are reconstructed only
while an exact inference traversal requests them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from sktlm.latent.candidates import (
    BoundaryOption,
    CandidateConfig,
    CandidateGraph,
    InternalBoundaryNode,
    LexicalBoundary,
    LexicalEdge,
    SegmentFactor,
    TokenLattice,
    _contains_avagraha,
    _internal_nodes,
    _merged_word,
    _phonemes,
    _visible_boundary_options,
)
from sktlm.latent.frontend import ObservedSegment, ObservedToken
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.phonology import Phoneme, PhonologicalForm


@dataclass(frozen=True, slots=True)
class LazyLexicalSpan:
    """One transient legal span; its form is not stored in the graph."""

    start: int
    end: int
    symbols: tuple[Phoneme, ...]
    boundary: LexicalBoundary | None
    rule_ids: tuple[str, ...]
    identity_edge: bool

    @property
    def word(self) -> PhonologicalForm:
        return PhonologicalForm(self.symbols)

    def materialize(self) -> LexicalEdge:
        return LexicalEdge(
            start=self.start,
            end=self.end,
            word=self.word,
            boundary=self.boundary,
            rule_ids=self.rule_ids,
            identity_edge=self.identity_edge,
        )


@dataclass(frozen=True, slots=True)
class LazyTokenLattice:
    token: ObservedToken
    incoming: BoundaryOption
    outgoing: BoundaryOption
    nodes: tuple[InternalBoundaryNode, ...]
    overflowed: bool = False
    raw_internal_matches: int = 0
    retained_internal_matches: int = 0

    def span(self, left_index: int, right_index: int) -> LazyLexicalSpan | None:
        if not 0 <= left_index < right_index < len(self.nodes):
            raise IndexError("span endpoints must be ordered node indices")
        left, right = self.nodes[left_index], self.nodes[right_index]
        if left.surface_end > right.surface_start:
            return None
        gap = self.token.units[left.surface_end : right.surface_start]
        identity_edge = left.is_start and right.is_end
        if _contains_avagraha(gap) and not identity_edge:
            return None
        symbols = left.right_underlying + _phonemes(gap) + right.left_underlying
        if not symbols:
            return None
        word = PhonologicalForm(symbols)
        if not identity_edge and not word.has_vowel():
            return None
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
                        self.token.units[
                            right.surface_start : right.surface_end
                        ]
                    )
                    else "unmarked"
                ),
                source_start=right.source_start,
                source_end=right.source_end,
            )
        return LazyLexicalSpan(
            start=left_index,
            end=right_index,
            symbols=symbols,
            boundary=boundary,
            rule_ids=right.rule_ids if not right.is_end else (),
            identity_edge=identity_edge,
        )

    def iter_spans_from(self, left_index: int) -> Iterator[LazyLexicalSpan]:
        if not 0 <= left_index < len(self.nodes) - 1:
            return
        for right_index in range(left_index + 1, len(self.nodes)):
            span = self.span(left_index, right_index)
            if span is not None:
                yield span

    def iter_spans(self) -> Iterator[LazyLexicalSpan]:
        for left_index in range(len(self.nodes) - 1):
            yield from self.iter_spans_from(left_index)


@dataclass(frozen=True, slots=True)
class LazySegmentFactor:
    factor_id: str
    start_token: int
    end_token: int
    incoming: BoundaryOption
    outgoing: BoundaryOption
    lattice: LazyTokenLattice | None
    merged_word: PhonologicalForm | None
    ignored_whitespace: int

    @property
    def is_merge(self) -> bool:
        return self.merged_word is not None


@dataclass(frozen=True, slots=True)
class LazyCandidateGraph:
    segment: ObservedSegment
    boundary_options: tuple[tuple[BoundaryOption, ...], ...]
    factors: tuple[LazySegmentFactor, ...]
    overflowed_tokens: int


def build_lazy_token_lattice(
    token: ObservedToken,
    grammar: StructuredSandhiGrammar,
    incoming: BoundaryOption,
    outgoing: BoundaryOption,
    *,
    max_internal_matches: int,
) -> LazyTokenLattice | None:
    nodes, overflowed, raw_matches, retained_matches = _internal_nodes(
        token,
        grammar,
        incoming,
        outgoing,
        max_internal_matches,
    )
    if not nodes:
        return None
    lattice = LazyTokenLattice(
        token=token,
        incoming=incoming,
        outgoing=outgoing,
        nodes=nodes,
        overflowed=overflowed,
        raw_internal_matches=raw_matches,
        retained_internal_matches=retained_matches,
    )
    if next(lattice.iter_spans_from(0), None) is None:
        return None
    return lattice


def build_lazy_candidate_graph(
    segment: ObservedSegment,
    grammar: StructuredSandhiGrammar,
    config: CandidateConfig = CandidateConfig(),
) -> LazyCandidateGraph:
    """Build the production-only node graph without materialized lexical edges."""

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

    factors: list[LazySegmentFactor] = []
    overflowed_tokens: set[int] = set()
    for index, token in enumerate(segment.tokens):
        for incoming in boundaries[index]:
            for outgoing in boundaries[index + 1]:
                lattice = build_lazy_token_lattice(
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
                    LazySegmentFactor(
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
                    LazySegmentFactor(
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
    return LazyCandidateGraph(
        segment=segment,
        boundary_options=tuple(boundaries),
        factors=tuple(factors),
        overflowed_tokens=len(overflowed_tokens),
    )


def lazy_candidate_graph_statistics(graph: LazyCandidateGraph) -> dict[str, int]:
    lattices = [
        factor.lattice for factor in graph.factors if factor.lattice is not None
    ]
    return {
        "boundary_options": sum(len(options) for options in graph.boundary_options),
        "factors": len(graph.factors),
        "merged_factors": sum(factor.is_merge for factor in graph.factors),
        "token_lattices": len(lattices),
        "raw_internal_matches": sum(
            lattice.raw_internal_matches for lattice in lattices
        ),
        "retained_internal_matches": sum(
            lattice.retained_internal_matches for lattice in lattices
        ),
        "lattice_nodes": sum(len(lattice.nodes) for lattice in lattices),
        "lexical_span_hypotheses": sum(
            1 for lattice in lattices for _span in lattice.iter_spans()
        ),
        "overflowed_tokens": graph.overflowed_tokens,
    }


def materialize_lazy_candidate_graph(graph: LazyCandidateGraph) -> CandidateGraph:
    """Test/comparator adapter; production inference must not call this."""

    factors: list[SegmentFactor] = []
    for factor in graph.factors:
        lattice = factor.lattice
        materialized = None
        if lattice is not None:
            materialized = TokenLattice(
                token=lattice.token,
                incoming=lattice.incoming,
                outgoing=lattice.outgoing,
                nodes=lattice.nodes,
                edges=tuple(span.materialize() for span in lattice.iter_spans()),
                overflowed=lattice.overflowed,
                raw_internal_matches=lattice.raw_internal_matches,
                retained_internal_matches=lattice.retained_internal_matches,
            )
        factors.append(
            SegmentFactor(
                factor_id=factor.factor_id,
                start_token=factor.start_token,
                end_token=factor.end_token,
                incoming=factor.incoming,
                outgoing=factor.outgoing,
                lattice=materialized,
                merged_word=factor.merged_word,
                ignored_whitespace=factor.ignored_whitespace,
            )
        )
    return CandidateGraph(
        segment=graph.segment,
        boundary_options=graph.boundary_options,
        factors=tuple(factors),
        overflowed_tokens=graph.overflowed_tokens,
    )

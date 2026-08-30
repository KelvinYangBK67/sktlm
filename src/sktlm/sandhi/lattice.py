from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Literal

from sktlm.sandhi.index import (
    SandhiRuleIndex,
    get_default_rule_index,
)
from sktlm.sandhi.rules import SandhiRule


EdgeKind = Literal["identity", "sandhi"]


@dataclass(frozen=True, slots=True)
class LatticeEdge:
    """
    One edge in a surface-conditioned candidate lattice.

    start/end are character offsets in the observed surface string.

    identity edge:
        consumes one surface character and keeps it unchanged.

    sandhi edge:
        consumes one surface span licensed by a tracked external-sandhi rule
        and exposes that rule's underlying left/right material as a latent
        alternative.

    The lattice does not choose between edges.
    """
    start: int
    end: int
    kind: EdgeKind
    surface: str

    # Present only for sandhi edges.
    left_underlying: str | None = None
    right_underlying: str | None = None
    rule_surface: str | None = None
    rule_id: str | None = None
    variant: int | None = None

    @property
    def latent_pieces(self) -> tuple[str, ...]:
        """
        Return the latent material contributed by this edge.

        identity:
            (surface_char,)

        sandhi:
            (left_underlying, "#", right_underlying)

        '#' is an abstract lexical-boundary marker in the latent path.
        """
        if self.kind == "identity":
            return (self.surface,)

        assert self.left_underlying is not None
        assert self.right_underlying is not None

        return (
            self.left_underlying,
            "#",
            self.right_underlying,
        )


@dataclass(frozen=True, slots=True)
class CandidateLattice:
    """
    DAG over character offsets in one observed surface string.

    Nodes are offsets 0..len(surface).
    Edges always move from a smaller offset to a larger offset.
    """
    surface: str
    edges: tuple[LatticeEdge, ...]

    @property
    def num_nodes(self) -> int:
        return len(self.surface) + 1

    @property
    def num_edges(self) -> int:
        return len(self.edges)

    def outgoing(self, node: int) -> tuple[LatticeEdge, ...]:
        if node < 0 or node >= self.num_nodes:
            raise IndexError(
                f"node out of range: {node}; "
                f"valid range is 0..{self.num_nodes - 1}"
            )

        return tuple(
            edge
            for edge in self.edges
            if edge.start == node
        )

    def incoming(self, node: int) -> tuple[LatticeEdge, ...]:
        if node < 0 or node >= self.num_nodes:
            raise IndexError(
                f"node out of range: {node}; "
                f"valid range is 0..{self.num_nodes - 1}"
            )

        return tuple(
            edge
            for edge in self.edges
            if edge.end == node
        )

    def sandhi_edges(self) -> tuple[LatticeEdge, ...]:
        return tuple(
            edge
            for edge in self.edges
            if edge.kind == "sandhi"
        )

    def identity_edges(self) -> tuple[LatticeEdge, ...]:
        return tuple(
            edge
            for edge in self.edges
            if edge.kind == "identity"
        )


def build_external_sandhi_lattice(
    surface: str,
    *,
    rules: Iterable[SandhiRule] | None = None,
    index: SandhiRuleIndex | None = None,
    boundary_separator: str = " ",
) -> CandidateLattice:
    """
    Build an ambiguity-preserving candidate lattice over observed surface text.

    The lattice always contains a complete identity path:
        surface[0] -> surface[1] -> ... -> surface[n]

    In addition, every tracked external-sandhi surface match contributes a
    competing sandhi edge over the same observed span.

    No path is selected or ranked.

    `rules` and `index` are mutually exclusive.
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

    edges: list[LatticeEdge] = []

    # Always preserve the literal surface path.
    for start, char in enumerate(surface):
        edges.append(
            LatticeEdge(
                start=start,
                end=start + 1,
                kind="identity",
                surface=char,
            )
        )

    # Add every licensed inverse sandhi alternative.
    for match in index.iter_surface_matches(surface):
        rule = match.rule

        edges.append(
            LatticeEdge(
                start=match.start,
                end=match.end,
                kind="sandhi",
                surface=match.rendered_surface,
                left_underlying=rule.left,
                right_underlying=rule.right,
                rule_surface=rule.surface,
                rule_id=rule.rule_id,
                variant=rule.variant,
            )
        )

    # Stable topological ordering:
    # start offset, then end offset, then identity before sandhi,
    # then rule id for deterministic serialization/testing.
    edges.sort(
        key=lambda edge: (
            edge.start,
            edge.end,
            0 if edge.kind == "identity" else 1,
            edge.rule_id or "",
        )
    )

    return CandidateLattice(
        surface=surface,
        edges=tuple(edges),
    )


def iter_paths(
    lattice: CandidateLattice,
    *,
    max_paths: int | None = None,
) -> Iterator[tuple[LatticeEdge, ...]]:
    """
    Enumerate complete paths from node 0 to node len(surface).

    This is intended only for tests and tiny examples.
    Do NOT use it on corpus-scale text: the number of paths can grow
    exponentially. Later scoring/marginalization should operate directly
    on the DAG.
    """
    if max_paths is not None and max_paths < 1:
        raise ValueError("max_paths must be >= 1 or None.")

    yielded = 0
    target = len(lattice.surface)

    def walk(
        node: int,
        path: tuple[LatticeEdge, ...],
    ) -> Iterator[tuple[LatticeEdge, ...]]:
        nonlocal yielded

        if max_paths is not None and yielded >= max_paths:
            return

        if node == target:
            yielded += 1
            yield path
            return

        for edge in lattice.outgoing(node):
            yield from walk(
                edge.end,
                path + (edge,),
            )

            if max_paths is not None and yielded >= max_paths:
                return

    yield from walk(0, ())


def path_latent_pieces(
    path: Iterable[LatticeEdge],
) -> tuple[str, ...]:
    """
    Flatten the latent contribution of a complete lattice path.
    """
    pieces: list[str] = []

    for edge in path:
        pieces.extend(edge.latent_pieces)

    return tuple(pieces)

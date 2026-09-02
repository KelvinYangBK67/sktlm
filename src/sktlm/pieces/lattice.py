"""Reference position lattices for exact reusable-piece segmentation."""

from __future__ import annotations

from dataclasses import dataclass

from sktlm.latent.phonology import PhonologicalForm


@dataclass(frozen=True, slots=True)
class PieceEdge:
    """One exact contiguous slice of a latent lexical form."""

    start: int
    end: int
    piece: PhonologicalForm


@dataclass(frozen=True, slots=True)
class PieceLattice:
    """A position DAG whose complete paths concatenate to ``form``."""

    form: PhonologicalForm
    edges: tuple[PieceEdge, ...]

    @property
    def positions(self) -> tuple[int, ...]:
        return tuple(range(len(self.form.symbols) + 1))

    @property
    def outgoing_edges(self) -> tuple[tuple[PieceEdge, ...], ...]:
        grouped: list[list[PieceEdge]] = [[] for _ in self.positions]
        for edge in self.edges:
            grouped[edge.start].append(edge)
        return tuple(tuple(items) for items in grouped)


def build_piece_lattice(
    form: PhonologicalForm,
    *,
    max_piece_length: int,
) -> PieceLattice:
    """Build the complete P0 legal piece DAG for one lexical form.

    Every nonempty contiguous piece up to ``max_piece_length`` is legal. The
    whole form is also legal even when it is longer than that bound, so the
    reference objective must genuinely compete with whole-form memorization.
    """

    if max_piece_length < 1:
        raise ValueError("max_piece_length must be >= 1")
    length = len(form.symbols)
    edges: list[PieceEdge] = []
    for start in range(length):
        ends = set(range(start + 1, min(length, start + max_piece_length) + 1))
        if start == 0:
            ends.add(length)
        for end in sorted(ends):
            edges.append(
                PieceEdge(
                    start=start,
                    end=end,
                    piece=PhonologicalForm(form.symbols[start:end]),
                )
            )
    return PieceLattice(form=form, edges=tuple(edges))

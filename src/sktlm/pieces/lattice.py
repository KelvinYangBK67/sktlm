"""Reference position lattices for exact reusable-piece segmentation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sktlm.latent.phonology import PhonologicalForm


class PieceRole(str, Enum):
    """Position of one piece inside its host lexical form."""

    WHOLE = "WHOLE"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True, slots=True)
class PieceIdentity:
    """A role-bearing piece occurrence; its learned key is the phonological form."""

    piece: PhonologicalForm
    role: PieceRole

    @property
    def key(self) -> str:
        return self.piece.key

    @classmethod
    def from_key(cls, key: str) -> "PieceIdentity":
        # SQLite and worker reductions carry learned form keys. WHOLE is only
        # a placeholder here; the original edge role remains in inference.
        return cls(PhonologicalForm.from_key(key), PieceRole.WHOLE)


def piece_role(start: int, end: int, lexical_length: int) -> PieceRole:
    """Classify one nonempty piece span within a lexical form."""

    if not 0 <= start < end <= lexical_length:
        raise ValueError("piece span must be nonempty and inside the lexical form")
    if start == 0 and end == lexical_length:
        return PieceRole.WHOLE
    if start == 0:
        return PieceRole.LEFT
    if end == lexical_length:
        return PieceRole.RIGHT
    return PieceRole.INTERNAL


@dataclass(frozen=True, slots=True)
class PieceEdge:
    """One exact contiguous slice of a latent lexical form."""

    start: int
    end: int
    piece: PhonologicalForm
    role: PieceRole


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
                    role=piece_role(start, end, length),
                )
            )
    return PieceLattice(form=form, edges=tuple(edges))

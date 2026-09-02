"""Exact forward/backward inference over a reference piece lattice."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from sktlm.latent.phonology import PhonologicalForm
from sktlm.pieces.lattice import PieceEdge, PieceLattice
from sktlm.pieces.scorer import PieceScorer


def _logaddexp(left: float, right: float) -> float:
    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    maximum = max(left, right)
    return maximum + math.log(math.exp(left - maximum) + math.exp(right - maximum))


def raw_prior_edge_score(edge: PieceEdge, *, rho: float) -> float:
    """Return this edge's local contribution to the boundary prior."""

    if not 0.0 < rho < 1.0:
        raise ValueError("rho must be strictly between 0 and 1")
    cut_count = int(edge.start > 0)
    no_cut_count = edge.end - edge.start - 1
    return cut_count * math.log(rho) + no_cut_count * math.log1p(-rho)


@dataclass(frozen=True, slots=True)
class PieceSegmentation:
    pieces: tuple[PhonologicalForm, ...]
    log_weight: float
    probability: float


@dataclass(frozen=True, slots=True)
class PieceEvaluation:
    log_score: float
    expected_piece_counts: dict[PhonologicalForm, float]
    top_segmentations: tuple[PieceSegmentation, ...]
    prior_log_normalizer: float


@dataclass(frozen=True, slots=True)
class _PrefixPath:
    raw_score: float
    pieces: tuple[PhonologicalForm, ...]


def _forward(
    lattice: PieceLattice,
    edge_scores: dict[int, float],
) -> list[float]:
    length = len(lattice.form.symbols)
    alpha = [-math.inf] * (length + 1)
    alpha[0] = 0.0
    outgoing = lattice.outgoing_edges
    for position in range(length):
        if alpha[position] == -math.inf:
            continue
        for edge in outgoing[position]:
            alpha[edge.end] = _logaddexp(
                alpha[edge.end],
                alpha[position] + edge_scores[id(edge)],
            )
    return alpha


def evaluate_piece_lattice(
    lattice: PieceLattice,
    scorer: PieceScorer,
    *,
    rho: float,
    top_k: int | None = 8,
) -> PieceEvaluation:
    """Marginalize every legal segmentation exactly.

    Only ``top_segmentations`` is bounded. The partition and expected piece
    counts always come from exact forward/backward dynamic programming.
    """

    if not 0.0 < rho < 1.0:
        raise ValueError("rho must be strictly between 0 and 1")
    if top_k is not None and top_k < 1:
        raise ValueError("top_k must be >= 1 or None")
    outgoing = lattice.outgoing_edges
    length = len(lattice.form.symbols)
    prior_scores = {
        id(edge): raw_prior_edge_score(edge, rho=rho)
        for edge in lattice.edges
    }
    prior_alpha = _forward(lattice, prior_scores)
    prior_log_z = prior_alpha[-1]
    if prior_log_z == -math.inf:
        raise ValueError("Piece lattice has no complete segmentation.")

    distinct_pieces = {edge.piece for edge in lattice.edges}
    distinct_piece_scores = {
        piece: scorer.score(piece)
        for piece in sorted(distinct_pieces, key=lambda item: item.key)
    }
    edge_scores = {
        id(edge): prior_scores[id(edge)] + distinct_piece_scores[edge.piece]
        for edge in lattice.edges
    }
    alpha = _forward(lattice, edge_scores)
    raw_log_z = alpha[-1]
    if raw_log_z == -math.inf:
        raise ValueError("Piece lattice has no finite complete segmentation.")

    beta = [-math.inf] * (length + 1)
    beta[-1] = 0.0
    for position in range(length - 1, -1, -1):
        for edge in outgoing[position]:
            beta[position] = _logaddexp(
                beta[position],
                edge_scores[id(edge)] + beta[edge.end],
            )

    expected_counts: dict[PhonologicalForm, float] = defaultdict(float)
    for edge in lattice.edges:
        posterior = math.exp(
            alpha[edge.start]
            + edge_scores[id(edge)]
            + beta[edge.end]
            - raw_log_z
        )
        expected_counts[edge.piece] += posterior

    top_segmentations: tuple[PieceSegmentation, ...] = ()
    if top_k is not None:
        paths: list[list[_PrefixPath]] = [[] for _ in range(length + 1)]
        paths[0] = [_PrefixPath(0.0, ())]
        for position in range(length):
            for edge in outgoing[position]:
                candidates = paths[edge.end]
                candidates.extend(
                    _PrefixPath(
                        raw_score=prefix.raw_score + edge_scores[id(edge)],
                        pieces=prefix.pieces + (edge.piece,),
                    )
                    for prefix in paths[position]
                )
                candidates.sort(
                    key=lambda path: (
                        -path.raw_score,
                        tuple(piece.key for piece in path.pieces),
                    )
                )
                del candidates[top_k:]
        top_segmentations = tuple(
            PieceSegmentation(
                pieces=path.pieces,
                log_weight=path.raw_score - prior_log_z,
                probability=math.exp(path.raw_score - raw_log_z),
            )
            for path in paths[-1]
        )

    return PieceEvaluation(
        log_score=raw_log_z - prior_log_z,
        expected_piece_counts=dict(expected_counts),
        top_segmentations=top_segmentations,
        prior_log_normalizer=prior_log_z,
    )

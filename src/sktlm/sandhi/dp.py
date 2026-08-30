from __future__ import annotations

import math
from collections.abc import Callable

from sktlm.sandhi.lattice import (
    CandidateLattice,
    LatticeEdge,
)


EdgeLogScore = Callable[[LatticeEdge], float]


def _logaddexp(a: float, b: float) -> float:
    """
    Stable log(exp(a) + exp(b)) without NumPy/PyTorch.
    """
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a

    m = max(a, b)
    return m + math.log(
        math.exp(a - m)
        + math.exp(b - m)
    )


def count_paths(
    lattice: CandidateLattice,
) -> int:
    """
    Count complete paths through the DAG without enumerating them.
    """
    counts = [0] * lattice.num_nodes
    counts[0] = 1

    for node in range(lattice.num_nodes - 1):
        if counts[node] == 0:
            continue

        for edge in lattice.outgoing(node):
            counts[edge.end] += counts[node]

    return counts[-1]


def forward_log_scores(
    lattice: CandidateLattice,
    edge_log_score: EdgeLogScore,
) -> tuple[float, ...]:
    """
    Compute forward log-scores for every lattice node.

    alpha[j] is the log-sum of scores of every complete partial path
    from node 0 to node j.

    Path score is the sum of its edge log-scores.
    """
    alpha = [-math.inf] * lattice.num_nodes
    alpha[0] = 0.0

    for node in range(lattice.num_nodes - 1):
        if alpha[node] == -math.inf:
            continue

        for edge in lattice.outgoing(node):
            score = float(edge_log_score(edge))
            candidate = alpha[node] + score

            alpha[edge.end] = _logaddexp(
                alpha[edge.end],
                candidate,
            )

    return tuple(alpha)


def forward_log_partition(
    lattice: CandidateLattice,
    edge_log_score: EdgeLogScore,
) -> float:
    """
    Return log sum of scores over all complete candidate paths.

    If every edge has log-score 0, the result is:
        log(number_of_complete_paths)
    """
    return forward_log_scores(
        lattice,
        edge_log_score,
    )[-1]


def uniform_edge_log_score(
    edge: LatticeEdge,
) -> float:
    """
    Debug/reference scorer assigning score 1 (log-score 0) to every edge.
    """
    del edge
    return 0.0


def kind_bias_log_score(
    *,
    identity_log_score: float = 0.0,
    sandhi_log_score: float = 0.0,
) -> EdgeLogScore:
    """
    Build a tiny diagnostic scorer based only on edge type.

    This is not a linguistic model. It is useful only for testing the
    forward algorithm before a real contextual scoring model is connected.
    """
    def score(edge: LatticeEdge) -> float:
        if edge.kind == "identity":
            return identity_log_score
        return sandhi_log_score

    return score


def viterbi_best_path(
    lattice: CandidateLattice,
    edge_log_score: EdgeLogScore,
) -> tuple[float, tuple[LatticeEdge, ...]]:
    """
    Return the highest-scoring complete path.

    This is provided only for debugging/inspection. The research model
    should preserve ambiguity and use forward marginalization rather than
    replacing the lattice with this hard path.
    """
    best = [-math.inf] * lattice.num_nodes
    back: list[LatticeEdge | None] = [None] * lattice.num_nodes

    best[0] = 0.0

    for node in range(lattice.num_nodes - 1):
        if best[node] == -math.inf:
            continue

        for edge in lattice.outgoing(node):
            candidate = (
                best[node]
                + float(edge_log_score(edge))
            )

            if candidate > best[edge.end]:
                best[edge.end] = candidate
                back[edge.end] = edge

    if best[-1] == -math.inf:
        raise ValueError(
            "Lattice has no complete path from start to end."
        )

    path: list[LatticeEdge] = []
    node = lattice.num_nodes - 1

    while node != 0:
        edge = back[node]

        if edge is None:
            raise RuntimeError(
                "Broken Viterbi backpointer chain."
            )

        path.append(edge)
        node = edge.start

    path.reverse()

    return best[-1], tuple(path)

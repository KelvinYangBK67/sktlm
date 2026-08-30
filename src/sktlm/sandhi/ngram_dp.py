from __future__ import annotations

import math
from collections import defaultdict

from sktlm.experiments.models.ngram import (
    EOS,
    CharNGramLM,
)
from sktlm.sandhi.dp import _logaddexp
from sktlm.sandhi.lattice import (
    CandidateLattice,
    LatticeEdge,
)


def edge_latent_text(
    edge: LatticeEdge,
) -> str:
    """
    Convert one lattice edge into the latent character material scored by LM.

    identity:
        observed surface character

    sandhi:
        underlying-left + '#' + underlying-right
    """
    if edge.kind == "identity":
        return edge.surface

    assert edge.left_underlying is not None
    assert edge.right_underlying is not None

    return (
        edge.left_underlying
        + "#"
        + edge.right_underlying
    )


def score_text_from_context(
    lm: CharNGramLM,
    text: str,
    context: tuple[str, ...],
) -> tuple[float, tuple[str, ...]]:
    """
    Score text under LM starting from an existing n-gram context.
    """
    total = 0.0
    current = context

    for char in text:
        symbol = lm.normalize_symbol(char)

        total += lm.log_prob(
            symbol,
            current,
        )

        current = lm.advance_context(
            current,
            symbol,
        )

    return total, current


def lattice_ngram_log_partition(
    lattice: CandidateLattice,
    lm: CharNGramLM,
    *,
    include_eos: bool = True,
) -> float:
    """
    Marginalize a character n-gram LM over every complete lattice path.

    Because n-gram edge scores depend on preceding latent context, the DP state
    is (surface_node, ngram_context), not merely surface_node.

    No complete candidate paths are explicitly enumerated.
    """
    states: list[
        dict[tuple[str, ...], float]
    ] = [
        {} for _ in range(lattice.num_nodes)
    ]

    states[0][lm.start_context()] = 0.0

    for node in range(lattice.num_nodes - 1):
        if not states[node]:
            continue

        for context, prefix_score in tuple(
            states[node].items()
        ):
            for edge in lattice.outgoing(node):
                text = edge_latent_text(edge)

                edge_score, next_context = (
                    score_text_from_context(
                        lm,
                        text,
                        context,
                    )
                )

                candidate = (
                    prefix_score
                    + edge_score
                )

                previous = states[edge.end].get(
                    next_context,
                    -math.inf,
                )

                states[edge.end][next_context] = (
                    _logaddexp(
                        previous,
                        candidate,
                    )
                )

    final_states = states[-1]

    if not final_states:
        raise ValueError(
            "Lattice has no complete path from start to end."
        )

    total = -math.inf

    for context, path_score in final_states.items():
        score = path_score

        if include_eos:
            score += lm.log_prob(
                EOS,
                context,
            )

        total = _logaddexp(
            total,
            score,
        )

    return total


def lattice_ngram_viterbi(
    lattice: CandidateLattice,
    lm: CharNGramLM,
    *,
    include_eos: bool = True,
) -> tuple[
    float,
    tuple[LatticeEdge, ...],
]:
    """
    Highest-scoring n-gram path for debugging/inspection only.

    Research scoring should normally use lattice_ngram_log_partition().
    """
    scores: list[
        dict[tuple[str, ...], float]
    ] = [
        {} for _ in range(lattice.num_nodes)
    ]

    back: list[
        dict[
            tuple[str, ...],
            tuple[
                int,
                tuple[str, ...],
                LatticeEdge,
            ],
        ]
    ] = [
        {} for _ in range(lattice.num_nodes)
    ]

    scores[0][lm.start_context()] = 0.0

    for node in range(lattice.num_nodes - 1):
        for context, prefix_score in tuple(
            scores[node].items()
        ):
            for edge in lattice.outgoing(node):
                text = edge_latent_text(edge)

                edge_score, next_context = (
                    score_text_from_context(
                        lm,
                        text,
                        context,
                    )
                )

                candidate = prefix_score + edge_score
                previous = scores[edge.end].get(
                    next_context,
                    -math.inf,
                )

                if candidate > previous:
                    scores[edge.end][next_context] = candidate
                    back[edge.end][next_context] = (
                        node,
                        context,
                        edge,
                    )

    if not scores[-1]:
        raise ValueError(
            "Lattice has no complete path from start to end."
        )

    best_context = None
    best_score = -math.inf

    for context, score in scores[-1].items():
        final_score = score

        if include_eos:
            final_score += lm.log_prob(
                EOS,
                context,
            )

        if final_score > best_score:
            best_score = final_score
            best_context = context

    assert best_context is not None

    path: list[LatticeEdge] = []
    node = lattice.num_nodes - 1
    context = best_context

    while node != 0:
        previous_node, previous_context, edge = (
            back[node][context]
        )

        path.append(edge)

        node = previous_node
        context = previous_context

    path.reverse()

    return best_score, tuple(path)

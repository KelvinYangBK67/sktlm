from __future__ import annotations

import math
from dataclasses import dataclass

from sktlm.experiments.models.ngram import (
    EOS,
    CharNGramLM,
)
from sktlm.sandhi.dp import _logaddexp
from sktlm.sandhi.lattice import (
    CandidateLattice,
    LatticeEdge,
)
from sktlm.sandhi.ngram_dp import (
    edge_latent_text,
    score_text_from_context,
)


@dataclass(frozen=True, slots=True)
class EdgePosterior:
    edge: LatticeEdge
    probability: float


@dataclass(frozen=True, slots=True)
class RulePosterior:
    rule_id: str
    probability: float


def _forward_states(
    lattice: CandidateLattice,
    lm: CharNGramLM,
) -> tuple[dict[tuple[str, ...], float], ...]:
    states: list[dict[tuple[str, ...], float]] = [
        {} for _ in range(lattice.num_nodes)
    ]
    states[0][lm.start_context()] = 0.0

    for node in range(lattice.num_nodes - 1):
        for context, prefix_score in tuple(
            states[node].items()
        ):
            for edge in lattice.outgoing(node):
                edge_score, next_context = score_text_from_context(
                    lm,
                    edge_latent_text(edge),
                    context,
                )

                candidate = prefix_score + edge_score

                previous = states[edge.end].get(
                    next_context,
                    -math.inf,
                )

                states[edge.end][next_context] = _logaddexp(
                    previous,
                    candidate,
                )

    return tuple(states)


def _log_partition_from_forward(
    forward: tuple[dict[tuple[str, ...], float], ...],
    lm: CharNGramLM,
    *,
    include_eos: bool,
) -> float:
    total = -math.inf

    for context, score in forward[-1].items():
        final_score = score

        if include_eos:
            final_score += lm.log_prob(
                EOS,
                context,
            )

        total = _logaddexp(
            total,
            final_score,
        )

    if total == -math.inf:
        raise ValueError(
            "Lattice has no complete path from start to end."
        )

    return total


def _backward_states(
    lattice: CandidateLattice,
    lm: CharNGramLM,
    forward: tuple[dict[tuple[str, ...], float], ...],
    *,
    include_eos: bool,
) -> tuple[dict[tuple[str, ...], float], ...]:
    """
    beta[node][context] is the log-sum score of every continuation
    from (node, context) to the end of the lattice.
    """
    beta: list[dict[tuple[str, ...], float]] = [
        {} for _ in range(lattice.num_nodes)
    ]

    for context in forward[-1]:
        beta[-1][context] = (
            lm.log_prob(EOS, context)
            if include_eos
            else 0.0
        )

    for node in range(lattice.num_nodes - 2, -1, -1):
        for context in forward[node]:
            total = -math.inf

            for edge in lattice.outgoing(node):
                edge_score, next_context = score_text_from_context(
                    lm,
                    edge_latent_text(edge),
                    context,
                )

                suffix_score = beta[edge.end].get(
                    next_context,
                    -math.inf,
                )

                if suffix_score == -math.inf:
                    continue

                total = _logaddexp(
                    total,
                    edge_score + suffix_score,
                )

            beta[node][context] = total

    return tuple(beta)


def ngram_edge_posteriors(
    lattice: CandidateLattice,
    lm: CharNGramLM,
    *,
    include_eos: bool = True,
) -> tuple[EdgePosterior, ...]:
    """
    Return posterior probability that a complete latent path uses each edge.

    Posterior is computed exactly under the character n-gram LM using
    forward-backward over states (surface_node, ngram_context).

    Edges with zero posterior are still returned with probability 0.
    """
    forward = _forward_states(
        lattice,
        lm,
    )

    log_z = _log_partition_from_forward(
        forward,
        lm,
        include_eos=include_eos,
    )

    backward = _backward_states(
        lattice,
        lm,
        forward,
        include_eos=include_eos,
    )

    results: list[EdgePosterior] = []

    for edge in lattice.edges:
        edge_log_mass = -math.inf

        for context, prefix_score in forward[edge.start].items():
            edge_score, next_context = score_text_from_context(
                lm,
                edge_latent_text(edge),
                context,
            )

            suffix_score = backward[edge.end].get(
                next_context,
                -math.inf,
            )

            if suffix_score == -math.inf:
                continue

            edge_log_mass = _logaddexp(
                edge_log_mass,
                prefix_score + edge_score + suffix_score,
            )

        probability = (
            0.0
            if edge_log_mass == -math.inf
            else math.exp(edge_log_mass - log_z)
        )

        # Numerical rounding can produce 1 + epsilon.
        probability = min(
            1.0,
            max(0.0, probability),
        )

        results.append(
            EdgePosterior(
                edge=edge,
                probability=probability,
            )
        )

    return tuple(results)


def ngram_rule_posteriors(
    lattice: CandidateLattice,
    lm: CharNGramLM,
    *,
    include_eos: bool = True,
) -> tuple[RulePosterior, ...]:
    """
    Aggregate sandhi-edge posterior mass by rule_id.

    If the same rule can match more than one non-overlapping location,
    the sum is an expected usage count and may exceed 1.0.
    """
    edge_posteriors = ngram_edge_posteriors(
        lattice,
        lm,
        include_eos=include_eos,
    )

    totals: dict[str, float] = {}

    for item in edge_posteriors:
        edge = item.edge

        if edge.kind != "sandhi":
            continue
        if edge.rule_id is None:
            continue

        totals[edge.rule_id] = (
            totals.get(edge.rule_id, 0.0)
            + item.probability
        )

    return tuple(
        RulePosterior(
            rule_id=rule_id,
            probability=probability,
        )
        for rule_id, probability in sorted(
            totals.items()
        )
    )


def expected_sandhi_edges(
    lattice: CandidateLattice,
    lm: CharNGramLM,
    *,
    include_eos: bool = True,
) -> float:
    """
    Expected number of sandhi edges used by a posterior-sampled path.
    """
    return sum(
        item.probability
        for item in ngram_edge_posteriors(
            lattice,
            lm,
            include_eos=include_eos,
        )
        if item.edge.kind == "sandhi"
    )

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from sktlm.experiments.models.ngram import (
    EOS,
    CharNGramLM,
)
from sktlm.sandhi.lattice import (
    CandidateLattice,
    build_external_sandhi_lattice,
)
from sktlm.sandhi.ngram_dp import (
    edge_latent_text,
    lattice_ngram_log_partition,
    score_text_from_context,
)
from sktlm.sandhi.ngram_posterior import (
    _backward_states,
    _forward_states,
    _log_partition_from_forward,
)


@dataclass(frozen=True, slots=True)
class ExpectedNGramCounts:
    ngram_counts: dict[tuple[str, ...], float]
    context_counts: dict[tuple[str, ...], float]
    log_partition: float


@dataclass(frozen=True, slots=True)
class SurfaceNGramTrainingResult:
    model: CharNGramLM
    log_partitions: tuple[float, ...]


def candidate_latent_alphabet(
    surfaces: tuple[str, ...],
) -> frozenset[str]:
    """
    Collect every Unicode character that can appear on any candidate path.

    This uses only observed surfaces plus the fixed external-sandhi grammar;
    it does not use latent gold analyses.
    """
    alphabet: set[str] = set()

    for surface in surfaces:
        lattice = build_external_sandhi_lattice(
            surface,
        )

        for edge in lattice.edges:
            alphabet.update(
                edge_latent_text(edge)
            )

    return frozenset(alphabet)


def initialize_surface_ngram(
    surfaces: tuple[str, ...],
    *,
    order: int = 3,
    alpha: float = 0.1,
) -> CharNGramLM:
    """
    Initialize from observed surface strings only.

    Candidate latent symbols are added to the vocabulary without adding any
    latent training counts. This prevents unseen underlying characters from
    being collapsed to UNK during the first E-step.
    """
    if not surfaces:
        raise ValueError(
            "Cannot train on an empty surface corpus."
        )

    if any(
        not isinstance(surface, str)
        or not surface
        for surface in surfaces
    ):
        raise ValueError(
            "All surface strings must be non-empty strings."
        )

    alphabet = candidate_latent_alphabet(
        surfaces,
    )

    return CharNGramLM(
        order=order,
        alpha=alpha,
    ).fit(
        surfaces,
        extra_symbols=alphabet,
    )


def expected_counts_for_lattice(
    lattice: CandidateLattice,
    lm: CharNGramLM,
    *,
    include_eos: bool = True,
) -> ExpectedNGramCounts:
    """
    Exact E-step expected n-gram transition counts for one lattice.

    Each posterior-weighted path contributes fractional character-transition
    counts. Multi-character sandhi edges are replayed internally so their
    changing n-gram contexts are counted correctly.
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

    ngram_counts: Counter[
        tuple[str, ...]
    ] = Counter()

    context_counts: Counter[
        tuple[str, ...]
    ] = Counter()

    for edge in lattice.edges:
        for context, prefix_score in forward[
            edge.start
        ].items():
            edge_score, next_context = (
                score_text_from_context(
                    lm,
                    edge_latent_text(edge),
                    context,
                )
            )

            suffix_score = backward[
                edge.end
            ].get(
                next_context,
                -math.inf,
            )

            if suffix_score == -math.inf:
                continue

            log_mass = (
                prefix_score
                + edge_score
                + suffix_score
                - log_z
            )
            mass = math.exp(log_mass)

            current = context

            for char in edge_latent_text(edge):
                symbol = lm.normalize_symbol(
                    char,
                )

                context_counts[current] += mass
                ngram_counts[
                    current + (symbol,)
                ] += mass

                current = lm.advance_context(
                    current,
                    symbol,
                )

    if include_eos:
        for context, prefix_score in forward[-1].items():
            eos_score = lm.log_prob(
                EOS,
                context,
            )

            mass = math.exp(
                prefix_score
                + eos_score
                - log_z
            )

            context_counts[context] += mass
            ngram_counts[
                context + (EOS,)
            ] += mass

    return ExpectedNGramCounts(
        ngram_counts=dict(
            ngram_counts,
        ),
        context_counts=dict(
            context_counts,
        ),
        log_partition=log_z,
    )


def expected_counts_for_corpus(
    surfaces: tuple[str, ...],
    lm: CharNGramLM,
) -> ExpectedNGramCounts:
    if not surfaces:
        raise ValueError(
            "Cannot train on an empty surface corpus."
        )

    total_ngram: Counter[
        tuple[str, ...]
    ] = Counter()

    total_context: Counter[
        tuple[str, ...]
    ] = Counter()

    total_log_z = 0.0

    for surface in surfaces:
        lattice = build_external_sandhi_lattice(
            surface,
        )

        expected = expected_counts_for_lattice(
            lattice,
            lm,
        )

        total_ngram.update(
            expected.ngram_counts,
        )
        total_context.update(
            expected.context_counts,
        )
        total_log_z += expected.log_partition

    return ExpectedNGramCounts(
        ngram_counts=dict(
            total_ngram,
        ),
        context_counts=dict(
            total_context,
        ),
        log_partition=total_log_z,
    )


def corpus_log_partition(
    surfaces: tuple[str, ...],
    lm: CharNGramLM,
) -> float:
    return sum(
        lattice_ngram_log_partition(
            build_external_sandhi_lattice(
                surface,
            ),
            lm,
        )
        for surface in surfaces
    )


def train_surface_ngram_expected_counts(
    surfaces: tuple[str, ...],
    *,
    order: int = 3,
    alpha: float = 0.1,
    iterations: int = 3,
) -> SurfaceNGramTrainingResult:
    """
    Surface-only EM-style expected-count training.

    No latent strings are supplied. The fixed external-sandhi grammar defines
    the candidate lattices; the current n-gram model provides posterior path
    weights; posterior expected counts replace the model counts each round.

    Because add-alpha smoothing remains active, this should be treated as an
    EM-style expected-count procedure, not as a claim of strict unsmoothed
    maximum-likelihood EM monotonicity.
    """
    if iterations < 0:
        raise ValueError(
            "iterations must be >= 0."
        )

    materialized = tuple(surfaces)

    model = initialize_surface_ngram(
        materialized,
        order=order,
        alpha=alpha,
    )

    history = [
        corpus_log_partition(
            materialized,
            model,
        )
    ]

    vocabulary = model.vocabulary

    for _ in range(iterations):
        expected = expected_counts_for_corpus(
            materialized,
            model,
        )

        model.replace_counts(
            ngram_counts=expected.ngram_counts,
            context_counts=expected.context_counts,
            vocabulary=vocabulary,
        )

        history.append(
            corpus_log_partition(
                materialized,
                model,
            )
        )

    return SurfaceNGramTrainingResult(
        model=model,
        log_partitions=tuple(
            history,
        ),
    )

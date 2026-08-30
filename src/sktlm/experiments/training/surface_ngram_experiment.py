from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from sktlm.experiments.training.ngram_em import (
    corpus_log_partition,
    expected_counts_for_corpus,
    initialize_surface_ngram,
)
from sktlm.sandhi.lattice import build_external_sandhi_lattice
from sktlm.sandhi.ngram_posterior import (
    expected_sandhi_edges,
    ngram_edge_posteriors,
)


DEFAULT_SURFACES = (
    "devo'pi",
    "rāmo'pi",
    "aśvo'pi",
    "naro'pi",
)


@dataclass(frozen=True, slots=True)
class IterationSummary:
    iteration: int
    corpus_log_partition: float
    mean_expected_sandhi_edges: float
    mean_target_posterior: float
    per_surface_target_posterior: dict[str, float]


def _target_posterior(
    surface: str,
    model,
) -> float:
    lattice = build_external_sandhi_lattice(surface)

    return sum(
        item.probability
        for item in ngram_edge_posteriors(
            lattice,
            model,
        )
        if item.edge.kind == "sandhi"
        and item.edge.left_underlying == "aḥ"
        and item.edge.right_underlying == "a"
        and item.edge.surface == "o'"
    )


def _summarize(
    iteration: int,
    surfaces: tuple[str, ...],
    model,
) -> IterationSummary:
    per_surface = {
        surface: _target_posterior(
            surface,
            model,
        )
        for surface in surfaces
    }

    sandhi_expectations = [
        expected_sandhi_edges(
            build_external_sandhi_lattice(
                surface
            ),
            model,
        )
        for surface in surfaces
    ]

    return IterationSummary(
        iteration=iteration,
        corpus_log_partition=corpus_log_partition(
            surfaces,
            model,
        ),
        mean_expected_sandhi_edges=(
            sum(sandhi_expectations)
            / len(sandhi_expectations)
        ),
        mean_target_posterior=(
            sum(per_surface.values())
            / len(per_surface)
        ),
        per_surface_target_posterior=per_surface,
    )


def run_surface_only_experiment(
    surfaces: tuple[str, ...] = DEFAULT_SURFACES,
    *,
    order: int = 3,
    alpha: float = 0.1,
    iterations: int = 10,
) -> tuple[IterationSummary, ...]:
    """
    Run a tiny surface-only latent-sandhi learning experiment.

    No latent gold strings are supplied.
    The external-sandhi grammar alone defines the candidate lattice.
    """
    if iterations < 0:
        raise ValueError(
            "iterations must be >= 0."
        )

    model = initialize_surface_ngram(
        surfaces,
        order=order,
        alpha=alpha,
    )

    summaries = [
        _summarize(
            0,
            surfaces,
            model,
        )
    ]

    vocabulary = model.vocabulary

    for iteration in range(
        1,
        iterations + 1,
    ):
        expected = expected_counts_for_corpus(
            surfaces,
            model,
        )

        model.replace_counts(
            ngram_counts=expected.ngram_counts,
            context_counts=expected.context_counts,
            vocabulary=vocabulary,
        )

        summaries.append(
            _summarize(
                iteration,
                surfaces,
                model,
            )
        )

    return tuple(summaries)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Surface-only toy latent-sandhi "
            "n-gram experiment."
        )
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--order",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.1,
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    summaries = run_surface_only_experiment(
        order=args.order,
        alpha=args.alpha,
        iterations=args.iterations,
    )

    print(
        json.dumps(
            [
                asdict(item)
                for item in summaries
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

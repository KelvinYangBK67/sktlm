from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Iterable

from sktlm.experiments.models.ngram import CharNGramLM
from sktlm.sandhi.dp import count_paths
from sktlm.sandhi.lattice import build_external_sandhi_lattice
from sktlm.sandhi.ngram_dp import (
    edge_latent_text,
    lattice_ngram_log_partition,
    lattice_ngram_viterbi,
)


DEFAULT_TRAINING_TEXTS = (
    "devaḥ#api",
    "rāmaḥ#api",
    "aśvaḥ#api",
    "naraḥ#api",
) * 20 + (
    "devo'pi",
)


@dataclass(frozen=True, slots=True)
class SandhiNGramSmokeResult:
    surface: str
    order: int
    alpha: float
    num_nodes: int
    num_edges: int
    num_paths: int
    marginal_log_likelihood: float
    viterbi_log_likelihood: float
    viterbi_latent_text: str
    viterbi_uses_sandhi: bool
    viterbi_rule_ids: tuple[str, ...]


def run_sandhi_ngram_smoke(
    surface: str = "devo'pi",
    *,
    training_texts: Iterable[str] = DEFAULT_TRAINING_TEXTS,
    order: int = 3,
    alpha: float = 0.01,
) -> SandhiNGramSmokeResult:
    """
    Run a minimal end-to-end latent-sandhi smoke experiment.

    Pipeline:
        latent-form toy training strings
            -> character n-gram LM
        observed surface string
            -> external-sandhi candidate lattice
            -> n-gram marginalization over all paths

    This function is a software/integration smoke test only.
    It does not use M0 corpus data and must not be reported as an experiment.
    """
    if not surface:
        raise ValueError("surface must be non-empty.")

    model = CharNGramLM(
        order=order,
        alpha=alpha,
    ).fit(training_texts)

    lattice = build_external_sandhi_lattice(surface)

    marginal = lattice_ngram_log_partition(
        lattice,
        model,
    )

    best_score, best_path = lattice_ngram_viterbi(
        lattice,
        model,
    )

    latent_text = "".join(
        edge_latent_text(edge)
        for edge in best_path
    )

    sandhi_edges = tuple(
        edge
        for edge in best_path
        if edge.kind == "sandhi"
    )

    return SandhiNGramSmokeResult(
        surface=surface,
        order=order,
        alpha=alpha,
        num_nodes=lattice.num_nodes,
        num_edges=lattice.num_edges,
        num_paths=count_paths(lattice),
        marginal_log_likelihood=marginal,
        viterbi_log_likelihood=best_score,
        viterbi_latent_text=latent_text,
        viterbi_uses_sandhi=bool(sandhi_edges),
        viterbi_rule_ids=tuple(
            edge.rule_id
            for edge in sandhi_edges
            if edge.rule_id is not None
        ),
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the toy end-to-end external-sandhi "
            "lattice + n-gram smoke experiment."
        )
    )
    parser.add_argument(
        "--surface",
        default="devo'pi",
        help="Observed IAST surface string to analyze.",
    )
    parser.add_argument(
        "--order",
        type=int,
        default=3,
        help="Character n-gram order.",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.01,
        help="Add-alpha smoothing value.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    result = run_sandhi_ngram_smoke(
        surface=args.surface,
        order=args.order,
        alpha=args.alpha,
    )

    print(
        json.dumps(
            asdict(result),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

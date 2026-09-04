"""CLI for full-corpus latent lexical induction over formal M0 cells."""

from __future__ import annotations

import argparse
from pathlib import Path

from sktlm.latent.training import TrainingConfig, run_training


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train the streaming v1 latent Sanskrit unigram lexicon for one "
            "frozen M0 or derived M0-prime script/spacing condition."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/manifests/representations.csv"),
    )
    parser.add_argument("--document-list", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/latent_lexicon"),
    )
    parser.add_argument("--run-id")
    parser.add_argument(
        "--script",
        choices=("iast", "devanagari", "iast_m0_prime"),
        default="iast",
    )
    parser.add_argument(
        "--condition",
        choices=("surface_word", "legacy_joined", "continuous"),
        default="surface_word",
    )
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument(
        "--vocab-budget",
        type=int,
        help=(
            "Freeze K distinct latent form_key identities after pass 1; K includes "
            "all 50 phonological base units."
        ),
    )
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument("--lexical-alpha", type=float, default=0.1)
    parser.add_argument("--complexity-weight", type=float, default=0.5)
    parser.add_argument("--complexity-tau", type=float, default=1.0)
    parser.add_argument("--whitespace-merge-penalty", type=float, default=8.0)
    parser.add_argument("--no-whitespace-merge", action="store_true")
    parser.add_argument("--max-internal-matches", type=int, default=512)
    parser.add_argument("--max-segment-tokens", type=int, default=128)
    parser.add_argument("--lexicon-cache-size", type=int, default=100_000)
    parser.add_argument("--flush-types", type=int, default=50_000)
    parser.add_argument("--analysis-top-k", type=int, default=8)
    parser.add_argument("--usage-posterior-threshold", type=float, default=0.01)
    parser.add_argument("--high-confidence-threshold", type=float, default=0.8)
    parser.add_argument("--low-count-threshold", type=float, default=1.0)
    parser.add_argument("--max-documents", type=int)
    parser.add_argument("--max-lines-per-document", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--equivalence-diagnostics", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    config = TrainingConfig(
        manifest=args.manifest,
        document_list=args.document_list,
        output_root=args.output_root,
        run_id=args.run_id,
        script=args.script,
        condition=args.condition,
        passes=args.passes,
        vocab_budget=args.vocab_budget,
        workers=args.workers,
        lexical_alpha=args.lexical_alpha,
        complexity_weight=args.complexity_weight,
        complexity_tau=args.complexity_tau,
        whitespace_merge_penalty=args.whitespace_merge_penalty,
        allow_whitespace_merge=not args.no_whitespace_merge,
        max_internal_matches=args.max_internal_matches,
        max_segment_tokens=args.max_segment_tokens,
        lexicon_cache_size=args.lexicon_cache_size,
        flush_types=args.flush_types,
        analysis_top_k=args.analysis_top_k,
        usage_posterior_threshold=args.usage_posterior_threshold,
        high_confidence_threshold=args.high_confidence_threshold,
        low_count_threshold=args.low_count_threshold,
        max_documents=args.max_documents,
        max_lines_per_document=args.max_lines_per_document,
        seed=args.seed,
        equivalence_diagnostics=args.equivalence_diagnostics,
        resume=args.resume,
    )
    result = run_training(config)
    print(f"run artifacts: {result.run_dir}")
    print(f"passes: {len(result.history)}")
    print(f"latent lexical types: {result.summary['complexity']['active_lexical_types']}")


if __name__ == "__main__":
    main()

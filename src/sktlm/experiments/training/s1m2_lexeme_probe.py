"""Diagnostic-only S1M2 training followed by held-out exact inspection."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.lazy_candidates import build_lazy_candidate_graph
from sktlm.latent.phonology import normalize_iast, parse_iast_form
from sktlm.latent.store import PieceStoreScorer
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.latent.training import (
    DiagnosticCorpusSource,
    S1M2_MODEL,
    TrainingConfig,
    _file_sha256,
    _git_commit,
    _write_json,
    run_training,
)
from sktlm.pieces.composed import ComposedPieceInference, infer_composed_segment


_GOLD_POSTERIOR_REASON = (
    "The exact composed reduction has lexical expected counts, not the "
    "indicator posterior for this particular target occurrence; top-K mass "
    "is not an exact substitute."
)
_TARGET_TRANSFORM_REASON = (
    "Exact transformed-event posteriors are sentence-level, not target-local."
)


def _read_challenge(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("text"), str):
                raise ValueError(f"Invalid challenge text at {path}:{line_number}")
            matches = row.get("matches", [])
            if not isinstance(matches, list) or any(
                not isinstance(match, dict) or not isinstance(match.get("form"), str)
                for match in matches
            ):
                raise ValueError(f"Invalid challenge matches at {path}:{line_number}")
            rows.append(row)
    if not rows:
        raise ValueError(f"Challenge is empty: {path}")
    return rows


def _read_extra_challenge(text_path: Path, gold_path: Path | None) -> list[dict[str, Any]]:
    texts = [
        line.strip()
        for line in text_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not texts:
        raise ValueError(f"Extra challenge is empty: {text_path}")
    if gold_path is None:
        return [{"text": text, "matches": []} for text in texts]
    gold = _read_challenge(gold_path)
    if len(gold) != len(texts) or any(
        row["text"] != text for row, text in zip(gold, texts)
    ):
        raise ValueError("Extra gold JSONL must align exactly with extra text lines.")
    return gold


def _validate_held_out(corpus: Path, challenge_rows: list[dict[str, Any]]) -> None:
    challenge_texts = {row["text"] for row in challenge_rows}
    with corpus.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.rstrip("\r\n") in challenge_texts:
                raise ValueError(
                    f"Challenge sentence occurs verbatim in training corpus at line {line_number}."
                )


def _gold_form(match: dict[str, Any]) -> tuple[str | None, str | None]:
    value = match.get("unsandhied")
    if not isinstance(value, str) or not value.strip():
        return None, "DCS Unsandhied is missing."
    try:
        return parse_iast_form(value.strip()).iast, None
    except ValueError:
        return None, "DCS Unsandhied is not a valid IAST phonological form."


def evaluate_challenge(
    *,
    config: TrainingConfig,
    run_dir: Path,
    source: DiagnosticCorpusSource,
    challenge_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read the final model via SQLite mode=ro; write only challenge artifacts."""

    database = run_dir / "learner.sqlite"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        scorer = PieceStoreScorer(
            connection,
            alpha=config.piece_alpha,
            complexity_weight=config.piece_complexity_weight,
            complexity_kappa=config.piece_complexity_kappa,
            complexity_beta=config.piece_complexity_beta,
            complexity_tau=config.piece_complexity_tau,
            base_stop_probability=config.piece_base_stop_probability,
            cache_size=config.lexicon_cache_size,
            telemetry=RuntimeTelemetry(),
        )
        engine = ComposedPieceInference(
            scorer,
            model_config=config.piece_model_config,
            cache_config=config.piece_cache_config,
            inspection_top_k=config.analysis_top_k,
        )
        grammar = StructuredSandhiGrammar.from_default_inventory()
        output = run_dir / "challenge_analyses.jsonl"
        occurrences = 0
        evaluable = 0
        recovered = 0
        top_whole = 0
        top_piece_count = 0
        with output.open("w", encoding="utf-8", newline="\n") as handle:
            for sentence_index, row in enumerate(challenge_rows):
                text = row["text"]
                matches = row.get("matches", [])
                segments = tuple(
                    iter_observed_segments(
                        text,
                        max_tokens=config.max_segment_tokens,
                        script="iast",
                    )
                )
                results = []
                for segment in segments:
                    graph = build_lazy_candidate_graph(
                        segment, grammar, config.candidate_config
                    )
                    results.append(
                        infer_composed_segment(
                            graph,
                            engine,
                            whitespace_merge_penalty=config.whitespace_merge_penalty,
                            sandhi_transformation_penalty=(
                                config.sandhi_transformation_penalty
                            ),
                            support_epsilon=config.piece_support_epsilon,
                        )
                    )
                if not results:
                    raise ValueError(f"Challenge sentence {sentence_index} has no segment.")
                top = [
                    inference.top_analyses[0] if inference.top_analyses else None
                    for inference in results
                ]
                if any(item is None for item in top):
                    raise ValueError(f"Challenge sentence {sentence_index} has no top analysis.")
                top_analyses = [item for item in top if item is not None]
                top_forms = [
                    word.iast for analysis in top_analyses for word in analysis.words
                ]
                top_posterior = 1.0
                for analysis in top_analyses:
                    top_posterior *= analysis.probability
                token_locations: dict[str, list[tuple[int, int]]] = {}
                for segment_index, segment in enumerate(segments):
                    for token_index, token in enumerate(segment.tokens):
                        token_locations.setdefault(normalize_iast(token.written), []).append(
                            (segment_index, token_index)
                        )
                for match_index, match in enumerate(matches or [None]):
                    if match is not None:
                        occurrences += 1
                    gold, gold_reason = (
                        _gold_form(match) if match is not None else (None, "No target match metadata.")
                    )
                    form = None if match is None else match["form"]
                    locations = (
                        [] if form is None else token_locations.get(normalize_iast(form), [])
                    )
                    localized = None
                    localization_reason = None
                    if len(matches) != 1 or len(locations) != 1:
                        localization_reason = (
                            "Target occurrence is absent or ambiguous in observed tokens."
                        )
                    else:
                        segment_index, token_index = locations[0]
                        analysis = top_analyses[segment_index]
                        if len(analysis.words) == len(segments[segment_index].tokens):
                            pieces = analysis.piece_segmentations[token_index]
                            localized = {
                                "lexical_form": analysis.words[token_index].iast,
                                "pieces": [piece.iast for piece in pieces],
                                "piece_count": len(pieces),
                                "whole_form": len(pieces) == 1,
                            }
                        else:
                            localization_reason = (
                                "Top analysis has multiple lexical factors in a surface token."
                            )
                    if localized is not None and gold is not None:
                        evaluable += 1
                        recovered += localized["lexical_form"] == gold
                        top_whole += localized["whole_form"]
                        top_piece_count += localized["piece_count"]
                    record = {
                        "target_id": source.target_id,
                        "level": source.level,
                        "sentence_index": sentence_index,
                        "match_index": match_index if match is not None else None,
                        "sentence_text": text,
                        "dcs_target_form": form,
                        "dcs_unsandhied_gold_form": gold,
                        "gold_unavailable_reason": gold_reason,
                        "top_analysis": {
                            "lexical_forms": top_forms,
                            "segments": [
                                {
                                    "surface": segment.written,
                                    "lexical_forms": [word.iast for word in analysis.words],
                                    "piece_segmentations": [
                                        [piece.iast for piece in pieces]
                                        for pieces in analysis.piece_segmentations
                                    ],
                                    "rule_ids": list(analysis.rule_ids),
                                }
                                for segment, analysis in zip(segments, top_analyses)
                            ],
                        },
                        "top_analysis_posterior": top_posterior,
                        "top_analysis_lexical_forms": top_forms,
                        "target_gold_lexical_form_posterior": None,
                        "target_gold_lexical_form_posterior_reason": _GOLD_POSTERIOR_REASON,
                        "target_top_analysis": localized,
                        "target_localization_reason": localization_reason,
                        "target_whole_form_posterior": None,
                        "target_whole_form_posterior_reason": (
                            "Exact piece usage is aggregated by host form, not target occurrence."
                        ),
                        "target_transformed_boundary_posterior": None,
                        "target_transformed_boundary_posterior_reason": (
                            _TARGET_TRANSFORM_REASON
                        ),
                        "sentence_expected_transformed_events": sum(
                            inference.expected_transformed_sandhi_events
                            for inference in results
                        ),
                        "multiple_target_occurrences": len(matches) > 1,
                        "ambiguous_target_surface_location": len(locations) != 1,
                    }
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        summary = {
            "target_id": source.target_id,
            "level": source.level,
            "challenge_sentences": len(challenge_rows),
            "target_occurrences": occurrences,
            "evaluable_target_occurrences": evaluable,
            "exact_lexical_recovery_posterior_mean": None,
            "exact_lexical_recovery_posterior_denominator": 0,
            "exact_lexical_recovery_posterior_reason": _GOLD_POSTERIOR_REASON,
            "top1_lexical_recovery_rate": (
                recovered / evaluable if evaluable else None
            ),
            "top1_lexical_recovery_denominator": evaluable,
            "mean_target_whole_form_posterior": None,
            "mean_target_whole_form_posterior_denominator": 0,
            "mean_target_top1_whole_form_use": (
                top_whole / evaluable if evaluable else None
            ),
            "mean_target_top1_piece_count": (
                top_piece_count / evaluable if evaluable else None
            ),
            "target_top1_piece_metric_denominator": evaluable,
            "target_piece_identity_expected_usage": None,
            "target_piece_identity_expected_usage_reason": (
                "Exact piece marginals are not target-occurrence-local."
            ),
            "target_local_transformed_sandhi": None,
            "target_local_transformed_sandhi_reason": _TARGET_TRANSFORM_REASON,
        }
        _write_json(run_dir / "challenge_summary.json", summary)
        return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnostic-only S1M2 lexeme evidence probe (not frozen M0)."
    )
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--level", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--sandhi-transformation-penalty", type=float, default=1.0)
    parser.add_argument("--piece-boundary-probability", type=float, default=0.4)
    parser.add_argument("--extra-challenge", type=Path)
    parser.add_argument(
        "--extra-gold",
        type=Path,
        help="Optional aligned JSONL with text and matches for --extra-challenge.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.extra_gold is not None and args.extra_challenge is None:
        raise ValueError("--extra-gold requires --extra-challenge")
    corpus = args.corpus.resolve(strict=True)
    challenge = args.challenge.resolve(strict=True)
    extra = None if args.extra_challenge is None else args.extra_challenge.resolve(strict=True)
    extra_gold = None if args.extra_gold is None else args.extra_gold.resolve(strict=True)
    challenge_sha256 = _file_sha256(challenge)
    rows = _read_challenge(challenge)
    if _file_sha256(challenge) != challenge_sha256:
        raise RuntimeError("Challenge changed while loading metadata.")
    if any(row.get("target_id", args.target_id) != args.target_id for row in rows):
        raise ValueError("Challenge target_id does not match --target-id.")
    extra_sha256 = None if extra is None else _file_sha256(extra)
    extra_gold_sha256 = None if extra_gold is None else _file_sha256(extra_gold)
    if extra is not None:
        rows.extend(_read_extra_challenge(extra, extra_gold))
        if _file_sha256(extra) != extra_sha256 or (
            extra_gold is not None and _file_sha256(extra_gold) != extra_gold_sha256
        ):
            raise RuntimeError("Extra challenge changed while loading metadata.")
    _validate_held_out(corpus, rows)
    source = DiagnosticCorpusSource(
        corpus=corpus,
        corpus_sha256=_file_sha256(corpus),
        challenge=challenge,
        challenge_sha256=challenge_sha256,
        target_id=args.target_id,
        level=args.level,
        extra_challenge=extra,
        extra_challenge_sha256=extra_sha256,
        extra_gold=extra_gold,
        extra_gold_sha256=extra_gold_sha256,
    )
    run_id = args.run_id or (
        f"diag_{args.target_id}_{args.level}_{source.identity_sha256()[:12]}"
    )
    config = TrainingConfig(
        manifest=Path("diagnostic/no_formal_manifest"),
        output_root=args.output_root,
        run_id=run_id,
        model=S1M2_MODEL,
        script="iast",
        condition="surface_word",
        passes=args.passes,
        workers=args.workers,
        sandhi_transformation_penalty=args.sandhi_transformation_penalty,
        piece_boundary_probability=args.piece_boundary_probability,
    )
    result = run_training(
        config,
        stop_after_training=True,
        _diagnostic_source=source,
    )
    if len(result.history) != config.passes:
        raise RuntimeError("Held-out inference requires every training pass to finish.")
    if _file_sha256(corpus) != source.corpus_sha256 or _file_sha256(challenge) != source.challenge_sha256:
        raise RuntimeError("Diagnostic input changed during training.")
    if extra is not None and _file_sha256(extra) != source.extra_challenge_sha256:
        raise RuntimeError("Extra challenge changed during training.")
    if extra_gold is not None and _file_sha256(extra_gold) != source.extra_gold_sha256:
        raise RuntimeError("Extra gold changed during training.")
    summary = evaluate_challenge(
        config=config,
        run_dir=result.run_dir,
        source=source,
        challenge_rows=rows,
    )
    print(f"run artifacts: {result.run_dir}")
    print(f"held-out sentences: {summary['challenge_sentences']}")
    print(f"training git commit: {_git_commit(Path('.').resolve())}")


if __name__ == "__main__":
    main()

"""Diagnostic-only S1M2 training followed by held-out exact inspection."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

from sktlm.latent.frontend import iter_observed_segments
from sktlm.latent.grammar import StructuredSandhiGrammar
from sktlm.latent.lazy_candidates import build_lazy_candidate_graph
from sktlm.latent.phonology import parse_iast_form
from sktlm.latent.store import PieceStoreScorer
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.latent.training import (
    DiagnosticCorpusSource,
    S1M2_MODEL,
    S1M2_MODELS,
    S1M2_REUSABLE_PIECES_V3,
    TrainingConfig,
    _file_sha256,
    _config_signature,
    _git_commit,
    _write_json,
    run_training,
)
from sktlm.pieces.composed import ComposedPieceInference, infer_composed_segment
from sktlm.experiments.training.s1m2_lexeme_alignment import (
    DCS_SOURCE_ROOT,
    fallback_unique_surface_location,
    locate_dcs_occurrences,
    top_factor_groups,
)


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
    artifact_version: int = 1,
    dcs_root: Path = DCS_SOURCE_ROOT,
    artifact_dir: Path | None = None,
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
            objective_model=config.model,
        )
        engine = ComposedPieceInference(
            scorer,
            model_config=config.piece_model_config,
            cache_config=config.piece_cache_config,
            inspection_top_k=config.analysis_top_k,
        )
        grammar = StructuredSandhiGrammar.from_default_inventory()
        if artifact_version not in (1, 2):
            raise ValueError("Unsupported challenge artifact version.")
        suffix = "" if artifact_version == 1 else ".v2"
        destination = run_dir if artifact_dir is None else artifact_dir
        if artifact_dir is not None:
            destination.mkdir(parents=True, exist_ok=True)
        output = destination / f"challenge_analyses{suffix}.jsonl"
        summary_path = destination / f"challenge_summary{suffix}.json"
        if artifact_version == 2 and (output.exists() or summary_path.exists()):
            raise FileExistsError("Versioned challenge reevaluation already exists.")
        occurrences = 0
        evaluable = 0
        recovered = 0
        top_whole = 0
        top_piece_count = 0
        piece_evaluable = 0
        unscorable_reasons: Counter[str] = Counter()
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
                dcs_locations, dcs_occ_ids, dcs_location_errors, dcs_error = locate_dcs_occurrences(
                    row, segments, dcs_root=dcs_root
                )
                factor_groups = [
                    top_factor_groups(segment, analysis)
                    for segment, analysis in zip(segments, top_analyses)
                ]
                for match_index, match in enumerate(matches or [None]):
                    if match is not None:
                        occurrences += 1
                    gold, gold_reason = (
                        _gold_form(match) if match is not None else (None, "No target match metadata.")
                    )
                    form = None if match is None else match["form"]
                    location = None
                    localized = None
                    localization_reason = None
                    if match is not None:
                        if dcs_error == "dcs_source_metadata_missing":
                            location, localization_reason = fallback_unique_surface_location(
                                match, segments
                            )
                        elif dcs_error is not None:
                            localization_reason = dcs_error
                        else:
                            try:
                                dcs_id = int(match["id"])
                            except (KeyError, TypeError, ValueError):
                                localization_reason = "dcs_target_id_invalid"
                            else:
                                if dcs_id not in dcs_occ_ids:
                                    localization_reason = "dcs_target_id_not_found"
                                elif (
                                    match.get("occ_id") is not None
                                    and str(match["occ_id"]) != dcs_occ_ids[dcs_id]
                                ):
                                    localization_reason = "dcs_occ_id_mismatch"
                                else:
                                    location = dcs_locations.get(dcs_id)
                                    if location is None:
                                        localization_reason = dcs_location_errors.get(
                                            dcs_id, "dcs_target_span_unavailable"
                                        )
                    if location is not None:
                        segment_index = location.segment_index
                        groups, group_error = factor_groups[segment_index]
                        if groups is None:
                            localization_reason = group_error
                        else:
                            analysis = top_analyses[segment_index]
                            factors = groups[location.token_index]
                            selected: tuple[int, ...] | None = None
                            if location.component_count == 1:
                                selected = factors
                            elif len(factors) == location.component_count:
                                selected = (factors[location.component_index],)
                            elif len(factors) == 1:
                                # One predicted factor merges several DCS components.
                                # Its target recovery is deterministically false.
                                selected = factors
                            else:
                                localization_reason = "dcs_component_factor_alignment_ambiguous"
                            if selected is not None and (
                                location.component_count == 1 and len(selected) == 1
                                or location.component_count > 1
                                and len(factors) == location.component_count
                            ):
                                factor_index = selected[0]
                                pieces = analysis.piece_segmentations[factor_index]
                                localized = {
                                    "lexical_form": analysis.words[factor_index].iast,
                                    "pieces": [piece.iast for piece in pieces],
                                    "piece_count": len(pieces),
                                    "whole_form": len(pieces) == 1,
                                }
                            elif selected is not None:
                                localized = {
                                    "lexical_form": None,
                                    "pieces": [],
                                    "piece_count": None,
                                    "whole_form": False,
                                    "factor_forms": [
                                        analysis.words[index].iast for index in selected
                                    ],
                                    "alignment_kind": (
                                        "merged_gold_components"
                                        if location.component_count > 1
                                        else "fragmented_gold_token"
                                    ),
                                }
                    if localized is not None and gold is not None:
                        evaluable += 1
                        recovered += localized["lexical_form"] == gold
                        top_whole += localized["whole_form"]
                        if localized["piece_count"] is not None:
                            top_piece_count += localized["piece_count"]
                            piece_evaluable += 1
                    elif match is not None:
                        unscorable_reasons[
                            gold_reason or localization_reason or "unknown_unscorable_reason"
                        ] += 1
                    record = {
                        "localization_schema_version": 2,
                        "target_id": source.target_id,
                        "level": source.level,
                        "sentence_index": sentence_index,
                        "match_index": match_index if match is not None else None,
                        "sentence_text": text,
                        "dcs_target_form": form,
                        "dcs_id": None if match is None else match.get("id"),
                        "dcs_occ_id": None if match is None else match.get("occ_id"),
                        "gold_surface_location": (
                            None if location is None else {
                                "source_start": location.source_start,
                                "source_end": location.source_end,
                                "segment_index": location.segment_index,
                                "token_index": location.token_index,
                                "component_index": location.component_index,
                                "component_count": location.component_count,
                                "method": location.method,
                            }
                        ),
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
                        "top1_lexical_recovered": (
                            None if localized is None or gold is None
                            else localized["lexical_form"] == gold
                        ),
                        "target_top1_piece_metric_evaluable": (
                            localized is not None
                            and gold is not None
                            and localized["piece_count"] is not None
                        ),
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
                        "ambiguous_target_surface_location": location is None,
                    }
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        summary = {
            "target_id": source.target_id,
            "level": source.level,
            "challenge_sentences": len(challenge_rows),
            "target_occurrences": occurrences,
            "evaluable_target_occurrences": evaluable,
            "unscorable_target_occurrences": occurrences - evaluable,
            "unscorable_reasons": dict(sorted(unscorable_reasons.items())),
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
                top_piece_count / piece_evaluable if piece_evaluable else None
            ),
            "target_top1_piece_metric_denominator": piece_evaluable,
            "target_piece_identity_expected_usage": None,
            "target_piece_identity_expected_usage_reason": (
                "Exact piece marginals are not target-occurrence-local."
            ),
            "target_local_transformed_sandhi": None,
            "target_local_transformed_sandhi_reason": _TARGET_TRANSFORM_REASON,
        }
        _write_json(summary_path, summary)
        return summary


def reevaluate_existing_run(
    run_dir: Path,
    *,
    dcs_root: Path = DCS_SOURCE_ROOT,
) -> dict[str, Any]:
    """Evaluate a completed diagnostic checkpoint without trainer invocation."""

    run_dir = run_dir.resolve(strict=True)
    config_path = run_dir / "config.json"
    provenance_path = run_dir / "provenance.json"
    checkpoint_path = run_dir / "checkpoint.json"
    original_analyses = run_dir / "challenge_analyses.jsonl"
    original_summary = run_dir / "challenge_summary.json"
    evaluation_provenance = run_dir / "challenge_evaluation.v2.provenance.json"
    if evaluation_provenance.exists():
        raise FileExistsError(evaluation_provenance)
    for path in (
        config_path,
        provenance_path,
        checkpoint_path,
        original_analyses,
        original_summary,
        run_dir / "learner.sqlite",
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    stored_config = json.loads(config_path.read_text(encoding="utf-8"))
    config_fields = dict(stored_config)
    for name in ("manifest", "output_root", "document_list"):
        if config_fields.get(name) is not None:
            config_fields[name] = Path(config_fields[name])
    config = TrainingConfig(**config_fields)
    if config.model not in S1M2_MODELS or config.payload() != stored_config:
        raise ValueError("Stored diagnostic scientific configuration is invalid.")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if (
        provenance.get("source_kind") != "diagnostic_s1m2_lexeme_probe"
        or provenance.get("formal_manifest_used") is not False
        or provenance.get("config_signature") != _config_signature(config)
    ):
        raise ValueError("Run is not this diagnostic S1M2 checkpoint identity.")
    if _file_sha256(Path(provenance["rules_path"])) != provenance["rules_sha256"]:
        raise ValueError("The frozen sandhi inventory differs from training.")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if (
        checkpoint.get("active_pass") is not None
        or int(checkpoint.get("completed_passes", 0)) != config.passes
    ):
        raise ValueError("Diagnostic training passes are not complete.")
    source = DiagnosticCorpusSource(
        corpus=Path(provenance["corpus"]),
        corpus_sha256=provenance["corpus_sha256"],
        challenge=Path(provenance["challenge"]),
        challenge_sha256=provenance["challenge_sha256"],
        target_id=provenance["target_id"],
        level=provenance["level"],
        extra_challenge=(
            None if provenance.get("extra_challenge") is None
            else Path(provenance["extra_challenge"])
        ),
        extra_challenge_sha256=provenance.get("extra_challenge_sha256"),
        extra_gold=(
            None if provenance.get("extra_gold") is None
            else Path(provenance["extra_gold"])
        ),
        extra_gold_sha256=provenance.get("extra_gold_sha256"),
    )
    if source.identity_sha256() != provenance.get("diagnostic_input_signature"):
        raise ValueError("Stored diagnostic input signature differs.")
    for path, digest in (
        (source.corpus, source.corpus_sha256),
        (source.challenge, source.challenge_sha256),
        (source.extra_challenge, source.extra_challenge_sha256),
        (source.extra_gold, source.extra_gold_sha256),
    ):
        if path is not None and _file_sha256(path) != digest:
            raise ValueError(f"Diagnostic input changed: {path}")
    rows = _read_challenge(source.challenge)
    if source.extra_challenge is not None:
        rows.extend(_read_extra_challenge(source.extra_challenge, source.extra_gold))
    source_root = dcs_root.resolve()
    dcs_files: dict[str, str] = {}
    for row in rows:
        source_file = row.get("source_file")
        if not isinstance(source_file, str):
            continue
        path = (source_root / source_file.replace("\\", "/")).resolve()
        if path.is_relative_to(source_root) and path.is_file():
            dcs_files[path.as_posix()] = _file_sha256(path)
    summary = evaluate_challenge(
        config=config,
        run_dir=run_dir,
        source=source,
        challenge_rows=rows,
        artifact_version=2,
        dcs_root=source_root,
    )
    if any(_file_sha256(Path(path)) != digest for path, digest in dcs_files.items()):
        raise RuntimeError("DCS source changed during reevaluation.")
    _write_json(
        evaluation_provenance,
        {
            "schema_version": 2,
            "evaluation_kind": "diagnostic_heldout_target_localization",
            "evaluation_git_commit": _git_commit(Path(".").resolve()),
            "training_git_commit": provenance["training_git_commit"],
            "training_provenance_sha256": _file_sha256(provenance_path),
            "training_config_sha256": _file_sha256(config_path),
            "training_checkpoint_sha256": _file_sha256(checkpoint_path),
            "diagnostic_input_signature": source.identity_sha256(),
            "challenge_sha256": source.challenge_sha256,
            "rules_sha256": provenance["rules_sha256"],
            "original_analyses_sha256": _file_sha256(original_analyses),
            "original_summary_sha256": _file_sha256(original_summary),
            "dcs_source_files_sha256": dict(sorted(dcs_files.items())),
            "analyses_sha256": _file_sha256(run_dir / "challenge_analyses.v2.jsonl"),
            "summary_sha256": _file_sha256(run_dir / "challenge_summary.v2.json"),
        },
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnostic-only S1M2 lexeme evidence probe (not frozen M0)."
    )
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--challenge", type=Path)
    parser.add_argument("--target-id")
    parser.add_argument("--level")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--reevaluate-run-dir",
        type=Path,
        help="Read a completed diagnostic checkpoint; do not run training.",
    )
    parser.add_argument("--dcs-root", type=Path, default=DCS_SOURCE_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--model",
        choices=(S1M2_MODEL, S1M2_REUSABLE_PIECES_V3),
        help="Reusable-piece objective version; defaults to the historical V2 probe.",
    )
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
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.reevaluate_run_dir is not None:
        if any(
            value is not None
            for value in (
                args.corpus,
                args.challenge,
                args.target_id,
                args.level,
                args.output_root,
                args.run_id,
                args.model,
                args.extra_challenge,
                args.extra_gold,
            )
        ):
            parser.error("--reevaluate-run-dir uses stored training inputs only.")
        summary = reevaluate_existing_run(
            args.reevaluate_run_dir, dcs_root=args.dcs_root
        )
        print(f"evaluable: {summary['evaluable_target_occurrences']}")
        print(f"unscorable reasons: {summary['unscorable_reasons']}")
        return
    for name in ("corpus", "challenge", "target_id", "level", "output_root"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required for training.")
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
        model=args.model or S1M2_MODEL,
        script="iast",
        condition="surface_word",
        passes=args.passes,
        workers=args.workers,
        sandhi_transformation_penalty=args.sandhi_transformation_penalty,
        piece_boundary_probability=args.piece_boundary_probability,
        piece_role_diagnostics=(args.model == S1M2_REUSABLE_PIECES_V3),
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
        dcs_root=args.dcs_root,
    )
    print(f"run artifacts: {result.run_dir}")
    print(f"held-out sentences: {summary['challenge_sentences']}")
    print(f"training git commit: {_git_commit(Path('.').resolve())}")


if __name__ == "__main__":
    main()

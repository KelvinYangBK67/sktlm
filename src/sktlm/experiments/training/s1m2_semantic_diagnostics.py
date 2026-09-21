"""Read-only held-out semantic diagnostics for completed S1M2 V2 probes."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sktlm.experiments.training.s1m2_lexeme_alignment import DCS_SOURCE_ROOT
from sktlm.latent.phonology import normalize_iast, parse_iast_form
from sktlm.latent.training import (
    S1M2_MODEL,
    TrainingConfig,
    _config_signature,
    _file_sha256,
    _git_commit,
)


SEMANTIC_SCHEMA_VERSION = 3
ANALYSES_NAME = "challenge_semantic_diagnostics.v3.jsonl"
SUMMARY_NAME = "challenge_semantic_summary.v3.json"
PROVENANCE_NAME = "challenge_semantic_diagnostics.v3.provenance.json"
TRAINING_GOLD_SIDECAR_NAME = "training_gold_wordforms.v1.json"
_PROTECTED_RUN_FILES = (
    "challenge_analyses.jsonl",
    "challenge_summary.json",
    "config.json",
    "checkpoint.json",
    "provenance.json",
    "learner.sqlite",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            rows.append(value)
    if not rows:
        raise ValueError(f"JSONL is empty: {path}")
    return rows


def _write_json_new(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _misc(value: str) -> dict[str, str]:
    return {
        key: item
        for part in value.split("|")
        if "=" in part
        for key, item in [part.split("=", 1)]
    }


def _dcs_blocks(path: Path) -> list[tuple[dict[str, str], list[dict[str, Any]]]]:
    result: list[tuple[dict[str, str], list[dict[str, Any]]]] = []
    block: list[str] = []

    def append_block() -> None:
        metadata: dict[str, str] = {}
        tokens: list[dict[str, Any]] = []
        for line in block:
            if line.startswith("# ") and " = " in line:
                key, value = line[2:].split(" = ", 1)
                metadata[key.strip()] = value.strip()
                continue
            columns = line.split("\t")
            if len(columns) < 10 or not columns[0].isdigit():
                continue
            misc = _misc(columns[9])
            raw = misc.get("Unsandhied")
            canonical: str | None = None
            unavailable_reason: str | None = None
            if raw is None or not raw.strip() or raw.strip() == "_":
                unavailable_reason = "dcs_unsandhied_missing"
            else:
                try:
                    canonical = parse_iast_form(raw.strip()).iast
                except ValueError:
                    unavailable_reason = "dcs_unsandhied_invalid_iast"
            tokens.append(
                {
                    "dcs_id": int(columns[0]),
                    "occ_id": misc.get("OccId"),
                    "dcs_form": columns[1],
                    "dcs_unsandhied_raw": raw,
                    "gold_wordform": canonical,
                    "gold_unavailable_reason": unavailable_reason,
                }
            )
        result.append((metadata, tokens))

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if line:
                block.append(line)
            elif block:
                append_block()
                block.clear()
    if block:
        append_block()
    return result


def _gold_sequence(tokens: Sequence[Mapping[str, Any]]) -> tuple[str | None, ...]:
    return tuple(
        None if token.get("gold_wordform") is None else str(token["gold_wordform"])
        for token in tokens
    )


def build_training_gold_inventory(
    *,
    corpus: Path,
    selection: Path,
    dcs_root: Path = DCS_SOURCE_ROOT,
) -> dict[str, Any]:
    """Reconstruct exact DCS-gold membership for a selected training corpus."""

    corpus = corpus.resolve(strict=True)
    selection = selection.resolve(strict=True)
    root = dcs_root.resolve(strict=True)
    selection_rows = _read_jsonl(selection)
    corpus_texts = [
        line for line in corpus.read_text(encoding="utf-8").splitlines() if line
    ]
    selected_texts = [row.get("text") for row in selection_rows]
    if any(not isinstance(text, str) or not text for text in selected_texts):
        raise ValueError("Training selection rows require nonempty text.")
    if sorted(selected_texts) != sorted(corpus_texts):
        raise ValueError("Training selection text multiset does not match corpus.txt.")

    block_cache: dict[Path, list[tuple[dict[str, str], list[dict[str, Any]]]]] = {}
    dcs_hashes: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    inventory: set[str] = set()
    unavailable = Counter()
    mapping_status = Counter()
    for selection_index, row in enumerate(selection_rows):
        source_file = row.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            raise ValueError(f"Training selection row {selection_index} lacks source_file.")
        path = (root / source_file.replace("\\", "/")).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Invalid DCS source path in selection: {source_file}")
        if path not in block_cache:
            block_cache[path] = _dcs_blocks(path)
            dcs_hashes[path.as_posix()] = _file_sha256(path)
        normalized_text = normalize_iast(str(row["text"]).strip())
        matches = [
            (metadata, tokens)
            for metadata, tokens in block_cache[path]
            if normalize_iast(metadata.get("text", "").strip()) == normalized_text
        ]
        if not matches:
            raise ValueError(
                f"Selected training sentence not found in DCS: {source_file} #{selection_index}"
            )
        sequences = {_gold_sequence(tokens) for _metadata, tokens in matches}
        if len(sequences) != 1:
            raise ValueError(
                "Training sentence maps to DCS candidates with different gold "
                f"wordforms: {source_file} #{selection_index}"
            )
        tokens = matches[0][1]
        status = (
            "unique_dcs_sentence"
            if len(matches) == 1
            else "gold_equivalent_multiple_dcs_sentences"
        )
        mapping_status[status] += 1
        for token in tokens:
            gold = token["gold_wordform"]
            if gold is None:
                unavailable[str(token["gold_unavailable_reason"])] += 1
            else:
                inventory.add(str(gold))
        records.append(
            {
                "selection_index": selection_index,
                "surface_text": row["text"],
                "source_file": source_file,
                "mapping_status": status,
                "candidate_sentence_identities": [
                    {
                        "sent_id": metadata.get("sent_id"),
                        "token_occ_ids": [token.get("occ_id") for token in candidate],
                    }
                    for metadata, candidate in matches
                ],
                "tokens": [
                    {
                        "dcs_id": token["dcs_id"],
                        "dcs_form": token["dcs_form"],
                        "dcs_unsandhied_raw": token["dcs_unsandhied_raw"],
                        "gold_wordform": token["gold_wordform"],
                        "gold_unavailable_reason": token["gold_unavailable_reason"],
                    }
                    for token in tokens
                ],
            }
        )
    if any(_file_sha256(Path(path)) != digest for path, digest in dcs_hashes.items()):
        raise RuntimeError("A DCS source changed during training-gold reconstruction.")
    return {
        "schema_version": 1,
        "inventory_semantics": (
            "membership in canonical valid IAST values explicitly stored in DCS "
            "integer-token Unsandhied fields for the exact selected training sentences"
        ),
        "corpus": corpus.as_posix(),
        "corpus_sha256": _file_sha256(corpus),
        "selection": selection.as_posix(),
        "selection_sha256": _file_sha256(selection),
        "selected_sentences": len(records),
        "mapping_status_counts": dict(sorted(mapping_status.items())),
        "gold_wordforms": sorted(inventory),
        "distinct_gold_wordforms": len(inventory),
        "gold_unavailable_tokens": sum(unavailable.values()),
        "gold_unavailable_reasons": dict(sorted(unavailable.items())),
        "dcs_source_files_sha256": dict(sorted(dcs_hashes.items())),
        "records": records,
    }


def write_training_gold_inventory(
    *,
    corpus: Path,
    selection: Path,
    sidecar: Path,
    dcs_root: Path = DCS_SOURCE_ROOT,
) -> dict[str, Any]:
    payload = build_training_gold_inventory(
        corpus=corpus, selection=selection, dcs_root=dcs_root
    )
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    _write_json_new(sidecar, payload)
    return payload


def _validate_training_gold_inventory(
    payload: Mapping[str, Any], *, corpus: Path, selection: Path
) -> frozenset[str]:
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported training-gold inventory schema.")
    if payload.get("corpus_sha256") != _file_sha256(corpus):
        raise ValueError("Training-gold inventory corpus hash differs.")
    if payload.get("selection_sha256") != _file_sha256(selection):
        raise ValueError("Training-gold inventory selection hash differs.")
    hashes = payload.get("dcs_source_files_sha256")
    if not isinstance(hashes, dict) or any(
        not isinstance(path, str)
        or not isinstance(digest, str)
        or not Path(path).is_file()
        or _file_sha256(Path(path)) != digest
        for path, digest in hashes.items()
    ):
        raise ValueError("Training-gold inventory DCS source hashes differ.")
    forms = payload.get("gold_wordforms")
    if not isinstance(forms, list) or any(not isinstance(form, str) for form in forms):
        raise ValueError("Training-gold inventory wordforms are invalid.")
    return frozenset(forms)


def read_piece_lexicon_values(
    database: Path, piece_forms: Iterable[str]
) -> tuple[dict[str, dict[str, float] | None], bool]:
    """Read only the held-out top-1 pieces from authoritative V2 state."""

    requested = sorted(set(piece_forms))
    values: dict[str, dict[str, float] | None] = {piece: None for piece in requested}
    uri = database.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        query_only = int(connection.execute("PRAGMA query_only").fetchone()[0]) == 1
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(piece_lexicon)")
        }
        required = {
            "form_key", "raw_expected_count", "max_host_expected_usage", "reusable_count"
        }
        if not required <= columns:
            raise ValueError("Completed learner is not S1M2 V2 C/M/R state.")
        for piece in requested:
            key = parse_iast_form(piece).key
            row = connection.execute(
                "SELECT raw_expected_count, max_host_expected_usage, reusable_count "
                "FROM piece_lexicon WHERE form_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                values[piece] = {
                    "raw_expected_count": float(row[0]),
                    "max_host_expected_usage": float(row[1]),
                    "reusable_count": float(row[2]),
                }
    return values, query_only


def _metric_bucket() -> dict[str, Any]:
    return {
        "target_occurrences": 0,
        "evaluable_occurrences": 0,
        "top1_lexical_recovery_numerator": 0,
        "top1_lexical_recovery_denominator": 0,
        "piece_count_sum": 0,
        "mean_top1_piece_count_denominator": 0,
        "whole_form_sum": 0,
        "mean_top1_whole_form_use_denominator": 0,
        "unscorable_reasons": Counter(),
        "piece_metric_unavailable_reasons": Counter(),
    }


def _finish_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    recovery_denominator = int(bucket["top1_lexical_recovery_denominator"])
    piece_denominator = int(bucket["mean_top1_piece_count_denominator"])
    return {
        "target_occurrences": int(bucket["target_occurrences"]),
        "evaluable_occurrences": int(bucket["evaluable_occurrences"]),
        "top1_lexical_recovery_numerator": int(
            bucket["top1_lexical_recovery_numerator"]
        ),
        "top1_lexical_recovery_denominator": recovery_denominator,
        "top1_lexical_recovery_rate": (
            bucket["top1_lexical_recovery_numerator"] / recovery_denominator
            if recovery_denominator else None
        ),
        "mean_top1_piece_count": (
            bucket["piece_count_sum"] / piece_denominator if piece_denominator else None
        ),
        "mean_top1_piece_count_denominator": piece_denominator,
        "mean_top1_whole_form_use": (
            bucket["whole_form_sum"] / piece_denominator if piece_denominator else None
        ),
        "mean_top1_whole_form_use_denominator": int(
            bucket["mean_top1_whole_form_use_denominator"]
        ),
        "unscorable_occurrences": sum(bucket["unscorable_reasons"].values()),
        "unscorable_reasons": dict(sorted(bucket["unscorable_reasons"].items())),
        "piece_metric_unavailable_occurrences": sum(
            bucket["piece_metric_unavailable_reasons"].values()
        ),
        "piece_metric_unavailable_reasons": dict(
            sorted(bucket["piece_metric_unavailable_reasons"].items())
        ),
    }


def analyze_semantic_records(
    records: Sequence[Mapping[str, Any]],
    *,
    training_gold_wordforms: frozenset[str],
    piece_values: Mapping[str, dict[str, float] | None],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compute held-out top-1 descriptive #3 and exact-membership #5 metrics."""

    buckets = {
        "overall": _metric_bucket(),
        "seen_exact_gold_wordform_in_training": _metric_bucket(),
        "unseen_exact_gold_wordform_in_training": _metric_bucket(),
    }
    piece_usage: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "wrong_occurrences": 0,
            "wrong_piece_token_uses": 0,
            "wrong_hosts": set(),
            "correct_occurrences": 0,
            "correct_piece_token_uses": 0,
            "correct_hosts": set(),
        }
    )
    diagnostics: list[dict[str, Any]] = []
    correct_occurrences = 0
    wrong_occurrences = 0
    wrong_single_host_occurrences = 0
    for record in records:
        if record.get("localization_schema_version") != 2:
            raise ValueError("Semantic diagnostics require DCS structural localization v2.")
        gold = record.get("dcs_unsandhied_gold_form")
        if not isinstance(gold, str) or not gold:
            raise ValueError("Seen/unseen classification requires DCS Unsandhied gold.")
        stratum = (
            "seen_exact_gold_wordform_in_training"
            if gold in training_gold_wordforms
            else "unseen_exact_gold_wordform_in_training"
        )
        target = record.get("target_top_analysis")
        target = target if isinstance(target, dict) else None
        predicted = None if target is None else target.get("lexical_form")
        predicted = predicted if isinstance(predicted, str) else None
        raw_pieces = [] if target is None else target.get("pieces", [])
        pieces = [piece for piece in raw_pieces if isinstance(piece, str)]
        recovered = record.get("top1_lexical_recovered")
        if recovered not in (True, False, None):
            raise ValueError("top1_lexical_recovered must be boolean or null.")
        piece_count = None if target is None else target.get("piece_count")
        piece_evaluable = isinstance(piece_count, int) and piece_count >= 1
        reason = record.get("target_localization_reason")
        if recovered is None:
            unscorable_reason = (
                str(record.get("gold_unavailable_reason"))
                if record.get("gold_unavailable_reason")
                else str(reason or "unknown_unscorable_reason")
            )
        else:
            unscorable_reason = None
        alignment_kind = None if target is None else target.get("alignment_kind")
        piece_unavailable_reason = (
            None
            if piece_evaluable or recovered is None
            else str(alignment_kind or "top1_piece_segmentation_unavailable")
        )
        for name in ("overall", stratum):
            bucket = buckets[name]
            bucket["target_occurrences"] += 1
            if recovered is None:
                bucket["unscorable_reasons"][unscorable_reason] += 1
            else:
                bucket["evaluable_occurrences"] += 1
                bucket["top1_lexical_recovery_denominator"] += 1
                bucket["top1_lexical_recovery_numerator"] += int(recovered)
                if piece_evaluable:
                    bucket["piece_count_sum"] += int(piece_count)
                    bucket["mean_top1_piece_count_denominator"] += 1
                    bucket["whole_form_sum"] += int(bool(target.get("whole_form")))
                    bucket["mean_top1_whole_form_use_denominator"] += 1
                else:
                    bucket["piece_metric_unavailable_reasons"][
                        piece_unavailable_reason
                    ] += 1
        if recovered is True:
            correct_occurrences += 1
        elif recovered is False:
            wrong_occurrences += 1
            if predicted is not None:
                wrong_single_host_occurrences += 1
        if recovered is not None and pieces:
            unique_pieces = set(pieces)
            for piece in unique_pieces:
                usage = piece_usage[piece]
                if recovered:
                    usage["correct_occurrences"] += 1
                    if predicted is not None:
                        usage["correct_hosts"].add(predicted)
                else:
                    usage["wrong_occurrences"] += 1
                    if predicted is not None:
                        usage["wrong_hosts"].add(predicted)
            for piece in pieces:
                field = (
                    "correct_piece_token_uses" if recovered else "wrong_piece_token_uses"
                )
                piece_usage[piece][field] += 1
        diagnostics.append(
            {
                "schema_version": SEMANTIC_SCHEMA_VERSION,
                "metric_semantics": {
                    "wrong_host_audit": "held_out_top1_descriptive_not_exact_posterior",
                    "seen_unseen": "exact_dcs_unsandhied_gold_wordform_membership",
                },
                "occurrence_identity": {
                    "target_id": record.get("target_id"),
                    "sentence_index": record.get("sentence_index"),
                    "match_index": record.get("match_index"),
                    "dcs_id": record.get("dcs_id"),
                    "dcs_occ_id": record.get("dcs_occ_id"),
                },
                "dcs_unsandhied_gold_wordform": gold,
                "dcs_target_surface_form": record.get("dcs_target_form"),
                "training_gold_wordform_stratum": stratum,
                "top1_predicted_lexical_wordform": predicted,
                "top1_factor_forms_when_no_single_host": (
                    target.get("factor_forms") if target is not None else None
                ),
                "top1_alignment_kind": alignment_kind,
                "top1_lexical_recovered": recovered,
                "top1_classification": (
                    "unscorable" if recovered is None else "correct" if recovered else "wrong"
                ),
                "unscorable_reason": unscorable_reason,
                "top1_piece_segmentation": pieces if piece_evaluable else None,
                "top1_piece_count": piece_count if piece_evaluable else None,
                "top1_whole_form_use": (
                    bool(target.get("whole_form")) if piece_evaluable else None
                ),
                "piece_metric_unavailable_reason": piece_unavailable_reason,
                "pieces_with_final_training_counts": [
                    {
                        "piece": piece,
                        "piece_lexicon_present": piece_values.get(piece) is not None,
                        **(
                            piece_values[piece]
                            if piece_values.get(piece) is not None else {
                                "raw_expected_count": None,
                                "max_host_expected_usage": None,
                                "reusable_count": None,
                            }
                        ),
                    }
                    for piece in pieces
                ],
            }
        )

    piece_rows: list[dict[str, Any]] = []
    for piece, usage in piece_usage.items():
        counts = piece_values.get(piece)
        wrong_hosts = sorted(usage["wrong_hosts"])
        correct_hosts = sorted(usage["correct_hosts"])
        reusable = None if counts is None else counts["reusable_count"]
        piece_rows.append(
            {
                "piece": piece,
                "wrong_target_occurrences": usage["wrong_occurrences"],
                "wrong_piece_token_uses": usage["wrong_piece_token_uses"],
                "distinct_wrong_predicted_host_forms": len(wrong_hosts),
                "wrong_predicted_host_forms": wrong_hosts,
                "correct_target_occurrences": usage["correct_occurrences"],
                "correct_piece_token_uses": usage["correct_piece_token_uses"],
                "distinct_correct_predicted_host_forms": len(correct_hosts),
                "correct_predicted_host_forms": correct_hosts,
                "piece_lexicon_present": counts is not None,
                "raw_expected_count": None if counts is None else counts["raw_expected_count"],
                "max_host_expected_usage": (
                    None if counts is None else counts["max_host_expected_usage"]
                ),
                "reusable_count": reusable,
                "coalition_candidate": len(wrong_hosts) >= 2 and reusable is not None and reusable > 0,
            }
        )
    wrong_piece_rows = [row for row in piece_rows if row["wrong_target_occurrences"] > 0]
    wrong_piece_rows.sort(
        key=lambda row: (
            -row["distinct_wrong_predicted_host_forms"],
            -row["wrong_target_occurrences"],
            row["piece"],
        )
    )
    candidates = [row for row in wrong_piece_rows if row["coalition_candidate"]]
    summary = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "metric_semantics": {
            "wrong_host_audit": (
                "held-out top-1 descriptive participation; final C/M/R are training "
                "state and do not establish that wrong hosts caused reusable count"
            ),
            "seen_unseen": (
                "membership of held-out exact DCS Unsandhied wordform in the exact "
                "selected-training DCS Unsandhied inventory; lemma and surface spelling ignored"
            ),
        },
        "wrong_host_coalition_audit": {
            "evaluable_occurrences": correct_occurrences + wrong_occurrences,
            "correct_host_occurrences": correct_occurrences,
            "wrong_host_occurrences": wrong_occurrences,
            "wrong_occurrences_with_single_predicted_host": wrong_single_host_occurrences,
            "pieces_appearing_in_wrong_predictions": len(wrong_piece_rows),
            "pieces_shared_by_at_least_two_distinct_wrong_predicted_hosts": sum(
                row["distinct_wrong_predicted_host_forms"] >= 2
                for row in wrong_piece_rows
            ),
            "coalition_candidates": len(candidates),
            "top_coalition_candidates": candidates,
            "all_wrong_prediction_pieces": wrong_piece_rows,
        },
        "unseen_exact_wordform_generalization": {
            name: _finish_bucket(bucket) for name, bucket in buckets.items()
        },
    }
    return diagnostics, summary


def _protected_hashes(run_dir: Path) -> dict[str, str]:
    paths = [run_dir / name for name in _PROTECTED_RUN_FILES]
    paths.extend(path for suffix in ("-wal", "-shm") if (path := run_dir / f"learner.sqlite{suffix}").exists())
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    return {path.name: _file_sha256(path) for path in paths}


def _validate_run(run_dir: Path) -> tuple[TrainingConfig, dict[str, Any], Path, Path]:
    config_path = run_dir / "config.json"
    provenance_path = run_dir / "provenance.json"
    checkpoint_path = run_dir / "checkpoint.json"
    stored = _read_json(config_path)
    fields = dict(stored)
    for name in ("manifest", "output_root", "document_list"):
        if fields.get(name) is not None:
            fields[name] = Path(fields[name])
    config = TrainingConfig(**fields)
    provenance = _read_json(provenance_path)
    checkpoint = _read_json(checkpoint_path)
    if config.model != S1M2_MODEL or config.payload() != stored:
        raise ValueError("Stored diagnostic configuration is not exact S1M2 V2.")
    if (
        provenance.get("source_kind") != "diagnostic_s1m2_lexeme_probe"
        or provenance.get("config_signature") != _config_signature(config)
    ):
        raise ValueError("Run provenance does not match the diagnostic configuration.")
    if checkpoint.get("active_pass") is not None or int(
        checkpoint.get("completed_passes", -1)
    ) != config.passes:
        raise ValueError("Diagnostic checkpoint is not complete.")
    corpus = Path(str(provenance["corpus"])).resolve(strict=True)
    challenge = Path(str(provenance["challenge"])).resolve(strict=True)
    if _file_sha256(corpus) != provenance.get("corpus_sha256"):
        raise ValueError("Training corpus hash differs from provenance.")
    if _file_sha256(challenge) != provenance.get("challenge_sha256"):
        raise ValueError("Challenge hash differs from provenance.")
    return config, provenance, corpus, challenge


def run_semantic_diagnostics(
    *,
    run_dir: Path,
    training_selection: Path,
    training_gold_sidecar: Path,
    dcs_root: Path = DCS_SOURCE_ROOT,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Create v3 diagnostics without inference, training, or existing-file writes."""

    run_dir = run_dir.resolve(strict=True)
    training_selection = training_selection.resolve(strict=True)
    sidecar_path = training_gold_sidecar.resolve()
    outputs = [run_dir / name for name in (ANALYSES_NAME, SUMMARY_NAME, PROVENANCE_NAME)]
    if any(path.exists() for path in outputs):
        raise FileExistsError("A v3 semantic diagnostic artifact already exists.")
    protected_before = _protected_hashes(run_dir)
    _config, provenance, corpus, challenge = _validate_run(run_dir)
    if sidecar_path.exists():
        sidecar = _read_json(sidecar_path)
    else:
        sidecar = write_training_gold_inventory(
            corpus=corpus,
            selection=training_selection,
            sidecar=sidecar_path,
            dcs_root=dcs_root,
        )
    inventory = _validate_training_gold_inventory(
        sidecar, corpus=corpus, selection=training_selection
    )
    analyses_path = run_dir / "challenge_analyses.jsonl"
    records = _read_jsonl(analyses_path)
    used_pieces = {
        piece
        for record in records
        for target in [record.get("target_top_analysis")]
        if isinstance(target, dict)
        for piece in target.get("pieces", [])
        if isinstance(piece, str)
    }
    piece_values, query_only = read_piece_lexicon_values(
        run_dir / "learner.sqlite", used_pieces
    )
    diagnostics, summary = analyze_semantic_records(
        records,
        training_gold_wordforms=inventory,
        piece_values=piece_values,
    )
    with outputs[0].open("x", encoding="utf-8", newline="\n") as handle:
        for row in diagnostics:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    _write_json_new(outputs[1], summary)
    protected_after = _protected_hashes(run_dir)
    if protected_after != protected_before:
        raise RuntimeError("Read-only diagnostics changed an existing run artifact.")
    challenge_rows = _read_jsonl(challenge)
    challenge_dcs_hashes: dict[str, str] = {}
    root = dcs_root.resolve(strict=True)
    for row in challenge_rows:
        source_file = row.get("source_file")
        if not isinstance(source_file, str):
            continue
        path = (root / source_file.replace("\\", "/")).resolve()
        if path.is_relative_to(root) and path.is_file():
            challenge_dcs_hashes[path.as_posix()] = _file_sha256(path)
    provenance_payload = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "evaluation_kind": "s1m2_v2_heldout_semantic_diagnostics",
        "evaluation_git_commit": _git_commit(repo_root.resolve()),
        "training_git_commit": provenance["training_git_commit"],
        "training_config_sha256": _file_sha256(run_dir / "config.json"),
        "training_provenance_sha256": _file_sha256(run_dir / "provenance.json"),
        "training_checkpoint_sha256": _file_sha256(run_dir / "checkpoint.json"),
        "learner_sqlite_sha256": protected_before["learner.sqlite"],
        "challenge_sha256": _file_sha256(challenge),
        "localized_analyses_sha256": _file_sha256(analyses_path),
        "training_gold_inventory_source": sidecar_path.as_posix(),
        "training_gold_inventory_sha256": _file_sha256(sidecar_path),
        "training_selection_source": training_selection.as_posix(),
        "training_selection_sha256": _file_sha256(training_selection),
        "training_dcs_source_files_sha256": sidecar["dcs_source_files_sha256"],
        "challenge_dcs_source_files_sha256": dict(sorted(challenge_dcs_hashes.items())),
        "sqlite_open_mode": "mode=ro",
        "sqlite_query_only_enforced": query_only,
        "trainer_invoked": False,
        "inference_invoked": False,
        "protected_run_artifacts_unchanged": True,
        "protected_run_artifacts_sha256": protected_before,
        "metric_semantics": summary["metric_semantics"],
        "diagnostics_sha256": _file_sha256(outputs[0]),
        "summary_sha256": _file_sha256(outputs[1]),
    }
    _write_json_new(outputs[2], provenance_payload)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only #3/#5 semantic diagnostics for completed S1M2 V2."
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--training-selection", type=Path, required=True)
    parser.add_argument("--training-gold-sidecar", type=Path, required=True)
    parser.add_argument("--dcs-root", type=Path, default=DCS_SOURCE_ROOT)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    summary = run_semantic_diagnostics(
        run_dir=args.run_dir,
        training_selection=args.training_selection,
        training_gold_sidecar=args.training_gold_sidecar,
        dcs_root=args.dcs_root,
    )
    audit = summary["wrong_host_coalition_audit"]
    strata = summary["unseen_exact_wordform_generalization"]
    print(f"wrong-host occurrences: {audit['wrong_host_occurrences']}")
    print(f"coalition candidates: {audit['coalition_candidates']}")
    print(json.dumps(strata, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

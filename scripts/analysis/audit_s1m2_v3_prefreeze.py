"""Reproduce the bounded S1M2 V3 pre-freeze forensic audit.

This command is a read-only consumer of the controlled DCS inputs and the
completed E000/E100 diagnostic runs.  It never invokes training or inference.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Iterable

from sktlm.latent.phonology import PhonologicalForm
from sktlm.pieces import cross_host_reusable_count


SCHEMA = "sktlm-s1m2-v3-prefreeze-audit/v1"
AUDIT_DATE = "2026-09-22"
RUNS = {
    "E000": "noun_high_deva_E000_v3_p3",
    "E100": "noun_high_deva_E100_v3_p3",
}
EXPECTED = {
    "model": "reusable_pieces_v3",
    "passes": 3,
    "workers": 1,
    "sandhi_transformation_penalty": 1.0,
    "piece_boundary_probability": 0.4,
    "piece_role_diagnostics": True,
    "training_git_commit": "9bd73b65b462284c3cd87f7daa38735664f41c1f",
    "challenge_sha256": "6f13a88fa49c0c05034f630cf63fb5ca7fa0ebd125c077e1f90dffc56d26ee59",
}
BIN_SPECS = (
    ("C=0", lambda value: value == 0.0),
    ("0<C<0.01", lambda value: 0.0 < value < 0.01),
    ("0.01<=C<0.1", lambda value: 0.01 <= value < 0.1),
    ("0.1<=C<1", lambda value: 0.1 <= value < 1.0),
    ("1<=C<10", lambda value: 1.0 <= value < 10.0),
    ("C>=10", lambda value: value >= 10.0),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.execute("PRAGMA query_only=ON")
    return connection


def _piece_row(
    form_key: str,
    c_value: float,
    q_value: float,
    maximum: float,
    reusable: float,
) -> dict[str, Any]:
    return {
        "piece": PhonologicalForm.from_key(form_key).iast,
        "form_key": form_key,
        "C": c_value,
        "Q": q_value,
        "M": maximum,
        "R_cross": reusable,
        "R_over_C": reusable / c_value if c_value > 0.0 else None,
        "effective_host_count": (
            c_value * c_value / q_value if q_value > 0.0 else None
        ),
    }


def _audit_moment_table(
    connection: sqlite3.Connection, table: str
) -> dict[str, Any]:
    role_column = ", role" if table == "piece_role_diagnostics" else ""
    maximum_column = (
        "max_host_expected_usage"
        if table == "piece_lexicon"
        else "NULL"
    )
    cursor = connection.execute(
        "SELECT form_key"
        + role_column
        + ", raw_expected_count, sum_host_support_squared, "
        + maximum_column
        + ", reusable_count FROM "
        + table
        + " ORDER BY form_key"
        + (", role" if role_column else "")
    )
    counts = collections.Counter()
    max_absolute = 0.0
    max_ulp_scale = 0.0
    for raw_row in cursor:
        offset = 1 if role_column else 0
        c_value = float(raw_row[1 + offset])
        q_value = float(raw_row[2 + offset])
        reusable = float(raw_row[4 + offset])
        counts["rows"] += 1
        if not all(math.isfinite(value) for value in (c_value, q_value, reusable)):
            counts["nonfinite_rows"] += 1
            continue
        if c_value < 0.0:
            counts["negative_C_rows"] += 1
        if q_value < 0.0:
            counts["negative_Q_rows"] += 1
        if c_value == 0.0 and q_value > 0.0:
            counts["C_zero_Q_positive_rows"] += 1
        try:
            expected = cross_host_reusable_count(c_value, q_value)
        except ValueError:
            counts["gross_bound_violation_rows"] += 1
            continue
        discrepancy = abs(reusable - expected)
        max_absolute = max(max_absolute, discrepancy)
        ulp = math.ulp(expected) if expected else math.ulp(0.0)
        max_ulp_scale = max(max_ulp_scale, discrepancy / ulp)
        if reusable != expected:
            counts["stored_recomputed_mismatch_rows"] += 1
    for name in (
        "rows",
        "nonfinite_rows",
        "negative_C_rows",
        "negative_Q_rows",
        "C_zero_Q_positive_rows",
        "gross_bound_violation_rows",
        "stored_recomputed_mismatch_rows",
    ):
        counts[name] += 0
    return {
        **dict(counts),
        "max_absolute_discrepancy": max_absolute,
        "max_ULP_scale_discrepancy": max_ulp_scale,
        "status": "PASS"
        if not any(
            counts[name]
            for name in counts
            if name != "rows"
        )
        else "FAIL",
    }


def _tail_audit(connection: sqlite3.Connection) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    ratios: dict[str, list[float]] = {name: [] for name, _ in BIN_SPECS}
    effective: dict[str, list[float]] = {name: [] for name, _ in BIN_SPECS}
    c_values: dict[str, list[float]] = {name: [] for name, _ in BIN_SPECS}
    r_values: dict[str, list[float]] = {name: [] for name, _ in BIN_SPECS}
    bins = {
        name: {"piece_types": 0, "C_total": 0.0, "R_cross_total": 0.0}
        for name, _ in BIN_SPECS
    }
    for form_key, c_value, q_value, maximum, reusable in connection.execute(
        "SELECT form_key, raw_expected_count, sum_host_support_squared, "
        "max_host_expected_usage, reusable_count FROM piece_lexicon "
        "ORDER BY form_key"
    ):
        row = _piece_row(
            str(form_key),
            float(c_value),
            float(q_value),
            float(maximum),
            float(reusable),
        )
        rows.append(row)
        for name, predicate in BIN_SPECS:
            if predicate(row["C"]):
                bucket = bins[name]
                bucket["piece_types"] += 1
                c_values[name].append(row["C"])
                r_values[name].append(row["R_cross"])
                if row["R_over_C"] is not None:
                    ratios[name].append(row["R_over_C"])
                if row["effective_host_count"] is not None:
                    effective[name].append(row["effective_host_count"])
                break
    c_total = math.fsum(row["C"] for row in rows)
    r_total = math.fsum(row["R_cross"] for row in rows)
    for name in bins:
        bins[name]["C_total"] = math.fsum(c_values[name])
        bins[name]["R_cross_total"] = math.fsum(r_values[name])
        bins[name].update(
            {
                "C_fraction": bins[name]["C_total"] / c_total,
                "R_cross_fraction": bins[name]["R_cross_total"] / r_total,
                "median_R_over_C": (
                    statistics.median(ratios[name]) if ratios[name] else None
                ),
                "median_effective_host_count": (
                    statistics.median(effective[name]) if effective[name] else None
                ),
            }
        )
    at_least_one = [row for row in rows if row["C"] >= 1.0]
    low_count = [row for row in rows if 0.0 < row["C"] < 1.0]

    def top(source: Iterable[dict[str, Any]], field: str) -> list[dict[str, Any]]:
        return sorted(
            source,
            key=lambda row: (-(row[field] or 0.0), row["form_key"]),
        )[:20]

    return {
        "piece_types": len(rows),
        "C_total": c_total,
        "R_cross_total": r_total,
        "bins": bins,
        "maximum_effective_host_count_for_C_at_least_1": max(
            row["effective_host_count"] or 0.0 for row in at_least_one
        ),
        "top_20_by_R_cross": top(rows, "R_cross"),
        "top_20_by_R_over_C_for_C_at_least_1": top(at_least_one, "R_over_C"),
        "top_20_by_effective_host_count_for_C_at_least_1": top(
            at_least_one, "effective_host_count"
        ),
        "top_20_low_count_by_R_cross": top(low_count, "R_cross"),
    }


def _occurrence_key(row: dict[str, Any]) -> tuple[Any, ...]:
    identity = row["occurrence_identity"]
    return tuple(
        identity[name]
        for name in (
            "target_id",
            "sentence_index",
            "dcs_id",
            "dcs_occ_id",
            "match_index",
        )
    )


def _classification(row: dict[str, Any]) -> str:
    recovered = row["top1_lexical_recovered"]
    if recovered is True:
        return "C"
    if recovered is False:
        return "W"
    return "U"


def _wordform_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    selected = list(rows)
    evaluable = [row for row in selected if _classification(row) != "U"]
    piece_rows = [row for row in selected if row["top1_piece_count"] is not None]
    recovered = sum(_classification(row) == "C" for row in evaluable)
    return {
        "occurrences": len(selected),
        "evaluable_occurrences": len(evaluable),
        "recovered_occurrences": recovered,
        "recovery_rate": recovered / len(evaluable) if evaluable else None,
        "piece_metric_occurrences": len(piece_rows),
        "mean_top1_piece_count": (
            statistics.fmean(row["top1_piece_count"] for row in piece_rows)
            if piece_rows
            else None
        ),
        "mean_top1_whole_form_use": (
            statistics.fmean(bool(row["top1_whole_form_use"]) for row in piece_rows)
            if piece_rows
            else None
        ),
    }


def _paired_audit(paths: dict[str, Path]) -> dict[str, Any]:
    indexed = {
        level: {_occurrence_key(row): row for row in _read_jsonl(path)}
        for level, path in paths.items()
    }
    key_sets = {level: set(rows) for level, rows in indexed.items()}
    if any(len(rows) != 80 for rows in indexed.values()) or len(key_sets["E000"]) != 80:
        raise RuntimeError("Each diagnostic input must contain 80 unique occurrences.")
    if key_sets["E000"] != key_sets["E100"]:
        raise RuntimeError("E000/E100 diagnostic occurrence identities differ.")

    transitions = collections.Counter()
    representation = collections.Counter()
    piece_count_delta = collections.Counter()
    for key in sorted(key_sets["E000"]):
        left, right = indexed["E000"][key], indexed["E100"][key]
        transitions[_classification(left) + _classification(right)] += 1
        if left["top1_piece_count"] is not None and right["top1_piece_count"] is not None:
            left_whole = "whole" if left["top1_whole_form_use"] else "multi"
            right_whole = "whole" if right["top1_whole_form_use"] else "multi"
            representation[f"{left_whole}_to_{right_whole}"] += 1
            piece_count_delta[
                str(right["top1_piece_count"] - left["top1_piece_count"])
            ] += 1

    wordforms = sorted(
        {row["dcs_unsandhied_gold_wordform"] for row in indexed["E000"].values()}
    )
    by_wordform: dict[str, Any] = {}
    for wordform in wordforms:
        entry: dict[str, Any] = {}
        for level in RUNS:
            entry[level] = _wordform_metrics(
                row
                for row in indexed[level].values()
                if row["dcs_unsandhied_gold_wordform"] == wordform
            )
        wordform_keys = [
            key
            for key, row in indexed["E000"].items()
            if row["dcs_unsandhied_gold_wordform"] == wordform
        ]
        entry["paired_transitions"] = dict(
            sorted(
                collections.Counter(
                    _classification(indexed["E000"][key])
                    + _classification(indexed["E100"][key])
                    for key in wordform_keys
                ).items()
            )
        )
        by_wordform[wordform] = entry

    macro: dict[str, Any] = {}
    for level in RUNS:
        macro[level] = {
            name: statistics.fmean(
                by_wordform[wordform][level][name] for wordform in wordforms
            )
            for name in (
                "recovery_rate",
                "mean_top1_piece_count",
                "mean_top1_whole_form_use",
            )
        }
    return {
        "occurrence_key_fields": [
            "target_id",
            "sentence_index",
            "dcs_id",
            "dcs_occ_id",
            "match_index",
        ],
        "unique_occurrences_per_run": 80,
        "key_sets_identical": True,
        "paired_classification_transitions": dict(sorted(transitions.items())),
        "paired_representation_transitions": dict(sorted(representation.items())),
        "paired_piece_count_delta_E100_minus_E000": dict(
            sorted(piece_count_delta.items(), key=lambda item: int(item[0]))
        ),
        "wordforms": by_wordform,
        "macro_average_across_wordforms": macro,
    }


def _source_rows(path: Path, repo_root: Path) -> list[dict[str, Any]]:
    relative = _relative(path, repo_root)
    return [
        {
            "source_row_id": f"{relative}#L{line_number}",
            "row": json.loads(line),
        }
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if line.strip()
    ]


def _selection_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(item["row"], ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
        for item in rows
    )


def _id_set_sha256(ids: Iterable[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(ids)).encode("utf-8")
    ).hexdigest()


def _text_multiset_sha256(counter: collections.Counter[str]) -> str:
    return _canonical_sha256(sorted(counter.items()))


def _reconstruct_selection(
    *,
    corpus: Path,
    sources: list[Path],
    repo_root: Path,
) -> list[dict[str, Any]]:
    queues: dict[str, collections.deque[dict[str, Any]]] = collections.defaultdict(
        collections.deque
    )
    for source in sources:
        for item in _source_rows(source, repo_root):
            queues[str(item["row"]["text"])].append(item)
    selected = []
    for text in corpus.read_text(encoding="utf-8").splitlines():
        if not queues[text]:
            raise RuntimeError(f"Cannot reconstruct corpus row from sources: {text!r}")
        selected.append(queues[text].popleft())
    return selected


def _selection_audit(data_root: Path, run_root: Path, repo_root: Path) -> dict[str, Any]:
    background = data_root / "background_1000.jsonl"
    target_paths = {
        level: data_root / "noun_high_deva" / level / "target_evidence.jsonl"
        for level in RUNS
    }
    corpora = {
        level: data_root / "noun_high_deva" / level / "corpus.txt"
        for level in RUNS
    }
    selected = {
        level: _reconstruct_selection(
            corpus=corpora[level],
            sources=[target_paths[level], background],
            repo_root=repo_root,
        )
        for level in RUNS
    }
    selected_ids = {
        level: {item["source_row_id"] for item in rows}
        for level, rows in selected.items()
    }
    shared = selected_ids["E000"] & selected_ids["E100"]
    only_e000 = selected_ids["E000"] - selected_ids["E100"]
    only_e100 = selected_ids["E100"] - selected_ids["E000"]
    text_counters = {
        level: collections.Counter(str(item["row"]["text"]) for item in rows)
        for level, rows in selected.items()
    }
    shared_text = text_counters["E000"] & text_counters["E100"]
    only_text_e000 = text_counters["E000"] - text_counters["E100"]
    only_text_e100 = text_counters["E100"] - text_counters["E000"]

    per_level: dict[str, Any] = {}
    for level, rows in selected.items():
        source_counts = collections.Counter(
            "target" if "target_evidence.jsonl" in item["source_row_id"] else "background"
            for item in rows
        )
        selection_hash = hashlib.sha256(_selection_bytes(rows)).hexdigest()
        run_selection = run_root / RUNS[level] / "training_selection.v1.jsonl"
        diagnostic_provenance = _read_json(
            run_root / RUNS[level] / "challenge_semantic_diagnostics.v4.provenance.json"
        )
        per_level[level] = {
            "corpus": _relative(corpora[level], repo_root),
            "corpus_sha256": _sha256(corpora[level]),
            "selected_rows": len(rows),
            "selected_source_counts": dict(sorted(source_counts.items())),
            "selected_source_row_id_set_sha256": _id_set_sha256(selected_ids[level]),
            "reconstructed_corpus_order_selection_sha256": selection_hash,
            "duplicate_text_excess_rows": sum(text_counters[level].values())
            - len(text_counters[level]),
            "diagnostics_training_selection_source": diagnostic_provenance[
                "training_selection_source"
            ],
            "diagnostics_training_selection_sha256": diagnostic_provenance[
                "training_selection_sha256"
            ],
            "run_selection_present": run_selection.is_file(),
            "run_selection_matches_reconstruction": (
                _sha256(run_selection) == selection_hash
                if run_selection.is_file()
                else None
            ),
        }
    return {
        "identity_scheme": (
            "repository-relative source JSONL path plus one-based physical line "
            "number; source file SHA-256 values below bind the bytes"
        ),
        "reconstruction_rule": (
            "queue target-evidence rows before background rows by exact text, then "
            "consume one source row for each corpus line in corpus order"
        ),
        "sources": {
            "background": {
                "path": _relative(background, repo_root),
                "sha256": _sha256(background),
                "rows": len(_source_rows(background, repo_root)),
            },
            **{
                f"{level}_target": {
                    "path": _relative(path, repo_root),
                    "sha256": _sha256(path),
                    "rows": len(_source_rows(path, repo_root)),
                }
                for level, path in target_paths.items()
            },
        },
        "conditions": per_level,
        "contrast": {
            "shared_selected_source_rows": len(shared),
            "E000_only_selected_source_rows": len(only_e000),
            "E100_only_selected_source_rows": len(only_e100),
            "shared_selected_source_row_id_set_sha256": _id_set_sha256(shared),
            "E000_only_source_row_id_set_sha256": _id_set_sha256(only_e000),
            "E100_only_source_row_id_set_sha256": _id_set_sha256(only_e100),
            "shared_text_rows": sum(shared_text.values()),
            "E000_only_text_rows": sum(only_text_e000.values()),
            "E100_only_text_rows": sum(only_text_e100.values()),
            "shared_text_multiset_sha256": _text_multiset_sha256(shared_text),
            "E000_only_text_multiset_sha256": _text_multiset_sha256(only_text_e000),
            "E100_only_text_multiset_sha256": _text_multiset_sha256(only_text_e100),
            "scientific_design": (
                "controlled evidence-condition contrast: E100 replaces 100 E000 "
                "background rows with 100 target-evidence rows at fixed n=1000"
            ),
            "strict_single_variable_causal_contrast": False,
        },
    }


def build_audit(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    run_root = repo_root / "artifacts/diagnostics/s1m2_lexeme_probe"
    data_root = repo_root / "data/diagnostics/s1m2_lexeme_probe/controlled"
    historical_contract_path = repo_root / "configs/production/s1m2_six_cell.json"
    v3_contract_path = repo_root / "configs/production/s1m2_six_cell_v3.json"
    historical_contract = _read_json(historical_contract_path)
    v3_contract = _read_json(v3_contract_path)
    if (
        v3_contract.get("model") != EXPECTED["model"]
        or v3_contract.get("passes") != EXPECTED["passes"]
        or v3_contract.get("scientific_config", {}).get(
            "sandhi_transformation_penalty"
        )
        != EXPECTED["sandhi_transformation_penalty"]
        or v3_contract.get("scientific_config", {}).get(
            "piece_boundary_probability"
        )
        != EXPECTED["piece_boundary_probability"]
    ):
        raise RuntimeError("Active production contract differs from qualified V3.")
    run_results: dict[str, Any] = {}
    diagnostic_paths: dict[str, Path] = {}
    for level, run_name in RUNS.items():
        run_dir = run_root / run_name
        config_path = run_dir / "config.json"
        provenance_path = run_dir / "provenance.json"
        database_path = run_dir / "learner.sqlite"
        diagnostic_path = run_dir / "challenge_semantic_diagnostics.v4.jsonl"
        diagnostic_paths[level] = diagnostic_path
        config = _read_json(config_path)
        provenance = _read_json(provenance_path)
        observed = {
            "model": config.get("model"),
            "passes": config.get("passes"),
            "workers": config.get("workers"),
            "sandhi_transformation_penalty": config.get(
                "sandhi_transformation_penalty"
            ),
            "piece_boundary_probability": config.get("piece_boundary_probability"),
            "piece_role_diagnostics": config.get("piece_role_diagnostics"),
            "training_git_commit": provenance.get("git_commit"),
            "challenge_sha256": provenance.get("challenge_sha256"),
        }
        if observed != EXPECTED:
            raise RuntimeError(
                f"{level} qualification identity mismatch: {observed!r}"
            )
        with _open_read_only(database_path) as connection:
            moment_audits = {
                table: _audit_moment_table(connection, table)
                for table in ("piece_lexicon", "piece_role_diagnostics")
            }
            if any(result["status"] != "PASS" for result in moment_audits.values()):
                raise RuntimeError(f"{level} failed C/Q/R contract validation.")
            tail = _tail_audit(connection)
        run_results[level] = {
            "run_directory": _relative(run_dir, repo_root),
            "qualification_identity": observed,
            "inputs": {
                "config": {"path": _relative(config_path, repo_root), "sha256": _sha256(config_path)},
                "provenance": {"path": _relative(provenance_path, repo_root), "sha256": _sha256(provenance_path)},
                "learner_sqlite": {"path": _relative(database_path, repo_root), "sha256": _sha256(database_path)},
                "semantic_diagnostics": {"path": _relative(diagnostic_path, repo_root), "sha256": _sha256(diagnostic_path)},
            },
            "moment_contract_audit": moment_audits,
            "posterior_tail_and_host_diversity": tail,
        }
    result = {
        "schema_version": SCHEMA,
        "audit_date": AUDIT_DATE,
        "status": "PASS_PENDING_RESEARCHER_FREEZE_DECISION",
        "method": {
            "trainer_invoked": False,
            "inference_invoked": False,
            "sqlite_open_mode": "mode=ro&immutable=1",
            "sqlite_query_only_enforced": True,
            "authoritative_reusable_count_helper": (
                "sktlm.pieces.cross_host_reusable_count"
            ),
        },
        "expected_qualification_identity": EXPECTED,
        "production_contract_closure": {
            "active_default": {
                "path": _relative(v3_contract_path, repo_root),
                "file_sha256": _sha256(v3_contract_path),
                "canonical_sha256": _canonical_sha256(v3_contract),
                "contract_id": v3_contract["contract_id"],
                "status": v3_contract["status"],
                "model": v3_contract["model"],
                "passes": v3_contract["passes"],
                "sandhi_transformation_penalty": v3_contract[
                    "scientific_config"
                ]["sandhi_transformation_penalty"],
                "piece_boundary_probability": v3_contract[
                    "scientific_config"
                ]["piece_boundary_probability"],
            },
            "historical_preserved": {
                "path": _relative(historical_contract_path, repo_root),
                "file_sha256": _sha256(historical_contract_path),
                "canonical_sha256": _canonical_sha256(historical_contract),
                "contract_id": historical_contract["contract_id"],
                "model": historical_contract["model"],
            },
        },
        "runs": run_results,
        "paired_occurrence_audit": _paired_audit(diagnostic_paths),
        "selection_provenance": _selection_audit(
            data_root, run_root, repo_root
        ),
        "researcher_review_flag": False,
        "researcher_review_reason": None,
    }
    result["audit_payload_sha256"] = _canonical_sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "reports/core_methods/reusable_pieces/evidence/"
            "s1m2_v3_prefreeze_audit_20260922.json"
        ),
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output = args.output
    if not output.is_absolute():
        output = repo_root / output
    audit = build_audit(repo_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {output}")
    print(f"audit_payload_sha256={audit['audit_payload_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

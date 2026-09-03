"""Read-only streaming compact export for one completed S1M1 cell.

The source run and SQLite database are never mutated. Publication is atomic
and refuses an existing destination; long real-data execution is external.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from .six_representation_gate import GateValidationError

SCHEMA_VERSION = "sktlm-s1m1-compact-cell/v1"
SQLITE_STATE_SCHEMA_VERSION = "sktlm-s1m1-sqlite-state/v1"
REQUIRED_RUN_FILES = (
    "iteration_metrics.json", "summary.json", "analyses.jsonl",
    "boundary_posteriors.jsonl", "latent_lexicon.tsv", "rule_usage.tsv",
    "timing_metrics.json", "provenance.json", "config.json", "checkpoint.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_database_identity(path: Path, *, role: str, required: bool) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        if required:
            raise GateValidationError((f"required source database artifact is absent or empty: {path}",))
        return {
            "artifact_role": role,
            "source_path": str(path),
            "present": False,
            "size_bytes": None,
            "sha256": None,
        }
    before = path.stat()
    size_bytes = before.st_size
    sha256 = _sha256(path)
    after = path.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise GateValidationError((f"source database artifact changed while hashing: {path}",))
    return {
        "artifact_role": role,
        "source_path": str(path),
        "present": True,
        "size_bytes": size_bytes,
        "sha256": sha256,
    }


def _number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise GateValidationError((f"{label} must be numeric",))
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise GateValidationError((f"{label} must be numeric",)) from exc
    if not math.isfinite(result):
        raise GateValidationError((f"{label} must be finite",))
    return result


def _json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateValidationError((f"{label} is unreadable JSON: {path}: {exc}",)) from exc


def _gzip_writer(path: Path, fields: Iterable[str]):
    handle = gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=6)
    writer = csv.DictWriter(handle, fieldnames=tuple(fields), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    return handle, writer


def _open_database(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.stat().st_size == 0:
        raise GateValidationError((f"learner SQLite is missing or empty: {path}",))
    uri = f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only = ON")
    required = {
        "lexicon": {"form_key", "expected_count", "probability"},
        "surface_usage": {"form_key", "surface", "expected_mass"},
        "context_usage": {"form_key", "context", "expected_mass"},
    }
    for table, columns in required.items():
        found = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not columns <= found:
            connection.close()
            raise GateValidationError((f"SQLite table {table} lacks required columns",))
    return connection


def _export_query(
    connection: sqlite3.Connection,
    query: str,
    output: Path,
    fields: tuple[str, ...],
    numeric_field: str,
) -> dict[str, Any]:
    count = 0
    total = 0.0
    handle, writer = _gzip_writer(output, fields)
    try:
        for values in connection.execute(query):
            row = dict(zip(fields, values, strict=True))
            value = _number(row[numeric_field], f"{output.name} {numeric_field}")
            if value < 0.0:
                raise GateValidationError((f"{output.name} has negative {numeric_field}",))
            writer.writerow(row)
            count += 1
            total += value
    finally:
        handle.close()
    return {"rows": count, f"sum_{numeric_field}": total}


def _export_database(connection: sqlite3.Connection, root: Path) -> dict[str, Any]:
    scorer = _export_query(
        connection,
        "SELECT form_key, expected_count, probability FROM lexicon ORDER BY form_key",
        root / "final_scorer.tsv.gz",
        ("form_key", "training_expected_count", "probability"),
        "training_expected_count",
    )
    surface = _export_query(
        connection,
        "SELECT form_key, surface, expected_mass FROM surface_usage ORDER BY form_key, surface",
        root / "surface_usage.tsv.gz",
        ("form_key", "surface", "expected_mass"),
        "expected_mass",
    )
    context = _export_query(
        connection,
        "SELECT form_key, context, expected_mass FROM context_usage ORDER BY form_key, context",
        root / "context_usage.tsv.gz",
        ("form_key", "context", "expected_mass"),
        "expected_mass",
    )
    declared = connection.execute(
        "SELECT COUNT(*), COALESCE(SUM(expected_count), 0), COALESCE(SUM(probability), 0) FROM lexicon"
    ).fetchone()
    assert declared is not None
    scorer["database_rows"] = int(declared[0])
    scorer["database_expected_count_sum"] = float(declared[1])
    scorer["database_probability_sum"] = float(declared[2])
    scorer["row_count_matches_database"] = scorer["rows"] == scorer["database_rows"]
    scorer["expected_count_sum_matches_database"] = math.isclose(
        scorer["sum_training_expected_count"], scorer["database_expected_count_sum"],
        rel_tol=1e-10, abs_tol=1e-6,
    )
    scorer["probability_sum_is_one"] = math.isclose(
        scorer["database_probability_sum"], 1.0, rel_tol=1e-9, abs_tol=1e-8,
    )
    return {"final_scorer": scorer, "surface_usage": surface, "context_usage": context}


def _export_lexicon(source: Path, output: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    fields = (
        "form_key", "rendered_form", "phoneme_ids", "phoneme_length",
        "inspection_expected_count", "training_probability",
        "number_of_surface_variants", "number_of_contexts",
    )
    length_stats: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    reuse_stats = {(axis, threshold): [0.0, 0.0] for axis in ("surface_variants", "contexts") for threshold in (2, 5, 10)}
    count = 0
    total = 0.0
    previous_count = math.inf
    previous_key = ""
    handle, writer = _gzip_writer(output, fields)
    try:
        with source.open("r", encoding="utf-8", newline="") as source_handle:
            reader = csv.DictReader(source_handle, delimiter="\t")
            required = {"form_key", "latent_form", "phoneme_ids", "expected_count", "probability", "number_of_surface_variants", "number_of_contexts"}
            if reader.fieldnames is None or not required <= set(reader.fieldnames):
                raise GateValidationError((f"invalid latent lexicon header: {source}",))
            for line_number, row in enumerate(reader, start=2):
                key = row["form_key"]
                mass = _number(row["expected_count"], f"{source}:{line_number} expected_count")
                probability = _number(row["probability"], f"{source}:{line_number} probability")
                phonemes = row["phoneme_ids"].split()
                variants = int(row["number_of_surface_variants"])
                contexts = int(row["number_of_contexts"])
                if not key or not phonemes or mass < 0.0 or probability < 0.0:
                    raise GateValidationError((f"invalid lexicon row at {source}:{line_number}",))
                if mass > previous_count or (mass == previous_count and previous_key and key < previous_key):
                    raise GateValidationError((f"latent lexicon sort order changed at {source}:{line_number}",))
                previous_count, previous_key = mass, key
                writer.writerow({
                    "form_key": key, "rendered_form": row["latent_form"],
                    "phoneme_ids": row["phoneme_ids"], "phoneme_length": len(phonemes),
                    "inspection_expected_count": mass,
                    "training_probability": probability,
                    "number_of_surface_variants": variants,
                    "number_of_contexts": contexts,
                })
                count += 1
                total += mass
                length_stats[len(phonemes)][0] += 1
                length_stats[len(phonemes)][1] += mass
                for axis, value in (("surface_variants", variants), ("contexts", contexts)):
                    for threshold in (2, 5, 10):
                        if value < threshold:
                            reuse_stats[(axis, threshold)][0] += 1
                            reuse_stats[(axis, threshold)][1] += mass
    finally:
        handle.close()
    length_rows = [
        {"phoneme_length": length, "type_count": int(values[0]), "inspection_expected_mass": values[1]}
        for length, values in sorted(length_stats.items())
    ]
    reuse_rows = [
        {"axis": axis, "threshold": f"<{threshold}", "type_count": int(values[0]), "type_fraction": values[0] / count if count else None, "inspection_expected_mass": values[1], "mass_fraction": values[1] / total if total else None}
        for (axis, threshold), values in sorted(reuse_stats.items())
    ]
    return {"rows": count, "inspection_expected_count_sum": total}, length_rows, reuse_rows


def _length_stratum(length: int) -> str:
    for ceiling in (16, 32, 64, 128):
        if length <= ceiling:
            return f"<={ceiling}"
    return ">128"


def _export_segments(source: Path, output: Path, script: str, representation: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    fields = (
        "segment_id", "document_id", "script", "representation",
        "identity_mass", "latent_mass", "entropy", "top1_posterior",
        "residual_mass", "log_partition", "candidate_factors",
        "candidate_nodes", "candidate_edges", "overflowed_tokens",
        "expected_lexical_tokens", "top1_form_keys", "top1_rule_ids",
        "source_span_characters", "surface_text_characters",
    )
    documents: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    strata: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    count = 0
    previous_id = ""
    handle, writer = _gzip_writer(output, fields)
    try:
        with source.open("r", encoding="utf-8") as source_handle:
            for line_number, line in enumerate(source_handle, start=1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GateValidationError((f"invalid analyses JSON at {source}:{line_number}",)) from exc
                segment_id = row.get("segment_id")
                if not isinstance(segment_id, str) or not segment_id or (previous_id and segment_id <= previous_id):
                    raise GateValidationError((f"non-unique/non-canonical segment_id at {source}:{line_number}",))
                previous_id = segment_id
                top = row.get("top_analyses")
                top1 = top[0] if isinstance(top, list) and top and isinstance(top[0], dict) else None
                top1_units = top1.get("latent_units", []) if top1 else []
                top1_rules = top1.get("rule_ids", []) if top1 else []
                counts = row.get("candidate_counts", {})
                surface = row.get("surface", "")
                start, end = row.get("source_start"), row.get("source_end")
                span = end - start if isinstance(start, int) and isinstance(end, int) else len(surface)
                top1_posterior = top1.get("posterior") if top1 else None
                output_row = {
                    "segment_id": segment_id, "document_id": row.get("document"),
                    "script": script, "representation": representation,
                    "identity_mass": row.get("identity_mass"), "latent_mass": row.get("latent_mass"),
                    "entropy": row.get("entropy"),
                    "top1_posterior": "N/A" if top1_posterior is None else top1_posterior,
                    "residual_mass": row.get("residual_posterior"),
                    "log_partition": row.get("log_partition"),
                    "candidate_factors": counts.get("factors"),
                    "candidate_nodes": counts.get("lattice_nodes"),
                    "candidate_edges": counts.get("lexical_edges"),
                    "overflowed_tokens": counts.get("overflowed_tokens"),
                    "expected_lexical_tokens": "N/A",
                    "top1_form_keys": json.dumps([unit.get("form_key") for unit in top1_units], separators=(",", ":")),
                    "top1_rule_ids": json.dumps(top1_rules, separators=(",", ":")),
                    "source_span_characters": span,
                    "surface_text_characters": len(surface),
                }
                writer.writerow(output_row)
                count += 1
                identity = _number(row.get("identity_mass"), f"{source}:{line_number} identity_mass")
                entropy = _number(row.get("entropy"), f"{source}:{line_number} entropy")
                edges = _number(counts.get("lexical_edges"), f"{source}:{line_number} lexical_edges")
                document = str(row.get("document"))
                for target in (documents[document], strata[_length_stratum(span)]):
                    target["segments"] += 1
                    target["identity_mass_sum"] += identity
                    target["entropy_sum"] += entropy
                    target["candidate_edges_sum"] += edges
    finally:
        handle.close()

    def rows(values: Mapping[str, Mapping[str, float]], key_name: str) -> list[dict[str, Any]]:
        result = []
        for key, stats in sorted(values.items()):
            n = stats["segments"]
            result.append({key_name: key, "segments": int(n), "mean_identity_mass": stats["identity_mass_sum"] / n, "mean_entropy": stats["entropy_sum"] / n, "mean_candidate_edges": stats["candidate_edges_sum"] / n})
        return result

    return {"rows": count}, rows(documents, "document_id"), rows(strata, "source_span_stratum")


def _export_boundaries(source: Path, output: Path) -> dict[str, Any]:
    fields = ("segment_id", "boundary_id", "cue_kind", "source_start", "source_end", "probability")
    segments = boundaries = 0
    previous_id = ""
    handle, writer = _gzip_writer(output, fields)
    try:
        with source.open("r", encoding="utf-8") as source_handle:
            for line_number, line in enumerate(source_handle, start=1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GateValidationError((f"invalid boundary JSON at {source}:{line_number}",)) from exc
                segment_id = row.get("segment_id")
                if not isinstance(segment_id, str) or not segment_id or (previous_id and segment_id <= previous_id):
                    raise GateValidationError((f"non-unique/non-canonical boundary segment_id at {source}:{line_number}",))
                previous_id = segment_id
                segment_boundaries = row.get("boundaries")
                if not isinstance(segment_boundaries, list):
                    raise GateValidationError((f"invalid boundaries at {source}:{line_number}",))
                for boundary in segment_boundaries:
                    writer.writerow({"segment_id": segment_id, **{field: boundary.get(field) for field in fields[1:]}})
                    boundaries += 1
                segments += 1
    finally:
        handle.close()
    return {"segment_rows": segments, "boundary_rows": boundaries}


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = tuple(rows[0]) if rows else ("status",)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        if rows:
            writer.writerows(
                {key: "N/A" if value is None else value for key, value in row.items()}
                for row in rows
            )


def _write_small_tables(run_dir: Path, metrics_dir: Path, root: Path) -> None:
    passes = _json(run_dir / "iteration_metrics.json", "iteration metrics")
    if not isinstance(passes, list) or not all(isinstance(row, dict) for row in passes):
        raise GateValidationError(("iteration_metrics.json must be an array of objects",))
    _write_rows(root / "pass_dynamics.tsv", passes)
    with (run_dir / "rule_usage.tsv").open("r", encoding="utf-8", newline="") as source, (root / "rule_usage.tsv").open("x", encoding="utf-8", newline="") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
    timing = _json(run_dir / "timing_metrics.json", "timing metrics")
    process = _json(metrics_dir / "process_tree_summary.json", "process summary")
    runtime_rows = []
    for group, values in (("timings_seconds", timing.get("timings_seconds", {})), ("counters", timing.get("counters", {})), ("process_tree", process)):
        if isinstance(values, dict):
            runtime_rows.extend({"group": group, "metric": key, "value": json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value} for key, value in sorted(values.items()))
    _write_rows(root / "runtime_breakdown.tsv", runtime_rows)


def _readback_gzip(path: Path, numeric_field: str | None = None) -> dict[str, Any]:
    count = 0
    total = 0.0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            count += 1
            if numeric_field is not None:
                total += _number(row[numeric_field], f"{path.name} read-back {numeric_field}")
    result: dict[str, Any] = {"rows": count}
    if numeric_field is not None:
        result[f"sum_{numeric_field}"] = total
    return result


def export_compact_cell(
    *,
    cell_id: str,
    script: str,
    representation: str,
    run_dir: Path,
    metrics_dir: Path,
    database_path: Path,
    output_dir: Path,
) -> None:
    """Stream one completed cell into an atomic compact archive directory."""

    run_dir = run_dir.resolve()
    metrics_dir = metrics_dir.resolve()
    database_path = database_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    missing = [name for name in REQUIRED_RUN_FILES if not (run_dir / name).is_file()]
    if not (metrics_dir / "process_tree_summary.json").is_file():
        missing.append("metrics/process_tree_summary.json")
    if missing:
        raise GateValidationError((f"missing required inputs: {missing}",))
    config = _json(run_dir / "config.json", "config")
    provenance = _json(run_dir / "provenance.json", "provenance")
    checkpoint = _json(run_dir / "checkpoint.json", "checkpoint")
    summary = _json(run_dir / "summary.json", "summary")
    if not all(isinstance(value, dict) for value in (config, provenance, checkpoint, summary)):
        raise GateValidationError(("config/provenance/checkpoint/summary must be objects",))
    config_identity = (config.get("script"), config.get("condition"))
    if config_identity not in {(script, representation), (None, None)}:
        raise GateValidationError(("config representation identity differs",))
    if (provenance.get("script"), provenance.get("condition")) != (script, representation):
        raise GateValidationError(("provenance representation identity differs",))
    if checkpoint.get("inspection_complete") is not True:
        raise GateValidationError(("checkpoint inspection is incomplete",))
    if checkpoint.get("completed_passes") != config.get("passes"):
        raise GateValidationError(("checkpoint passes differ from config",))

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_database(database_path)
        database = _export_database(connection, temporary)
        lexicon, length_rows, reuse_rows = _export_lexicon(
            run_dir / "latent_lexicon.tsv", temporary / "lexicon_inventory.tsv.gz"
        )
        segments, document_rows, stratum_rows = _export_segments(
            run_dir / "analyses.jsonl", temporary / "segment_metrics.tsv.gz",
            script, representation,
        )
        boundaries = _export_boundaries(
            run_dir / "boundary_posteriors.jsonl", temporary / "boundary_table.tsv.gz"
        )
        _write_rows(temporary / "lexical_length.tsv", length_rows)
        _write_rows(temporary / "reuse_distribution.tsv", reuse_rows)
        _write_rows(temporary / "document_distribution.tsv", document_rows)
        _write_rows(temporary / "length_strata.tsv", stratum_rows)
        _write_small_tables(run_dir, metrics_dir, temporary)

        readback = {
            "final_scorer": _readback_gzip(temporary / "final_scorer.tsv.gz", "training_expected_count"),
            "surface_usage": _readback_gzip(temporary / "surface_usage.tsv.gz", "expected_mass"),
            "context_usage": _readback_gzip(temporary / "context_usage.tsv.gz", "expected_mass"),
            "lexicon_inventory": _readback_gzip(temporary / "lexicon_inventory.tsv.gz", "inspection_expected_count"),
            "segment_metrics": _readback_gzip(temporary / "segment_metrics.tsv.gz"),
            "boundary_table": _readback_gzip(temporary / "boundary_table.tsv.gz"),
        }
        declared_segments = int(_number(summary.get("segments"), "summary segments"))
        declared_types = int(_number(summary.get("complexity", {}).get("active_lexical_types"), "summary active lexical types"))
        consistency = {
            "final_scorer_readback_rows_match": readback["final_scorer"]["rows"] == database["final_scorer"]["rows"],
            "final_scorer_readback_mass_matches": math.isclose(readback["final_scorer"]["sum_training_expected_count"], database["final_scorer"]["sum_training_expected_count"], rel_tol=1e-10, abs_tol=1e-6),
            "lexicon_rows_match_summary": lexicon["rows"] == declared_types,
            "lexicon_readback_rows_match": readback["lexicon_inventory"]["rows"] == lexicon["rows"],
            "lexicon_readback_mass_matches": math.isclose(readback["lexicon_inventory"]["sum_inspection_expected_count"], lexicon["inspection_expected_count_sum"], rel_tol=1e-10, abs_tol=1e-6),
            "analysis_rows_match_summary": segments["rows"] == declared_segments,
            "analysis_readback_rows_match": readback["segment_metrics"]["rows"] == segments["rows"],
            "boundary_segment_rows_match_summary": boundaries["segment_rows"] == declared_segments,
            "boundary_readback_rows_match": readback["boundary_table"]["rows"] == boundaries["boundary_rows"],
            "database_lexicon_checks_pass": all(database["final_scorer"][key] for key in ("row_count_matches_database", "expected_count_sum_matches_database", "probability_sum_is_one")),
        }
        if not all(consistency.values()):
            raise GateValidationError((f"compact export consistency failed: {consistency}",))

        data_files = sorted(path for path in temporary.iterdir() if path.is_file())
        compact_artifacts = [
            {"name": path.name, "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in data_files
        ]
        database_identity = _source_database_identity(
            database_path, role="learner_sqlite", required=True
        )
        database_identity["database_path"] = str(database_path)
        wal_identity = _source_database_identity(
            database_path.with_name(f"{database_path.name}-wal"),
            role="learner_sqlite_wal",
            required=False,
        )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "cell_id": cell_id, "script": script, "representation": representation,
            "scientific_commit": provenance.get("git_commit"),
            "config_signature": provenance.get("config_signature"),
            "source_artifacts": [
                {"relative_to_run_dir": name, "size_bytes": (run_dir / name).stat().st_size}
                for name in REQUIRED_RUN_FILES
            ] + [database_identity, wal_identity],
            "statistics": {
                "database": database, "lexicon_inventory": lexicon,
                "segments": segments, "boundaries": boundaries,
            },
            "readback": readback, "consistency": consistency,
            "compact_artifacts": compact_artifacts,
            "source_mutation": "none; SQLite opened mode=ro/query_only",
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="",
        )
        checksum_files = sorted(path for path in temporary.iterdir() if path.is_file())
        with (temporary / "SHA256SUMS").open("x", encoding="utf-8", newline="") as handle:
            for path in checksum_files:
                handle.write(f"{_sha256(path)}  {path.name}\n")
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        if connection is not None:
            connection.close()


def export_sqlite_state(
    *,
    cell_id: str,
    database_path: Path,
    output_dir: Path,
    wal_path: Path | None = None,
) -> None:
    """Export only training-final scorer and association state from SQLite."""

    database_path = database_path.resolve()
    output_dir = output_dir.resolve()
    wal_resolution = "explicit" if wal_path is not None else "derived_as_<database>-wal"
    resolved_wal_path = (
        wal_path.resolve()
        if wal_path is not None
        else database_path.with_name(f"{database_path.name}-wal")
    )
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_database(database_path)
        database = _export_database(connection, temporary)
        readback = {
            "final_scorer": _readback_gzip(
                temporary / "final_scorer.tsv.gz", "training_expected_count"
            ),
            "surface_usage": _readback_gzip(
                temporary / "surface_usage.tsv.gz", "expected_mass"
            ),
            "context_usage": _readback_gzip(
                temporary / "context_usage.tsv.gz", "expected_mass"
            ),
        }
        consistency = {
            f"{name}_readback_rows_match": readback[name]["rows"] == database[name]["rows"]
            for name in readback
        }
        for name, numeric_field in (
            ("final_scorer", "training_expected_count"),
            ("surface_usage", "expected_mass"),
            ("context_usage", "expected_mass"),
        ):
            consistency[f"{name}_readback_mass_matches"] = math.isclose(
                readback[name][f"sum_{numeric_field}"],
                database[name][f"sum_{numeric_field}"],
                rel_tol=1e-10,
                abs_tol=1e-6,
            )
        consistency["database_lexicon_checks_pass"] = all(
            database["final_scorer"][key]
            for key in (
                "row_count_matches_database",
                "expected_count_sum_matches_database",
                "probability_sum_is_one",
            )
        )
        if not all(consistency.values()):
            raise GateValidationError(
                (f"SQLite-state export consistency failed: {consistency}",)
            )

        compact_artifacts = [
            {"name": path.name, "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in sorted(temporary.iterdir())
            if path.is_file()
        ]
        database_identity = _source_database_identity(
            database_path, role="learner_sqlite", required=True
        )
        database_identity["database_path"] = str(database_path)
        wal_identity = _source_database_identity(
            resolved_wal_path, role="learner_sqlite_wal", required=False
        )
        manifest = {
            "schema_version": SQLITE_STATE_SCHEMA_VERSION,
            "cell_id": cell_id,
            "source_artifacts": [database_identity, wal_identity],
            "wal_path_resolution": wal_resolution,
            "statistics": {"database": database},
            "readback": readback,
            "consistency": consistency,
            "compact_artifacts": compact_artifacts,
            "sqlite_view": "mode=ro/query_only; includes committed WAL-visible state",
            "source_mutation": "none; no checkpoint, journal-mode change, or SQL write",
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        checksum_files = sorted(path for path in temporary.iterdir() if path.is_file())
        with (temporary / "SHA256SUMS").open(
            "x", encoding="utf-8", newline=""
        ) as handle:
            for path in checksum_files:
                handle.write(f"{_sha256(path)}  {path.name}\n")
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        if connection is not None:
            connection.close()

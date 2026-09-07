#!/usr/bin/env python3
"""Measure S1M2 transient SQLite/storage classes on a disposable copy."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any


TRAINING_DIAGNOSTIC_TABLES = (
    "lexical_diagnostics",
    "piece_inventory",
)
INSPECTION_TABLES = (
    "context_usage",
    "inspection_counts",
    "inspection_piece_counts",
    "surface_usage",
)


def _database_bytes(path: Path) -> dict[str, int]:
    sizes = {
        "database": path.stat().st_size if path.is_file() else 0,
        "wal": Path(f"{path}-wal").stat().st_size
        if Path(f"{path}-wal").is_file()
        else 0,
        "shm": Path(f"{path}-shm").stat().st_size
        if Path(f"{path}-shm").is_file()
        else 0,
    }
    sizes["total"] = sum(sizes.values())
    return sizes


def _tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )


def _compact_after_drop(
    connection: sqlite3.Connection,
    path: Path,
    tables: tuple[str, ...],
) -> dict[str, Any]:
    existing = set(_tables(connection))
    dropped = tuple(name for name in tables if name in existing)
    started = time.perf_counter()
    with connection:
        for name in dropped:
            connection.execute(f"DROP TABLE {name}")
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    connection.execute("VACUUM")
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    return {
        "dropped_tables": list(dropped),
        "retained_tables": list(_tables(connection)),
        "bytes": _database_bytes(path),
        "seconds": time.perf_counter() - started,
    }


def measure(run_dir: Path, *, candidate_workers: int) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    database = run_dir / "learner.sqlite"
    timing_path = run_dir / "timing_metrics.json"
    if not database.is_file() or not timing_path.is_file():
        raise FileNotFoundError("Run requires learner.sqlite and timing_metrics.json")
    source_bytes = _database_bytes(database)
    if source_bytes["wal"]:
        raise RuntimeError("Measurement requires a closed source with zero WAL bytes.")
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    benchmark_path = run_dir / "benchmark_metrics.json"
    benchmark = (
        json.loads(benchmark_path.read_text(encoding="utf-8"))
        if benchmark_path.is_file()
        else {}
    )
    gauges = timing["gauges"]
    excluded = {
        "benchmark_metrics.json",
        "timing_metrics.json",
        "learner.sqlite-wal",
        "learner.sqlite-shm",
    }
    finalize_base_bytes = sum(
        path.stat().st_size
        for path in run_dir.iterdir()
        if path.is_file() and path.name not in excluded
    )
    inferred_retained_shards = (
        int(gauges["artifact_bytes_before_timing_metrics"])
        - finalize_base_bytes
        - int(gauges["sqlite_wal_bytes"])
        - int(gauges["sqlite_shm_bytes"])
    )
    source_stat = (database.stat().st_size, database.stat().st_mtime_ns)
    with tempfile.TemporaryDirectory(
        prefix=".sktlm-opt15-",
        dir=database.parent,
    ) as raw_root:
        copy_path = Path(raw_root) / "learner.sqlite"
        copy_started = time.perf_counter()
        shutil.copyfile(database, copy_path)
        copy_seconds = time.perf_counter() - copy_started
        connection = sqlite3.connect(copy_path)
        try:
            initial_tables = _tables(connection)
            inspection_plus_active = _compact_after_drop(
                connection,
                copy_path,
                TRAINING_DIAGNOSTIC_TABLES,
            )
            active_only = _compact_after_drop(
                connection,
                copy_path,
                INSPECTION_TABLES,
            )
        finally:
            connection.close()
    source_stat_after = (database.stat().st_size, database.stat().st_mtime_ns)
    inspection_plus_active_bytes = int(
        inspection_plus_active["bytes"]["total"]
    )
    active_only_bytes = int(active_only["bytes"]["total"])
    measured_workers = max(1, int(benchmark.get("workers", 1)))
    phoneme_multiplier = 101.23887973280279
    current_transient_projection_gib = 366.69411719870857
    bounded_pending_bytes = int(
        gauges["inspection_pending_shard_bytes"]
    ) * candidate_workers / measured_workers
    candidate_representative_bytes = (
        int(gauges["artifact_bytes_before_timing_metrics"])
        - (int(source_bytes["total"]) - inspection_plus_active_bytes)
        - inferred_retained_shards
        + int(gauges["inspection_pending_shard_bytes"])
    )
    candidate_projection_gib = (
        current_transient_projection_gib
        - (
            int(source_bytes["total"])
            - inspection_plus_active_bytes
            + inferred_retained_shards
        )
        * phoneme_multiplier
        / (1024**3)
        + bounded_pending_bytes / (1024**3)
    )
    return {
        "schema_version": "sktlm-s1m2-opt15-transient-storage-measurement/v1",
        "run_dir": run_dir.as_posix(),
        "source_database": database.as_posix(),
        "source_database_stat_unchanged": source_stat == source_stat_after,
        "source_bytes": source_bytes,
        "source_tables": list(initial_tables),
        "copy_seconds": copy_seconds,
        "selective_compaction": {
            "inspection_plus_active": inspection_plus_active,
            "active_only": active_only,
            "training_diagnostic_bytes": (
                int(source_bytes["total"]) - inspection_plus_active_bytes
            ),
            "inspection_bytes": inspection_plus_active_bytes - active_only_bytes,
            "active_state_bytes": active_only_bytes,
        },
        "observed_lifetime": {
            "precleanup_artifact_highwater_bytes": int(
                gauges["artifact_bytes_before_timing_metrics"]
            ),
            "sqlite_total_highwater_bytes": int(gauges["sqlite_total_bytes"]),
            "sqlite_wal_highwater_bytes": int(gauges["sqlite_wal_bytes"]),
            "inspection_pending_shard_highwater_bytes": int(
                gauges["inspection_pending_shard_bytes"]
            ),
            "inferred_retained_inspection_shard_bytes": inferred_retained_shards,
            "inference_note": (
                "Retained shard bytes are the measured precleanup directory "
                "high-water residual after the extant finalization files and "
                "simultaneous recorded SQLite WAL/SHM bytes are removed."
            ),
        },
        "bounded_candidate_model": {
            "representative_peak_bytes": candidate_representative_bytes,
            "representative_reduction_percent": 100.0
            * (
                int(gauges["artifact_bytes_before_timing_metrics"])
                - candidate_representative_bytes
            )
            / int(gauges["artifact_bytes_before_timing_metrics"]),
            "full_corpus_projection_classification": (
                "PROJECTION_NOT_VM_OR_FULL_CORPUS_MEASUREMENT"
            ),
            "current_transient_projection_gib": current_transient_projection_gib,
            "candidate_transient_projection_gib": candidate_projection_gib,
            "candidate_workers": candidate_workers,
            "measured_source_workers": measured_workers,
            "bounded_pending_shard_bytes": int(bounded_pending_bytes),
            "assumptions": [
                "Measured training diagnostic pages are reusable before inspection.",
                "Reduced shards do not scale with corpus size after early retirement.",
                "The observed pending-shard high-water scales linearly from four to eight workers as a conservative bounded allowance.",
                "The historical WAL projection is left unchanged.",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--candidate-workers", type=int, default=8)
    args = parser.parse_args()
    if args.candidate_workers < 1:
        parser.error("--candidate-workers must be positive")
    print(
        json.dumps(
            measure(args.run_dir, candidate_workers=args.candidate_workers),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

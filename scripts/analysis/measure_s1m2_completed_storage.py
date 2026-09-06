#!/usr/bin/env python3
"""Measure completed S1M2 database compaction on a bounded disposable copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from sktlm.latent.store import LexiconStore


def _piece_state_digest(connection: sqlite3.Connection) -> tuple[int, str]:
    digest = hashlib.sha256()
    rows = 0
    for key, count, support in connection.execute(
        "SELECT form_key, expected_count, occurrence_support "
        "FROM piece_lexicon ORDER BY form_key"
    ):
        digest.update(str(key).encode("ascii"))
        digest.update(b"\t")
        digest.update(float(count).hex().encode("ascii"))
        digest.update(b"\t")
        digest.update(str(int(support)).encode("ascii"))
        digest.update(b"\n")
        rows += 1
    return rows, digest.hexdigest()


def measure(database: Path) -> dict[str, object]:
    database = database.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    source_sizes = {
        "database": database.stat().st_size,
        "wal": Path(f"{database}-wal").stat().st_size
        if Path(f"{database}-wal").is_file()
        else 0,
        "shm": Path(f"{database}-shm").stat().st_size
        if Path(f"{database}-shm").is_file()
        else 0,
    }
    source_sizes["total"] = sum(source_sizes.values())
    if source_sizes["wal"]:
        raise RuntimeError(
            "Measurement requires a closed completed database with no WAL."
        )
    source_stat_before = (database.stat().st_size, database.stat().st_mtime_ns)
    with tempfile.TemporaryDirectory(
        prefix=".sktlm-opt14-",
        dir=database.parent,
    ) as raw_root:
        copy_path = Path(raw_root) / "learner.sqlite"
        backup_started = time.perf_counter()
        shutil.copyfile(database, copy_path)
        backup_seconds = time.perf_counter() - backup_started

        store = LexiconStore(copy_path)
        try:
            rows_before, digest_before = _piece_state_digest(store.connection)
            result = store.compact_completed_piece_state()
            rows_after, digest_after = _piece_state_digest(store.connection)
        finally:
            store.close()
    source_stat_after = (database.stat().st_size, database.stat().st_mtime_ns)
    return {
        "schema_version": "sktlm-s1m2-opt14-storage-measurement/v1",
        "source_database": database.as_posix(),
        "source_database_stat_unchanged": source_stat_before == source_stat_after,
        "source_bytes": source_sizes,
        "backup_seconds": backup_seconds,
        "compaction": result,
        "authoritative_piece_rows_before": rows_before,
        "authoritative_piece_rows_after": rows_after,
        "authoritative_piece_digest_before": digest_before,
        "authoritative_piece_digest_after": digest_after,
        "authoritative_piece_state_exact": (
            rows_before == rows_after and digest_before == digest_after
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.database), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Short synthetic journal-mode evidence for the S1M2 transient support table."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Iterator

from sktlm.latent.phonology import Phoneme, PhonologicalForm, pack_phonological_form


SAFE_BIND_PARAMETERS = 900
ROW_WIDTH = 3
BATCH_ROWS = SAFE_BIND_PARAMETERS // ROW_WIDTH
UPSERT_PREFIX = (
    "INSERT INTO piece_host_support_next(piece_key, host_key, support) VALUES "
)
UPSERT_SUFFIX = (
    " ON CONFLICT(piece_key, host_key) DO UPDATE SET "
    "support=support+excluded.support"
)
PHONEMES = tuple(Phoneme)


def _digits(value: int, width: int) -> tuple[Phoneme, ...]:
    result = [PHONEMES[0]] * width
    for position in range(width - 1, -1, -1):
        value, digit = divmod(value, len(PHONEMES))
        result[position] = PHONEMES[digit]
    if value:
        raise ValueError("synthetic identity width is insufficient")
    return tuple(result)


def _row(index: int, round_index: int) -> tuple[str, bytes, float]:
    piece_length = 2 + (index % 7)
    piece = PhonologicalForm(_digits(index, 8)[-piece_length:]).key
    host_symbols = (
        (Phoneme.A, Phoneme.K, Phoneme.A)
        + _digits(index, 4)
        + (Phoneme.T, Phoneme.I) * (8 + index % 8)
    )
    host = pack_phonological_form(PhonologicalForm(host_symbols))
    return piece, host, float((index + round_index) % 13 + 1) / 16.0


def _batches(
    start: int, stop: int, round_index: int
) -> Iterator[list[tuple[str, bytes, float]]]:
    batch: list[tuple[str, bytes, float]] = []
    for index in range(start, stop):
        batch.append(_row(index, round_index))
        if len(batch) == BATCH_ROWS:
            yield batch
            batch = []
    if batch:
        yield batch


def _execute_batch(
    connection: sqlite3.Connection, batch: list[tuple[str, bytes, float]]
) -> None:
    placeholders = ",".join("(?,?,?)" for _ in batch)
    connection.execute(
        UPSERT_PREFIX + placeholders + UPSERT_SUFFIX,
        tuple(value for row in batch for value in row),
    )


def _sizes(database: Path) -> dict[str, int]:
    paths = {
        "database": database,
        "wal": Path(f"{database}-wal"),
        "rollback_journal": Path(f"{database}-journal"),
    }
    result = {
        name: path.stat().st_size if path.is_file() else 0
        for name, path in paths.items()
    }
    result["total"] = sum(result.values())
    return result


def _configure(connection: sqlite3.Connection, mode: str) -> str:
    row = connection.execute(f"PRAGMA journal_mode={mode}").fetchone()
    actual = "" if row is None else str(row[0]).lower()
    if actual != mode.lower():
        raise RuntimeError(f"journal mode {mode!r} resolved to {row!r}")
    connection.execute("PRAGMA synchronous=NORMAL")
    return actual


def _run_mode(
    root: Path,
    mode: str,
    *,
    unique_rows: int,
    conflict_rounds: int,
    seed_rows: int,
) -> dict[str, object]:
    database = root / f"{mode.lower()}.sqlite"
    connection = sqlite3.connect(database)
    actual_mode = _configure(connection, mode)
    connection.execute(
        "CREATE TABLE piece_host_support_next("
        "piece_key TEXT NOT NULL, host_key BLOB NOT NULL, support REAL NOT NULL, "
        "PRIMARY KEY(piece_key, host_key)) WITHOUT ROWID"
    )
    connection.commit()
    for batch in _batches(0, seed_rows, -1):
        _execute_batch(connection, batch)
    connection.commit()
    if actual_mode == "wal":
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()

    peak = _sizes(database)
    wall_started = time.perf_counter()
    connection.execute("BEGIN IMMEDIATE")
    transaction_started = time.perf_counter()
    statement_calls = 0
    input_rows = 0
    for round_index in range(conflict_rounds):
        for batch in _batches(0, unique_rows, round_index):
            _execute_batch(connection, batch)
            statement_calls += 1
            input_rows += len(batch)
            current = _sizes(database)
            for key, value in current.items():
                peak[key] = max(peak[key], value)
    transaction_seconds = time.perf_counter() - transaction_started
    commit_started = time.perf_counter()
    connection.commit()
    commit_seconds = time.perf_counter() - commit_started
    committed_sizes = _sizes(database)
    for key, value in committed_sizes.items():
        peak[key] = max(peak[key], value)
    committed_state = connection.execute(
        "SELECT COUNT(*), SUM(support) FROM piece_host_support_next"
    ).fetchone()
    assert committed_state is not None

    sentinel_piece, sentinel_host, sentinel_value = _row(unique_rows + 1, 0)
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        UPSERT_PREFIX + "(?,?,?)" + UPSERT_SUFFIX,
        (sentinel_piece, sentinel_host, sentinel_value),
    )
    connection.close()  # deliberate uncommitted-close rollback probe

    reopened = sqlite3.connect(database)
    reopened_mode = _configure(reopened, mode)
    rollback_absent = reopened.execute(
        "SELECT COUNT(*) FROM piece_host_support_next "
        "WHERE piece_key=? AND host_key=?",
        (sentinel_piece, sentinel_host),
    ).fetchone()[0] == 0
    state_after_rollback = reopened.execute(
        "SELECT COUNT(*), SUM(support) FROM piece_host_support_next"
    ).fetchone()
    rollback_preserved_state = state_after_rollback == committed_state

    reopened.execute("BEGIN IMMEDIATE")
    reopened.execute(
        UPSERT_PREFIX + "(?,?,?)" + UPSERT_SUFFIX,
        (sentinel_piece, sentinel_host, sentinel_value),
    )
    reopened.commit()
    reopened.close()

    final = sqlite3.connect(database)
    committed_sentinel = final.execute(
        "SELECT support FROM piece_host_support_next "
        "WHERE piece_key=? AND host_key=?",
        (sentinel_piece, sentinel_host),
    ).fetchone()
    quick_check = final.execute("PRAGMA quick_check").fetchone()[0]
    final.close()
    if not (
        rollback_absent
        and rollback_preserved_state
        and committed_sentinel == (sentinel_value,)
        and quick_check == "ok"
    ):
        raise RuntimeError(f"journal semantics failed for {mode}")

    return {
        "journal_mode": actual_mode,
        "reopen_journal_mode": reopened_mode,
        "synchronous": "normal",
        "unique_rows": unique_rows,
        "conflict_rounds": conflict_rounds,
        "seed_rows": seed_rows,
        "input_rows": input_rows,
        "statement_calls": statement_calls,
        "wall_seconds": time.perf_counter() - wall_started,
        "transaction_seconds_before_commit": transaction_seconds,
        "commit_seconds": commit_seconds,
        "peak_bytes": peak,
        "committed_bytes": committed_sizes,
        "committed_row_count": int(committed_state[0]),
        "committed_support_sum": float(committed_state[1]),
        "rollback_uncommitted_absent": rollback_absent,
        "rollback_preserved_committed_state": rollback_preserved_state,
        "commit_state_complete": committed_sentinel == (sentinel_value,),
        "quick_check": quick_check,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unique-rows", type=int, default=40_000)
    parser.add_argument("--conflict-rounds", type=int, default=4)
    parser.add_argument("--seed-rows", type=int, default=10_000)
    args = parser.parse_args()
    if not 0 <= args.seed_rows <= args.unique_rows:
        parser.error("seed rows must be between zero and unique rows")
    if args.unique_rows < 1 or args.conflict_rounds < 1:
        parser.error("unique rows and conflict rounds must be positive")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="sktlm-round3d-journal-") as temporary:
        root = Path(temporary)
        results = [
            _run_mode(
                root,
                mode,
                unique_rows=args.unique_rows,
                conflict_rounds=args.conflict_rounds,
                seed_rows=args.seed_rows,
            )
            for mode in ("wal", "delete", "truncate")
        ]
    payload = {
        "schema_version": "sktlm-s1m2-round3d-journal-benchmark/v1",
        "qualification_scope": "engineering_strategy_only_not_performance_qualification",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "safe_bind_parameters": SAFE_BIND_PARAMETERS,
        "batch_rows": BATCH_ROWS,
        "total_wall_seconds": time.perf_counter() - started,
        "results": results,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

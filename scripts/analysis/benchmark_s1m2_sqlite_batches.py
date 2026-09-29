"""Bounded local comparison of transient-support SQLite UPSERT batch sizes."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Iterator


ROW_COUNT = 120_000
UNIQUE_ROWS = 40_000
BATCH_ROWS = (300, 600, 1_200)
MAX_BIND_PARAMETERS = 3_600


def _variable_limit(connection: sqlite3.Connection) -> tuple[int, str]:
    getlimit = getattr(connection, "getlimit", None)
    category = getattr(sqlite3, "SQLITE_LIMIT_VARIABLE_NUMBER", None)
    if getlimit is None or category is None:
        return 900, "python_api_unavailable_fallback"
    value = int(getlimit(category))
    if value < 3:
        raise RuntimeError(f"Invalid SQLite variable-number limit: {value}")
    return value, "connection.getlimit(SQLITE_LIMIT_VARIABLE_NUMBER)"


def _rows() -> Iterator[tuple[bytes, bytes, float]]:
    for index in range(ROW_COUNT):
        key = index % UNIQUE_ROWS
        piece = b"\x01" + key.to_bytes(3, "big")
        host = b"\x01" + ((key * 17) % UNIQUE_ROWS).to_bytes(3, "big")
        yield piece, host, float(index % 17 + 1) / 17.0


def _batches(
    rows: Iterable[tuple[bytes, bytes, float]], batch_size: int
) -> Iterator[list[tuple[bytes, bytes, float]]]:
    batch: list[tuple[bytes, bytes, float]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _files(path: Path) -> dict[str, int]:
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


def _run_case(root: Path, requested_rows: int) -> dict[str, Any]:
    path = root / f"batch-{requested_rows}.sqlite"
    connection = sqlite3.connect(path)
    try:
        journal = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            "CREATE TABLE piece_host_support_next("
            "piece_key BLOB NOT NULL, host_key BLOB NOT NULL, support REAL NOT NULL, "
            "PRIMARY KEY(piece_key, host_key)) WITHOUT ROWID"
        )
        connection.commit()
        variable_limit, limit_source = _variable_limit(connection)
        bind_cap = min(variable_limit, MAX_BIND_PARAMETERS)
        batch_rows = min(requested_rows, bind_cap // 3)
        peak = _files(path)
        started = time.perf_counter()
        connection.execute("BEGIN IMMEDIATE")
        statement_calls = 0
        for batch in _batches(_rows(), batch_rows):
            placeholders = ",".join("(?,?,?)" for _ in batch)
            parameters = tuple(value for row in batch for value in row)
            connection.execute(
                "INSERT INTO piece_host_support_next(piece_key,host_key,support) "
                f"VALUES {placeholders} ON CONFLICT(piece_key,host_key) DO UPDATE "
                "SET support=support+excluded.support",
                parameters,
            )
            statement_calls += 1
            sizes = _files(path)
            if sizes["total"] > peak["total"]:
                peak = sizes
        connection.commit()
        wall = time.perf_counter() - started
        final_files = _files(path)
        if final_files["total"] > peak["total"]:
            peak = final_files
        logical = connection.execute(
            "SELECT COUNT(*), SUM(support) FROM piece_host_support_next"
        ).fetchone()
        integrity = connection.execute("PRAGMA quick_check").fetchone()
        return {
            "requested_batch_rows": requested_rows,
            "effective_batch_rows": batch_rows,
            "statement_calls": statement_calls,
            "input_rows": ROW_COUNT,
            "logical_rows": int(logical[0]),
            "support_sum": float(logical[1]),
            "wall_seconds": wall,
            "rows_per_second": ROW_COUNT / wall,
            "peak_files_bytes": peak,
            "final_files_bytes": final_files,
            "sqlite_variable_limit": variable_limit,
            "variable_limit_source": limit_source,
            "journal_mode": str(journal[0]).lower() if journal else None,
            "quick_check": integrity[0] if integrity else None,
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="sktlm-sqlite-batches-") as temporary:
        root = Path(temporary)
        cases = [_run_case(root, batch_rows) for batch_rows in BATCH_ROWS]
    payload = {
        "schema_version": "sktlm-s1m2-sqlite-batch-benchmark/v1",
        "purpose": "engineering strategy evidence only; not scientific qualification",
        "row_count_per_case": ROW_COUNT,
        "unique_rows": UNIQUE_ROWS,
        "bind_cap": MAX_BIND_PARAMETERS,
        "cache_size": "sqlite_default_unchanged",
        "rss": "not sampled; no dependency-free exact peak RSS source used",
        "cases": cases,
        "total_wall_seconds": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

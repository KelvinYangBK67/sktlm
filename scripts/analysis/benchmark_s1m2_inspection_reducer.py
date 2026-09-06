#!/usr/bin/env python3
"""Bounded one-shot benchmark for the S1M2 inspection shard reducer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Iterable

from sktlm.latent.phonology import Phoneme, PhonologicalForm
from sktlm.latent.store import LexiconStore


TABLE_QUERIES = (
    "SELECT form_key, expected_count FROM inspection_counts ORDER BY form_key",
    "SELECT form_key, expected_count, occurrence_support "
    "FROM inspection_piece_counts ORDER BY form_key",
    "SELECT form_key, surface, expected_mass "
    "FROM surface_usage ORDER BY form_key, surface",
    "SELECT form_key, context, expected_mass "
    "FROM context_usage ORDER BY form_key, context",
)


def _form(index: int) -> PhonologicalForm:
    symbols = tuple(Phoneme)
    base = len(symbols)
    return PhonologicalForm(
        (
            symbols[index % base],
            symbols[(index // base) % base],
            symbols[(index // (base * base)) % base],
        )
    )


def _chunks(total: int, size: int) -> Iterable[range]:
    for start in range(0, total, size):
        yield range(start, min(total, start + size))


def _write_fixture(root: Path, *, rows: int, batch_size: int) -> tuple[Path, ...]:
    legacy_paths = tuple(root / f"{name}.tsv" for name in ("counts", "pieces", "surfaces", "contexts"))
    aggregate_path = root / "aggregates.sqlite"
    connection = sqlite3.connect(aggregate_path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.executescript(
        "CREATE TABLE count_rows (row_number INTEGER PRIMARY KEY, "
        "form_key TEXT NOT NULL, expected_count REAL NOT NULL);"
        "CREATE TABLE piece_rows (row_number INTEGER PRIMARY KEY, "
        "form_key TEXT NOT NULL, expected_count REAL NOT NULL, "
        "occurrence_support INTEGER NOT NULL);"
        "CREATE TABLE surface_rows (row_number INTEGER PRIMARY KEY, "
        "form_key TEXT NOT NULL, surface TEXT NOT NULL, "
        "expected_mass REAL NOT NULL);"
        "CREATE TABLE context_rows (row_number INTEGER PRIMARY KEY, "
        "form_key TEXT NOT NULL, context TEXT NOT NULL, "
        "expected_mass REAL NOT NULL);"
    )
    handles = [path.open("w", encoding="utf-8", newline="") for path in legacy_paths]
    try:
        unique = max(1, rows // 2)
        for indices in _chunks(rows, batch_size):
            count_rows = []
            piece_rows = []
            surface_rows = []
            context_rows = []
            for index in indices:
                key = _form(index % unique).key
                value = 0.125 + (index % 17) / 32.0
                surface = f"surface-{index % 31}"
                context = f"left-{index % 13}>right-{index % 19}"
                row_number = index + 1
                count_rows.append((row_number, key, value))
                piece_rows.append((row_number, key, value, 1))
                surface_rows.append((row_number, key, surface, value))
                context_rows.append((row_number, key, context, value))
                handles[0].write(f"{key}\t{float(value).hex()}\n")
                handles[1].write(f"{key}\t{float(value).hex()}\t1\n")
                handles[2].write(
                    f"{key}\t{json.dumps(surface)}\t{float(value).hex()}\n"
                )
                handles[3].write(
                    f"{key}\t{json.dumps(context)}\t{float(value).hex()}\n"
                )
            connection.executemany("INSERT INTO count_rows VALUES (?, ?, ?)", count_rows)
            connection.executemany("INSERT INTO piece_rows VALUES (?, ?, ?, ?)", piece_rows)
            connection.executemany("INSERT INTO surface_rows VALUES (?, ?, ?, ?)", surface_rows)
            connection.executemany("INSERT INTO context_rows VALUES (?, ?, ?, ?)", context_rows)
        connection.commit()
    finally:
        connection.close()
        for handle in handles:
            handle.close()
    return (*legacy_paths, aggregate_path)


def _legacy_merge(store: LexiconStore, paths: tuple[Path, ...], batch_size: int) -> None:
    counts: list[tuple[PhonologicalForm, float]] = []
    with paths[0].open(encoding="utf-8") as handle:
        for line in handle:
            key, value = line.rstrip("\n").split("\t", 1)
            counts.append((PhonologicalForm.from_key(key), float.fromhex(value)))
            if len(counts) >= batch_size:
                store.add_counts(counts, table="inspection_counts")
                counts.clear()
    if counts:
        store.add_counts(counts, table="inspection_counts")

    pieces: list[tuple[PhonologicalForm, float, int]] = []
    with paths[1].open(encoding="utf-8") as handle:
        for line in handle:
            key, value, support = line.rstrip("\n").split("\t", 2)
            pieces.append(
                (PhonologicalForm.from_key(key), float.fromhex(value), int(support))
            )
            if len(pieces) >= batch_size:
                store.add_inspection_piece_counts(pieces)
                pieces.clear()
    if pieces:
        store.add_inspection_piece_counts(pieces)

    for kind, path in zip(("surfaces", "contexts"), paths[2:4], strict=True):
        usage: list[tuple[str, str, float]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                key, encoded, mass = line.rstrip("\n").split("\t", 2)
                usage.append((key, str(json.loads(encoded)), float.fromhex(mass)))
                if len(usage) >= batch_size:
                    store.add_usage(**{kind: usage})
                    usage.clear()
        if usage:
            store.add_usage(**{kind: usage})


def _digest(store: LexiconStore) -> str:
    digest = hashlib.sha256()
    for query in TABLE_QUERIES:
        for row in store.connection.execute(query):
            digest.update(repr(tuple(row)).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def run(*, rows: int, batch_size: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="sktlm-opt13-") as raw_root:
        root = Path(raw_root)
        paths = _write_fixture(root, rows=rows, batch_size=batch_size)
        legacy = LexiconStore(root / "legacy.sqlite")
        candidate = LexiconStore(root / "candidate.sqlite")
        try:
            legacy.begin_piece_inspection()
            candidate.begin_piece_inspection()
            started = time.perf_counter()
            _legacy_merge(legacy, paths, batch_size)
            legacy_seconds = time.perf_counter() - started
            started = time.perf_counter()
            candidate.merge_inspection_shard(
                paths[4],
                row_counts={name: rows for name in ("counts", "pieces", "surfaces", "contexts")},
            )
            candidate_seconds = time.perf_counter() - started
            legacy_digest = _digest(legacy)
            candidate_digest = _digest(candidate)
            return {
                "schema_version": "sktlm-s1m2-opt13-reducer-benchmark/v1",
                "rows_per_table": rows,
                "total_rows": rows * 4,
                "batch_size": batch_size,
                "legacy_seconds": legacy_seconds,
                "candidate_seconds": candidate_seconds,
                "improvement_percent": 100.0 * (legacy_seconds - candidate_seconds) / legacy_seconds,
                "legacy_digest": legacy_digest,
                "candidate_digest": candidate_digest,
                "exact_table_equivalence": legacy_digest == candidate_digest,
                "aggregate_shard_bytes": paths[4].stat().st_size,
                "legacy_tsv_bytes": sum(path.stat().st_size for path in paths[:4]),
            }
        finally:
            legacy.close()
            candidate.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=5_000)
    args = parser.parse_args()
    if args.rows < 1 or args.batch_size < 1:
        parser.error("--rows and --batch-size must be positive")
    print(json.dumps(run(rows=args.rows, batch_size=args.batch_size), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

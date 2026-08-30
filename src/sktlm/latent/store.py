"""Disk-backed lexical statistics for bounded-memory corpus passes."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from sktlm.latent.phonology import PhonologicalForm
from sktlm.latent.telemetry import RuntimeTelemetry


TRAINING_CHECKPOINT_KEY = "training_checkpoint"


class LexiconScorer:
    """Unigram scorer with an explicit reweighted MDL type penalty.

    The declared complexity is

        R(c) = lambda * sum_w log(1 + c_w / tau)

    and the per-use score subtracts its exact one-count increment at the
    previous pass's count:

        lambda * log(1 + 1 / (tau + c_w)).
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        alpha: float,
        complexity_weight: float,
        complexity_tau: float,
        cache_size: int,
        telemetry: RuntimeTelemetry,
    ) -> None:
        self.connection = connection
        self.alpha = alpha
        self.complexity_weight = complexity_weight
        self.complexity_tau = complexity_tau
        self.cache_size = cache_size
        self.telemetry = telemetry
        self._cache: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self.score_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.sqlite_selects = 0
        self.sqlite_seconds = 0.0
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) FROM lexicon"
        ).fetchone()
        assert row is not None
        self.vocabulary_size = int(row[0])
        self.total_count = float(row[1])
        self.denominator = self.total_count + alpha * self.vocabulary_size

    def _lookup(self, key: str) -> tuple[float, float]:
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            self._cache.move_to_end(key)
            return cached
        self.cache_misses += 1
        started = time.perf_counter()
        row = self.connection.execute(
            "SELECT expected_count, probability FROM lexicon WHERE form_key = ?",
            (key,),
        ).fetchone()
        self.sqlite_seconds += time.perf_counter() - started
        self.sqlite_selects += 1
        if row is None:
            count = 0.0
            probability = (
                self.alpha / self.denominator if self.denominator > 0.0 else 1.0
            )
        else:
            count = float(row[0])
            probability = float(row[1])
        value = (count, probability)
        self._cache[key] = value
        if len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return value

    def score(self, form: PhonologicalForm) -> float:
        self.score_calls += 1
        count, probability = self._lookup(form.key)
        penalty = self.complexity_weight * math.log1p(
            1.0 / (self.complexity_tau + count)
        )
        return math.log(max(probability, 1e-300)) - penalty


class LexiconStore:
    def __init__(
        self,
        path: Path,
        *,
        telemetry: RuntimeTelemetry | None = None,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.telemetry = telemetry or RuntimeTelemetry()
        self._scorers: list[LexiconScorer] = []
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def set_metadata(self, key: str, value: str) -> None:
        with self.connection:
            self._set_metadata(key, value)

    def _set_metadata(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_metadata(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,),
        ).fetchone()
        return None if row is None else str(row[0])

    def has_lexicon(self) -> bool:
        return self.has_table("lexicon")

    def has_table(self, name: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
        return row is not None

    def load_training_checkpoint(self) -> dict[str, Any] | None:
        payload = self.get_metadata(TRAINING_CHECKPOINT_KEY)
        return None if payload is None else json.loads(payload)

    def _set_training_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self._set_metadata(
            TRAINING_CHECKPOINT_KEY,
            json.dumps(
                checkpoint,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def save_training_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        with self.connection:
            self._set_training_checkpoint(checkpoint)

    def begin_count_pass(
        self,
        *,
        resume: bool,
        checkpoint: dict[str, Any],
    ) -> None:
        with self.connection:
            if not resume:
                self.connection.execute("DROP TABLE IF EXISTS counts_next")
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS counts_next ("
                "form_key TEXT PRIMARY KEY, "
                "expected_count REAL NOT NULL"
                ") WITHOUT ROWID"
            )
            self._set_training_checkpoint(checkpoint)

    def _has_expanded_form_payload(self, table: str) -> bool:
        if table not in {'counts_next', 'inspection_counts'}:
            raise ValueError(f'Unsupported count table: {table}')
        return any(
            str(row[1]) == 'iast'
            for row in self.connection.execute(f'PRAGMA table_info({table})')
        )

    def _count_rows(
        self,
        counts: Iterable[tuple[PhonologicalForm, float]],
        *,
        expanded: bool,
    ) -> list[tuple[Any, ...]]:
        started = time.perf_counter()
        if expanded:
            rows = [
                (
                    form.key,
                    form.iast,
                    ' '.join(form.phoneme_ids),
                    float(value),
                )
                for form, value in counts
                if value > 0.0
            ]
        else:
            rows = [
                (form.key, float(value))
                for form, value in counts
                if value > 0.0
            ]
        self.telemetry.elapsed('sqlite_count_row_serialization', started)
        self.telemetry.increment('sqlite_count_rows_serialized', len(rows))
        return rows

    def _upsert_counts(
        self,
        counts: Iterable[tuple[PhonologicalForm, float]],
        *,
        table: str,
    ) -> None:
        expanded = self._has_expanded_form_payload(table)
        rows = self._count_rows(counts, expanded=expanded)
        started = time.perf_counter()
        if expanded:
            self.connection.executemany(
                f"INSERT INTO {table}(form_key, iast, phoneme_ids, expected_count) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(form_key) DO UPDATE SET "
                "expected_count = expected_count + excluded.expected_count",
                rows,
            )
        else:
            self.connection.executemany(
                f'INSERT INTO {table}(form_key, expected_count) VALUES (?, ?) '
                'ON CONFLICT(form_key) DO UPDATE SET '
                'expected_count = expected_count + excluded.expected_count',
                rows,
            )
        self.telemetry.elapsed('sqlite_count_upsert', started)
        self.telemetry.increment('sqlite_count_upsert_calls')
        self.telemetry.increment('sqlite_count_upsert_rows', len(rows))

    def add_counts(
        self,
        counts: Iterable[tuple[PhonologicalForm, float]],
        *,
        table: str = "counts_next",
    ) -> None:
        with self.connection:
            self._upsert_counts(counts, table=table)

    def begin_document_counts(self) -> None:
        started = time.perf_counter()
        if self.connection.in_transaction:
            raise RuntimeError("Cannot start a document inside an open transaction.")
        self.connection.execute("BEGIN IMMEDIATE")

        self.telemetry.elapsed('sqlite_document_begin', started)

    def add_document_counts(
        self,
        counts: Iterable[tuple[PhonologicalForm, float]],
    ) -> None:
        if not self.connection.in_transaction:
            raise RuntimeError("Document counts require an open transaction.")
        self._upsert_counts(counts, table="counts_next")

    def commit_document(self, checkpoint: dict[str, Any]) -> None:
        if not self.connection.in_transaction:
            raise RuntimeError("No document transaction is open.")
        self._set_training_checkpoint(checkpoint)
        started = time.perf_counter()
        self.connection.commit()
        self.telemetry.elapsed('sqlite_document_commit', started)
        self.telemetry.increment('sqlite_documents_committed')

    def rollback_document(self) -> None:
        if self.connection.in_transaction:
            self.connection.rollback()

    def finalize_count_pass(
        self,
        *,
        alpha: float,
        checkpoint: dict[str, Any],
    ) -> tuple[int, float]:
        row = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) FROM counts_next"
        ).fetchone()
        assert row is not None
        vocabulary_size = int(row[0])
        total_count = float(row[1])
        if vocabulary_size == 0 or total_count <= 0.0:
            raise ValueError("Count pass produced an empty latent lexicon.")
        denominator = total_count + alpha * vocabulary_size
        with self.connection:
            if self.has_lexicon():
                self.connection.execute("DROP INDEX IF EXISTS lexicon_form_key")
                self.connection.execute("DROP TABLE lexicon")
            self.connection.execute(
                'CREATE TABLE lexicon ('
                'form_key TEXT PRIMARY KEY, '
                'expected_count REAL NOT NULL, '
                'probability REAL NOT NULL'
                ') WITHOUT ROWID'
            )
            self.connection.execute(
                'INSERT INTO lexicon(form_key, expected_count, probability) '
                'SELECT form_key, expected_count, '
                '(expected_count + ?) / ? FROM counts_next',
                (alpha, denominator),
            )
            self.connection.execute("DROP TABLE counts_next")
            self._set_training_checkpoint(checkpoint)
        return vocabulary_size, total_count

    def scorer(
        self,
        *,
        alpha: float,
        complexity_weight: float,
        complexity_tau: float,
        cache_size: int,
    ) -> LexiconScorer:
        if not self.has_lexicon():
            raise RuntimeError("Cannot score before the neutral count pass.")
        scorer = LexiconScorer(
            self.connection,
            alpha=alpha,
            complexity_weight=complexity_weight,
            complexity_tau=complexity_tau,
            cache_size=cache_size,
            telemetry=self.telemetry,
        )
        self._scorers.append(scorer)
        return scorer

    def runtime_payload(self) -> dict[str, Any]:
        payload = self.telemetry.payload()
        payload['lexical_scorers'] = [
            {
                'score_calls': scorer.score_calls,
                'cache_hits': scorer.cache_hits,
                'cache_misses': scorer.cache_misses,
                'sqlite_selects': scorer.sqlite_selects,
                'sqlite_seconds': scorer.sqlite_seconds,
                'cache_size': scorer.cache_size,
            }
            for scorer in self._scorers
        ]
        return payload

    def begin_inspection(self) -> None:
        with self.connection:
            self.connection.execute("DROP TABLE IF EXISTS inspection_counts")
            self.connection.execute(
                "CREATE TABLE inspection_counts ("
                "form_key TEXT PRIMARY KEY, "
                "expected_count REAL NOT NULL"
                ") WITHOUT ROWID"
            )
            self.connection.execute("DROP TABLE IF EXISTS surface_usage")
            self.connection.execute(
                "CREATE TABLE surface_usage ("
                "form_key TEXT NOT NULL, surface TEXT NOT NULL, expected_mass REAL NOT NULL, "
                "PRIMARY KEY(form_key, surface))"
            )
            self.connection.execute("DROP TABLE IF EXISTS context_usage")
            self.connection.execute(
                "CREATE TABLE context_usage ("
                "form_key TEXT NOT NULL, context TEXT NOT NULL, expected_mass REAL NOT NULL, "
                "PRIMARY KEY(form_key, context))"
            )

    def add_usage(
        self,
        *,
        surfaces: Iterable[tuple[str, str, float]] = (),
        contexts: Iterable[tuple[str, str, float]] = (),
    ) -> None:
        self.connection.executemany(
            "INSERT INTO surface_usage(form_key, surface, expected_mass) VALUES (?, ?, ?) "
            "ON CONFLICT(form_key, surface) DO UPDATE SET "
            "expected_mass = expected_mass + excluded.expected_mass",
            tuple(surfaces),
        )
        self.connection.executemany(
            "INSERT INTO context_usage(form_key, context, expected_mass) VALUES (?, ?, ?) "
            "ON CONFLICT(form_key, context) DO UPDATE SET "
            "expected_mass = expected_mass + excluded.expected_mass",
            tuple(contexts),
        )
        self.connection.commit()

    def export_lexicon(self, path: Path, *, usage_threshold: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        query = """
            SELECT i.form_key, i.expected_count,
                   COALESCE(l.probability, 0.0),
                   COALESCE(s.variant_count, 0),
                   COALESCE(c.context_count, 0)
            FROM inspection_counts i
            LEFT JOIN lexicon l ON l.form_key = i.form_key
            LEFT JOIN (
                SELECT form_key, COUNT(*) AS variant_count
                FROM surface_usage WHERE expected_mass >= ? GROUP BY form_key
            ) s ON s.form_key = i.form_key
            LEFT JOIN (
                SELECT form_key, COUNT(*) AS context_count
                FROM context_usage WHERE expected_mass >= ? GROUP BY form_key
            ) c ON c.form_key = i.form_key
            ORDER BY i.expected_count DESC, i.form_key
        """
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(
                (
                    "form_key",
                    "latent_form",
                    "phoneme_ids",
                    "expected_count",
                    "probability",
                    "number_of_surface_variants",
                    "number_of_contexts",
                )
            )
            for row in self.connection.execute(
                query,
                (usage_threshold, usage_threshold),
            ):
                form = PhonologicalForm.from_key(str(row[0]))
                writer.writerow(
                    (
                        row[0],
                        form.iast,
                        ' '.join(form.phoneme_ids),
                        row[1],
                        row[2],
                        row[3],
                        row[4],
                    )
                )

    def complexity_summary(
        self,
        *,
        weight: float,
        tau: float,
        low_count_threshold: float,
    ) -> dict[str, float | int]:
        row = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0), "
            "COALESCE(SUM(CASE WHEN expected_count <= ? THEN 1 ELSE 0 END), 0), "
            "COALESCE(SUM(log(1.0 + expected_count / ?)), 0.0) "
            "FROM inspection_counts",
            (low_count_threshold, tau),
        ).fetchone()
        assert row is not None
        raw = float(row[3])
        return {
            "active_lexical_types": int(row[0]),
            "expected_lexical_tokens": float(row[1]),
            "low_count_types": int(row[2]),
            "low_count_threshold": low_count_threshold,
            "complexity_raw": raw,
            "complexity_weight": weight,
            "complexity_tau": tau,
            "complexity_penalty": weight * raw,
        }

    def top_lexicon(self, limit: int) -> list[tuple[str, float, float]]:
        return [
            (
                PhonologicalForm.from_key(str(row[0])).iast,
                float(row[1]),
                float(row[2] or 0.0),
            )
            for row in self.connection.execute(
                "SELECT form_key, expected_count, "
                "(SELECT probability FROM lexicon l WHERE l.form_key = i.form_key) "
                "FROM inspection_counts i ORDER BY expected_count DESC, form_key LIMIT ?",
                (limit,),
            )
        ]

    def low_count_lexicon(
        self,
        limit: int,
        threshold: float,
    ) -> list[tuple[str, float]]:
        return [
            (PhonologicalForm.from_key(str(row[0])).iast, float(row[1]))
            for row in self.connection.execute(
                "SELECT form_key, expected_count FROM inspection_counts "
                "WHERE expected_count <= ? ORDER BY expected_count DESC, form_key LIMIT ?",
                (threshold, limit),
            )
        ]

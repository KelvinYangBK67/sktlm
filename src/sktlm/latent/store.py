"""Disk-backed lexical statistics for bounded-memory corpus passes."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import time
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, Iterable

from sktlm.latent.phonology import PhonologicalForm
from sktlm.latent.telemetry import RuntimeTelemetry
from sktlm.latent.vocabulary import (
    BASE_FORMS,
    BASE_UNIT_COUNT,
    FrozenVocabulary,
    VocabularyEntry,
    allowed_key_sha256,
)
from sktlm.pieces.scorer import GeometricPhonemeBaseMeasure


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


class PieceStoreScorer:
    """Bounded-cache P1a scorer over the finite active SQLite piece state."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        alpha: float,
        complexity_weight: float,
        complexity_kappa: float,
        complexity_beta: float,
        complexity_tau: float,
        base_stop_probability: float,
        cache_size: int,
        telemetry: RuntimeTelemetry,
    ) -> None:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='piece_lexicon'"
        ).fetchone():
            raise RuntimeError("Cannot score before the neutral piece-count pass.")
        self.connection = connection
        self.alpha = alpha
        self.complexity_weight = complexity_weight
        self.complexity_kappa = complexity_kappa
        self.complexity_beta = complexity_beta
        self.complexity_tau = complexity_tau
        self.base_measure = GeometricPhonemeBaseMeasure(base_stop_probability)
        self.cache_size = cache_size
        self.telemetry = telemetry
        self._cache: OrderedDict[str, float] = OrderedDict()
        self.score_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.sqlite_selects = 0
        self.store_lookups = 0
        self.sqlite_seconds = 0.0
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) "
            "FROM piece_lexicon"
        ).fetchone()
        assert row is not None
        self.active_piece_types = int(row[0])
        self.total_count = float(row[1])
        self.denominator = self.total_count + alpha

    def _lookup(self, key: str) -> float:
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            self._cache.move_to_end(key)
            return cached
        self.cache_misses += 1
        started = time.perf_counter()
        row = self.connection.execute(
            "SELECT expected_count FROM piece_lexicon WHERE form_key = ?",
            (key,),
        ).fetchone()
        self.sqlite_seconds += time.perf_counter() - started
        self.sqlite_selects += 1
        self.store_lookups += 1
        count = 0.0 if row is None else float(row[0])
        self._cache[key] = count
        if len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return count

    def probability(self, piece: PhonologicalForm, count: float) -> float:
        return (
            count + self.alpha * self.base_measure.probability(piece)
        ) / self.denominator

    def score(self, piece: PhonologicalForm) -> float:
        self.score_calls += 1
        count = self._lookup(piece.key)
        amplitude = self.complexity_weight * (
            self.complexity_kappa
            + self.complexity_beta * len(piece.symbols)
        )
        penalty = amplitude * math.log1p(
            1.0 / (self.complexity_tau + count)
        )
        return math.log(max(self.probability(piece, count), 1e-300)) - penalty


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
        self._piece_scorers: list[PieceStoreScorer] = []
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

    def begin_piece_count_pass(
        self,
        *,
        resume: bool,
        checkpoint: dict[str, Any],
    ) -> None:
        """Start or resume one crash-safe S1M2 lexical/piece count pass."""

        with self.connection:
            if not resume:
                self.connection.execute("DROP TABLE IF EXISTS piece_counts_next")
                self.connection.execute(
                    "DROP TABLE IF EXISTS lexical_diagnostics_next"
                )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS piece_counts_next ("
                "form_key TEXT PRIMARY KEY, "
                "expected_count REAL NOT NULL, "
                "occurrence_support INTEGER NOT NULL"
                ") WITHOUT ROWID"
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS lexical_diagnostics_next ("
                "form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL"
                ") WITHOUT ROWID"
            )
            self._set_training_checkpoint(checkpoint)

    def add_document_piece_counts(
        self,
        counts: Iterable[tuple[PhonologicalForm, float, int]],
    ) -> None:
        if not self.connection.in_transaction:
            raise RuntimeError("Document piece counts require an open transaction.")
        rows = [
            (piece.key, float(value), int(support))
            for piece, value, support in counts
            if value > 0.0
        ]
        started = time.perf_counter()
        self.connection.executemany(
            "INSERT INTO piece_counts_next("
            "form_key, expected_count, occurrence_support"
            ") VALUES (?, ?, ?) "
            "ON CONFLICT(form_key) DO UPDATE SET "
            "expected_count = expected_count + excluded.expected_count, "
            "occurrence_support = occurrence_support + excluded.occurrence_support",
            rows,
        )
        self.telemetry.elapsed("sqlite_piece_count_upsert", started)
        self.telemetry.increment("sqlite_piece_count_upsert_calls")
        self.telemetry.increment("sqlite_piece_count_upsert_rows", len(rows))

    def add_document_lexical_diagnostics(
        self,
        counts: Iterable[tuple[PhonologicalForm, float]],
    ) -> None:
        if not self.connection.in_transaction:
            raise RuntimeError(
                "Document lexical diagnostics require an open transaction."
            )
        rows = [
            (form.key, float(value))
            for form, value in counts
            if value > 0.0
        ]
        started = time.perf_counter()
        self.connection.executemany(
            "INSERT INTO lexical_diagnostics_next(form_key, expected_count) "
            "VALUES (?, ?) ON CONFLICT(form_key) DO UPDATE SET "
            "expected_count = expected_count + excluded.expected_count",
            rows,
        )
        self.telemetry.elapsed("sqlite_lexical_diagnostic_upsert", started)
        self.telemetry.increment("sqlite_lexical_diagnostic_upsert_calls")
        self.telemetry.increment("sqlite_lexical_diagnostic_upsert_rows", len(rows))

    def finalize_piece_count_pass(
        self,
        *,
        min_reuse_occurrences: int,
        checkpoint: dict[str, Any],
    ) -> tuple[int, int, float]:
        """Freeze the next finite active piece map and retain all diagnostics."""

        row = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) "
            "FROM piece_counts_next"
        ).fetchone()
        assert row is not None
        all_piece_types = int(row[0])
        if all_piece_types == 0 or float(row[1]) <= 0.0:
            raise ValueError("Piece count pass produced an empty inventory.")
        with self.connection:
            self.connection.execute("DROP TABLE IF EXISTS piece_inventory")
            self.connection.execute(
                "ALTER TABLE piece_counts_next RENAME TO piece_inventory"
            )
            self.connection.execute("DROP TABLE IF EXISTS lexical_diagnostics")
            self.connection.execute(
                "ALTER TABLE lexical_diagnostics_next RENAME TO lexical_diagnostics"
            )
            self.connection.execute("DROP TABLE IF EXISTS piece_lexicon")
            self.connection.execute(
                "CREATE TABLE piece_lexicon ("
                "form_key TEXT PRIMARY KEY, "
                "expected_count REAL NOT NULL, "
                "occurrence_support INTEGER NOT NULL"
                ") WITHOUT ROWID"
            )
            self.connection.execute(
                "INSERT INTO piece_lexicon("
                "form_key, expected_count, occurrence_support"
                ") SELECT form_key, expected_count, occurrence_support "
                "FROM piece_inventory WHERE expected_count > 0.0 AND "
                "(instr(form_key, '.') = 0 OR occurrence_support >= ?)",
                (min_reuse_occurrences,),
            )
            active = self.connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) "
                "FROM piece_lexicon"
            ).fetchone()
            assert active is not None
            checkpoint["history"][-1].update(
                {
                    "piece_types": all_piece_types,
                    "active_piece_types": int(active[0]),
                    "active_piece_count_total": float(active[1]),
                }
            )
            self._set_training_checkpoint(checkpoint)
        if int(active[0]) == 0 or float(active[1]) <= 0.0:
            raise ValueError("Piece activation produced an empty active state.")
        return all_piece_types, int(active[0]), float(active[1])

    def piece_scorer(
        self,
        *,
        alpha: float,
        complexity_weight: float,
        complexity_kappa: float,
        complexity_beta: float,
        complexity_tau: float,
        base_stop_probability: float,
        cache_size: int,
    ) -> PieceStoreScorer:
        scorer = PieceStoreScorer(
            self.connection,
            alpha=alpha,
            complexity_weight=complexity_weight,
            complexity_kappa=complexity_kappa,
            complexity_beta=complexity_beta,
            complexity_tau=complexity_tau,
            base_stop_probability=base_stop_probability,
            cache_size=cache_size,
            telemetry=self.telemetry,
        )
        self._piece_scorers.append(scorer)
        return scorer

    def load_frozen_vocabulary(self) -> FrozenVocabulary | None:
        """Load and validate the durable pass-1 vocabulary, if present."""

        if not self.has_table("frozen_vocabulary"):
            return None
        header_text = self.get_metadata("frozen_vocabulary_header")
        if header_text is None:
            raise RuntimeError("Frozen vocabulary is missing its metadata header.")
        header = json.loads(header_text)
        entries = tuple(
            VocabularyEntry(
                rank=int(row[0]),
                kind=str(row[1]),
                form=PhonologicalForm.from_key(str(row[2])),
                pass1_expected_count=float(row[3]),
            )
            for row in self.connection.execute(
                "SELECT rank, kind, form_key, pass1_expected_count "
                "FROM frozen_vocabulary ORDER BY rank"
            )
        )
        return FrozenVocabulary(
            total_budget=int(header["total_budget"]),
            entries=entries,
            allowed_sha256=str(header["allowed_key_sha256"]),
        )

    def select_and_freeze_vocabulary(self, budget: int) -> FrozenVocabulary:
        """Select pass-1 identities, project pruned counts, and freeze atomically."""

        existing = self.load_frozen_vocabulary()
        if existing is not None:
            if existing.total_budget != budget:
                raise ValueError(
                    "Stored frozen vocabulary does not match requested vocab_budget."
                )
            return existing
        if budget < BASE_UNIT_COUNT:
            raise ValueError(
                f"vocab_budget must be >= {BASE_UNIT_COUNT}; got {budget}"
            )
        if not self.has_table("counts_next"):
            raise RuntimeError("Pass-1 counts are unavailable for vocabulary selection.")

        learned_capacity = budget - BASE_UNIT_COUNT
        selected_rows = tuple(
            (str(row[0]), float(row[1]))
            for row in self.connection.execute(
                "SELECT form_key, expected_count FROM counts_next "
                "WHERE instr(form_key, '.') > 0 "
                "ORDER BY expected_count DESC, form_key ASC LIMIT ?",
                (learned_capacity,),
            )
        )
        selected_keys = {key for key, _ in selected_rows}
        base_counts: Counter[str] = Counter()
        for row in self.connection.execute(
            "SELECT form_key, expected_count FROM counts_next ORDER BY form_key"
        ):
            key = str(row[0])
            if key in selected_keys:
                continue
            value = float(row[1])
            form = PhonologicalForm.from_key(key)
            for symbol in form.symbols:
                base_counts[symbol.value] += value

        entries: list[VocabularyEntry] = []
        for rank, form in enumerate(BASE_FORMS, 1):
            entries.append(
                VocabularyEntry(
                    rank=rank,
                    kind="base",
                    form=form,
                    pass1_expected_count=float(base_counts[form.key]),
                )
            )
        for learned_rank, (key, value) in enumerate(selected_rows, 1):
            entries.append(
                VocabularyEntry(
                    rank=BASE_UNIT_COUNT + learned_rank,
                    kind="lexical",
                    form=PhonologicalForm.from_key(key),
                    pass1_expected_count=value,
                )
            )
        digest = allowed_key_sha256(entry.form.key for entry in entries)
        vocabulary = FrozenVocabulary(
            total_budget=budget,
            entries=tuple(entries),
            allowed_sha256=digest,
        )

        with self.connection:
            self.connection.execute("DROP TABLE IF EXISTS counts_frozen")
            self.connection.execute(
                "CREATE TABLE counts_frozen ("
                "form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL"
                ") WITHOUT ROWID"
            )
            self.connection.executemany(
                "INSERT INTO counts_frozen(form_key, expected_count) VALUES (?, ?)",
                (
                    (entry.form.key, entry.pass1_expected_count)
                    for entry in vocabulary.entries
                ),
            )
            self.connection.execute("DROP TABLE counts_next")
            self.connection.execute("ALTER TABLE counts_frozen RENAME TO counts_next")
            self.connection.execute(
                "CREATE TABLE frozen_vocabulary ("
                "rank INTEGER PRIMARY KEY, kind TEXT NOT NULL, "
                "form_key TEXT NOT NULL UNIQUE, "
                "pass1_expected_count REAL NOT NULL"
                ")"
            )
            self.connection.executemany(
                "INSERT INTO frozen_vocabulary("
                "rank, kind, form_key, pass1_expected_count"
                ") VALUES (?, ?, ?, ?)",
                (
                    (
                        entry.rank,
                        entry.kind,
                        entry.form.key,
                        entry.pass1_expected_count,
                    )
                    for entry in vocabulary.entries
                ),
            )
            self._set_metadata(
                "frozen_vocabulary_header",
                json.dumps(
                    vocabulary.checkpoint_payload(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        return vocabulary

    def ensure_frozen_count_keys(self, vocabulary: FrozenVocabulary) -> None:
        """Retain every frozen parameter, including zero-count base units."""

        stored = self.load_frozen_vocabulary()
        if stored is None or stored.allowed_sha256 != vocabulary.allowed_sha256:
            raise RuntimeError("Frozen vocabulary is missing or changed.")
        unexpected = self.connection.execute(
            "SELECT c.form_key FROM counts_next c "
            "LEFT JOIN frozen_vocabulary v ON v.form_key = c.form_key "
            "WHERE v.form_key IS NULL LIMIT 1"
        ).fetchone()
        if unexpected is not None:
            raise RuntimeError(
                f"OOV form escaped frozen-vocabulary projection: {unexpected[0]}"
            )
        with self.connection:
            if self._has_expanded_form_payload("counts_next"):
                self.connection.executemany(
                    "INSERT OR IGNORE INTO counts_next("
                    "form_key, iast, phoneme_ids, expected_count"
                    ") VALUES (?, ?, ?, 0.0)",
                    (
                        (
                            entry.form.key,
                            entry.form.iast,
                            " ".join(entry.form.phoneme_ids),
                        )
                        for entry in vocabulary.entries
                    ),
                )
            else:
                self.connection.execute(
                    "INSERT OR IGNORE INTO counts_next(form_key, expected_count) "
                    "SELECT form_key, 0.0 FROM frozen_vocabulary"
                )

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
        payload["piece_scorers"] = [
            {
                "score_calls": scorer.score_calls,
                "cache_hits": scorer.cache_hits,
                "cache_misses": scorer.cache_misses,
                "sqlite_selects": scorer.sqlite_selects,
                "sqlite_seconds": scorer.sqlite_seconds,
                "cache_size": scorer.cache_size,
                "active_piece_types": scorer.active_piece_types,
                "active_count_total": scorer.total_count,
            }
            for scorer in self._piece_scorers
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

    def begin_piece_inspection(self) -> None:
        self.begin_inspection()
        with self.connection:
            self.connection.execute(
                "DROP TABLE IF EXISTS inspection_piece_counts"
            )
            self.connection.execute(
                "CREATE TABLE inspection_piece_counts ("
                "form_key TEXT PRIMARY KEY, "
                "expected_count REAL NOT NULL, "
                "occurrence_support INTEGER NOT NULL"
                ") WITHOUT ROWID"
            )

    def add_inspection_piece_counts(
        self,
        counts: Iterable[tuple[PhonologicalForm, float, int]],
    ) -> None:
        rows = [
            (piece.key, float(value), int(support))
            for piece, value, support in counts
            if value > 0.0
        ]
        with self.connection:
            self.connection.executemany(
                "INSERT INTO inspection_piece_counts("
                "form_key, expected_count, occurrence_support"
                ") VALUES (?, ?, ?) ON CONFLICT(form_key) DO UPDATE SET "
                "expected_count = expected_count + excluded.expected_count, "
                "occurrence_support = occurrence_support + excluded.occurrence_support",
                rows,
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

    def export_piece_inventory(
        self,
        path: Path,
        *,
        alpha: float,
        complexity_weight: float,
        complexity_kappa: float,
        complexity_beta: float,
        complexity_tau: float,
        base_stop_probability: float,
    ) -> None:
        """Export final piece counts with the fixed active scoring state."""

        active_row = self.connection.execute(
            "SELECT COALESCE(SUM(expected_count), 0.0) FROM piece_lexicon"
        ).fetchone()
        assert active_row is not None
        denominator = float(active_row[0]) + alpha
        base = GeometricPhonemeBaseMeasure(base_stop_probability)
        query = (
            "SELECT i.form_key, i.expected_count, i.occurrence_support, "
            "a.expected_count FROM inspection_piece_counts i "
            "LEFT JOIN piece_lexicon a ON a.form_key = i.form_key "
            "ORDER BY i.expected_count DESC, i.form_key"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(
                (
                    "piece_key",
                    "piece",
                    "phoneme_ids",
                    "length",
                    "expected_count",
                    "occurrence_support",
                    "active",
                    "active_parameter_count",
                    "model_probability",
                    "model_log_score",
                )
            )
            for key, expected, support, active_raw in self.connection.execute(query):
                piece = PhonologicalForm.from_key(str(key))
                active_count = 0.0 if active_raw is None else float(active_raw)
                probability = (
                    active_count + alpha * base.probability(piece)
                ) / denominator
                amplitude = complexity_weight * (
                    complexity_kappa + complexity_beta * len(piece.symbols)
                )
                score = math.log(max(probability, 1e-300)) - amplitude * math.log1p(
                    1.0 / (complexity_tau + active_count)
                )
                writer.writerow(
                    (
                        key,
                        piece.iast,
                        " ".join(piece.phoneme_ids),
                        len(piece.symbols),
                        expected,
                        support,
                        int(active_raw is not None),
                        active_count,
                        probability,
                        score,
                    )
                )

    def export_lexical_diagnostics(
        self,
        path: Path,
        *,
        usage_threshold: float,
    ) -> None:
        """Export S1M2 lexical-form counts without treating them as parameters."""

        path.parent.mkdir(parents=True, exist_ok=True)
        query = """
            SELECT i.form_key, i.expected_count,
                   COALESCE(s.variant_count, 0),
                   COALESCE(c.context_count, 0)
            FROM inspection_counts i
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
                    "number_of_surface_variants",
                    "number_of_contexts",
                    "parameter_role",
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
                        " ".join(form.phoneme_ids),
                        row[1],
                        row[2],
                        row[3],
                        "diagnostic_not_scoring_parameter",
                    )
                )

    def piece_summary(
        self,
        *,
        low_support_threshold: float,
        complexity_weight: float,
        complexity_kappa: float,
        complexity_beta: float,
        complexity_tau: float,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0), "
            "COALESCE(SUM(CASE WHEN expected_count <= ? THEN 1 ELSE 0 END), 0) "
            "FROM inspection_piece_counts",
            (low_support_threshold,),
        ).fetchone()
        active = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) FROM piece_lexicon"
        ).fetchone()
        assert row is not None and active is not None
        length_counts = {
            str(int(length)): float(count)
            for length, count in self.connection.execute(
                "SELECT 1 + length(form_key) - length(replace(form_key, '.', '')), "
                "SUM(expected_count) FROM inspection_piece_counts GROUP BY 1 "
                "ORDER BY 1"
            )
        }
        reuse_distribution = {
            "0": 0,
            "1": 0,
            "2-4": 0,
            "5-9": 0,
            "10-99": 0,
            "100+": 0,
        }
        for support, types in self.connection.execute(
            "SELECT occurrence_support, COUNT(*) FROM inspection_piece_counts "
            "GROUP BY occurrence_support"
        ):
            value = int(support)
            bucket = (
                "0"
                if value == 0
                else "1"
                if value == 1
                else "2-4"
                if value < 5
                else "5-9"
                if value < 10
                else "10-99"
                if value < 100
                else "100+"
            )
            reuse_distribution[bucket] += int(types)
        complexity_raw = 0.0
        for key, count in self.connection.execute(
            "SELECT form_key, expected_count FROM inspection_piece_counts"
        ):
            length = str(key).count(".") + 1
            complexity_raw += (
                complexity_kappa + complexity_beta * length
            ) * math.log1p(float(count) / complexity_tau)
        return {
            "piece_types": int(row[0]),
            "expected_piece_tokens": float(row[1]),
            "low_support_piece_types": int(row[2]),
            "low_support_threshold": low_support_threshold,
            "active_piece_types": int(active[0]),
            "active_piece_count_total": float(active[1]),
            "expected_count_by_length": length_counts,
            "piece_types_by_occurrence_support": reuse_distribution,
            "complexity_raw": complexity_raw,
            "complexity_weight": complexity_weight,
            "complexity_penalty": complexity_weight * complexity_raw,
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

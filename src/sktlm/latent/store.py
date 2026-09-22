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
from sktlm.pieces.lattice import PieceIdentity, PieceRole
from sktlm.pieces.objective import (
    S1M2_REUSABLE_PIECES_V2,
    S1M2_REUSABLE_PIECES_V3,
    cross_host_reusable_count,
)
from sktlm.pieces.scorer import GeometricPhonemeBaseMeasure


TRAINING_CHECKPOINT_KEY = "training_checkpoint"
S1M2_RECONSTRUCTIBLE_TABLES = (
    "context_usage",
    "inspection_counts",
    "inspection_piece_counts",
    "inspection_piece_host_support",
    "lexical_diagnostics",
    "piece_inventory",
    "surface_usage",
)
S1M2_PASS_DIAGNOSTIC_TABLES = (
    "lexical_diagnostics",
    "lexical_diagnostics_next",
)


def _sqlite_cross_host_moments_valid(raw_count: object, squared_sum: object) -> int:
    """Expose the authoritative roundoff rule to rare SQL boundary cases."""

    try:
        cross_host_reusable_count(float(raw_count), float(squared_sum))
    except (TypeError, ValueError, OverflowError):
        return 0
    return 1


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
    """Versioned reusable-count scorer with exact SQLite lookup and bounded LRU."""

    piece_scores_are_role_neutral = True

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
        objective_model: str = S1M2_REUSABLE_PIECES_V2,
    ) -> None:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='piece_lexicon'"
        ).fetchone():
            raise RuntimeError("Cannot score before the neutral piece-count pass.")
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(piece_lexicon)")
        }
        v2_columns = {
            "raw_expected_count", "max_host_expected_usage", "reusable_count"
        }
        if not v2_columns <= columns:
            raise RuntimeError("V1 piece state cannot be scored as reusable_pieces_v2.")
        has_metadata = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'"
        ).fetchone()
        stored_model_row = (
            connection.execute(
                "SELECT value FROM metadata WHERE key='piece_objective_model'"
            ).fetchone()
            if has_metadata
            else None
        )
        stored_model = None if stored_model_row is None else str(stored_model_row[0])
        if objective_model == S1M2_REUSABLE_PIECES_V3:
            if stored_model != S1M2_REUSABLE_PIECES_V3 or (
                "sum_host_support_squared" not in columns
            ):
                raise RuntimeError(
                    "V2 piece state cannot be scored as reusable_pieces_v3."
                )
        elif objective_model == S1M2_REUSABLE_PIECES_V2:
            if stored_model == S1M2_REUSABLE_PIECES_V3 or (
                "sum_host_support_squared" in columns
            ):
                raise RuntimeError(
                    "V3 piece state cannot be scored as reusable_pieces_v2."
                )
        else:
            raise ValueError(f"unsupported reusable-piece objective: {objective_model}")
        self.objective_model = objective_model
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
            "SELECT COALESCE(SUM(CASE WHEN reusable_count > 0.0 THEN 1 ELSE 0 END), 0), "
            "COALESCE(SUM(reusable_count), 0.0) "
            "FROM piece_lexicon"
        ).fetchone()
        assert row is not None
        self.active_piece_types = int(row[0])
        self.total_count = float(row[1])
        self.denominator = self.total_count + alpha

    def _lookup(self, key: str) -> float:
        self.store_lookups += 1
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            self._cache.move_to_end(key)
            return cached
        self.cache_misses += 1
        started = time.perf_counter()
        row = self.connection.execute(
            "SELECT reusable_count FROM piece_lexicon WHERE form_key = ?",
            (key,),
        ).fetchone()
        self.sqlite_seconds += time.perf_counter() - started
        self.sqlite_selects += 1
        count = 0.0 if row is None else float(row[0])
        self._cache[key] = count
        if len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return count

    def probability(self, piece: PhonologicalForm, count: float) -> float:
        return (
            count + self.alpha * self.base_measure.probability(piece)
        ) / self.denominator

    def score_from_count_and_length(self, count: float, length: int) -> float:
        """Apply the unchanged production equation to an exact trie count."""

        base_probability = math.exp(
            self.base_measure.log_probability_for_length(length)
        )
        probability = (
            count + self.alpha * base_probability
        ) / self.denominator
        amplitude = self.complexity_weight * (
            self.complexity_kappa + self.complexity_beta * length
        )
        penalty = amplitude * math.log1p(
            1.0 / (self.complexity_tau + count)
        )
        return math.log(max(probability, 1e-300)) - penalty

    def score(self, piece: PhonologicalForm) -> float:
        return self.score_piece(piece, PieceRole.WHOLE)

    def score_piece(self, piece: PhonologicalForm, role: PieceRole) -> float:
        del role
        self.score_calls += 1
        count = self._lookup(piece.key)
        return self.score_from_count_and_length(count, len(piece.symbols))


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
        self.connection.create_function(
            "sktlm_cross_host_moments_valid",
            2,
            _sqlite_cross_host_moments_valid,
            deterministic=True,
        )
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _storage_bytes(self) -> dict[str, int]:
        paths = {
            "database": self.path,
            "wal": Path(f"{self.path}-wal"),
            "shm": Path(f"{self.path}-shm"),
        }
        sizes = {
            label: path.stat().st_size if path.is_file() else 0
            for label, path in paths.items()
        }
        sizes["total"] = sum(sizes.values())
        return sizes

    def storage_bytes(self) -> dict[str, int]:
        """Measure the three SQLite files at one explicit lifecycle boundary."""

        return self._storage_bytes()

    def checkpoint_and_truncate_wal_at_pass_boundary(self) -> dict[str, Any]:
        """Fail closed while reclaiming WAL after a committed training pass."""

        if self.connection.in_transaction:
            raise RuntimeError("Pass-boundary WAL checkpoint requires no transaction.")
        before = self._storage_bytes()
        started = time.perf_counter()
        result = self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        elapsed = time.perf_counter() - started
        if result is None or len(result) != 3 or int(result[0]) != 0:
            raise RuntimeError(f"Pass-boundary WAL checkpoint failed: {result!r}")
        after = self._storage_bytes()
        self.telemetry.add_seconds(
            "sqlite_pass_boundary_wal_checkpoint_seconds", elapsed
        )
        self.telemetry.increment("sqlite_pass_boundary_wal_checkpoints")
        return {
            "before_bytes": before,
            "after_bytes": after,
            "sqlite_result": [int(value) for value in result],
            "seconds": elapsed,
        }

    def compact_completed_piece_state(self) -> dict[str, Any]:
        """Retain learned parameters and any explicitly collected V3 diagnostics."""

        if not self.has_table("piece_lexicon"):
            raise RuntimeError("Completed S1M2 state requires piece_lexicon.")
        before = self._storage_bytes()
        dropped = tuple(
            table for table in S1M2_RECONSTRUCTIBLE_TABLES if self.has_table(table)
        )
        started = time.perf_counter()
        with self.connection:
            for table in dropped:
                self.connection.execute(f"DROP TABLE {table}")
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        self.connection.execute("VACUUM")
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        elapsed = time.perf_counter() - started
        after = self._storage_bytes()
        retained = tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        if "metadata" not in retained or "piece_lexicon" not in retained:
            raise RuntimeError("Completed S1M2 compaction lost authoritative state.")
        self.telemetry.add_seconds("sqlite_completed_state_compaction", elapsed)
        self.telemetry.increment("sqlite_completed_state_tables_dropped", len(dropped))
        objective_model = (
            self.get_metadata("piece_objective_model")
            or S1M2_REUSABLE_PIECES_V2
        )
        return {
            "layout": (
                "s1m2_reusable_piece_state_v3"
                if objective_model == S1M2_REUSABLE_PIECES_V3
                else "s1m2_reusable_piece_state_v2"
            ),
            "before_bytes": before,
            "after_bytes": after,
            "dropped_tables": list(dropped),
            "retained_tables": list(retained),
            "seconds": elapsed,
        }

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
        objective_model: str = S1M2_REUSABLE_PIECES_V2,
        collect_role_diagnostics: bool = False,
    ) -> None:
        """Start or resume one crash-safe versioned S1M2 count pass."""

        if objective_model not in {
            S1M2_REUSABLE_PIECES_V2,
            S1M2_REUSABLE_PIECES_V3,
        }:
            raise ValueError(f"unsupported reusable-piece objective: {objective_model}")
        if collect_role_diagnostics and objective_model != S1M2_REUSABLE_PIECES_V3:
            raise ValueError("role diagnostics are defined only for reusable_pieces_v3")

        with self.connection:
            stored_model = self.get_metadata("piece_objective_model")
            if stored_model is not None and stored_model != objective_model:
                raise RuntimeError(
                    "Reusable-piece objective state cannot be resumed under another model."
                )
            if (
                resume
                and stored_model is None
                and objective_model == S1M2_REUSABLE_PIECES_V3
                and self.has_table("piece_counts_next")
                and "sum_host_support_squared"
                not in {
                    str(row[1])
                    for row in self.connection.execute(
                        "PRAGMA table_info(piece_counts_next)"
                    )
                }
            ):
                raise RuntimeError(
                    "Reusable-piece objective state cannot be resumed under another model."
                )
            if objective_model == S1M2_REUSABLE_PIECES_V3:
                # V3 state always has explicit identity. Historical/new V2 state
                # retains its published metadata layout and is schema-identified.
                self._set_metadata("piece_objective_model", objective_model)
            if not resume:
                self.connection.execute("DROP TABLE IF EXISTS piece_counts_next")
                self.connection.execute(
                    "DROP TABLE IF EXISTS piece_host_support_next"
                )
                self.connection.execute(
                    "DROP TABLE IF EXISTS piece_host_role_support_next"
                )
                self.connection.execute(
                    "DROP TABLE IF EXISTS lexical_diagnostics_next"
                )
            moment_column = (
                ", sum_host_support_squared REAL NOT NULL DEFAULT 0"
                if objective_model == S1M2_REUSABLE_PIECES_V3
                else ""
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS piece_counts_next ("
                "form_key TEXT PRIMARY KEY, "
                "expected_count REAL NOT NULL, "
                "max_host_expected_usage REAL NOT NULL DEFAULT 0, "
                "reusable_count REAL NOT NULL DEFAULT 0"
                f"{moment_column}"
                ") WITHOUT ROWID"
            )
            count_columns = {
                str(row[1])
                for row in self.connection.execute(
                    "PRAGMA table_info(piece_counts_next)"
                )
            }
            has_squared = "sum_host_support_squared" in count_columns
            if has_squared != (objective_model == S1M2_REUSABLE_PIECES_V3):
                raise RuntimeError("Active piece-count schema does not match objective model.")
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS piece_host_support_next ("
                "piece_key TEXT NOT NULL, "
                "host_key TEXT NOT NULL, "
                "support REAL NOT NULL, "
                "PRIMARY KEY(piece_key, host_key)"
                ") WITHOUT ROWID"
            )
            if collect_role_diagnostics:
                if resume and not self.has_table("piece_host_role_support_next"):
                    raise RuntimeError(
                        "Resumed V3 role-diagnostic pass is missing aggregate state."
                    )
                self.connection.execute(
                    "CREATE TABLE IF NOT EXISTS piece_host_role_support_next ("
                    "piece_key TEXT NOT NULL, "
                    "host_key TEXT NOT NULL, "
                    "role TEXT NOT NULL, "
                    "support REAL NOT NULL, "
                    "PRIMARY KEY(piece_key, host_key, role)"
                    ") WITHOUT ROWID"
                )
            elif self.has_table("piece_host_role_support_next"):
                raise RuntimeError(
                    "Role-diagnostic state exists but collection is disabled."
                )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS lexical_diagnostics_next ("
                "form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL"
                ") WITHOUT ROWID"
            )
            self._set_training_checkpoint(checkpoint)

    def add_document_piece_counts(
        self,
        counts: Iterable[tuple[PieceIdentity, float]],
    ) -> None:
        if not self.connection.in_transaction:
            raise RuntimeError("Document piece counts require an open transaction.")
        row_count = 0

        def rows() -> Iterable[tuple[str, float]]:
            nonlocal row_count
            for identity, value in counts:
                if value > 0.0:
                    row_count += 1
                    yield identity.key, float(value)

        started = time.perf_counter()
        self.connection.executemany(
            "INSERT INTO piece_counts_next("
            "form_key, expected_count"
            ") VALUES (?, ?) "
            "ON CONFLICT(form_key) DO UPDATE SET "
            "expected_count = expected_count + excluded.expected_count",
            rows(),
        )
        self.telemetry.elapsed("sqlite_piece_count_upsert", started)
        self.telemetry.increment("sqlite_piece_count_upsert_calls")
        self.telemetry.increment("sqlite_piece_count_upsert_rows", row_count)

    def add_document_piece_host_support(
        self,
        support: Iterable[tuple[PieceIdentity, PhonologicalForm, float]],
        *,
        collect_roles: bool = False,
    ) -> None:
        """Aggregate support by piece form and latent phonological host type."""

        if not self.connection.in_transaction:
            raise RuntimeError("Piece host support requires an open transaction.")
        source_rows = [
            (identity, host, float(value))
            for identity, host, value in support
            if value > 0.0
        ]
        started = time.perf_counter()
        self.connection.executemany(
            "INSERT INTO piece_host_support_next(piece_key, host_key, support) "
            "VALUES (?, ?, ?) ON CONFLICT(piece_key, host_key) DO UPDATE SET "
            "support = support + excluded.support",
            (
                (identity.key, host.key, value)
                for identity, host, value in source_rows
            ),
        )
        self.telemetry.elapsed("sqlite_piece_host_support_upsert", started)
        self.telemetry.increment("sqlite_piece_host_support_upsert_calls")
        self.telemetry.increment(
            "sqlite_piece_host_support_upsert_rows", len(source_rows)
        )
        if collect_roles:
            if not self.has_table("piece_host_role_support_next"):
                raise RuntimeError("Role-diagnostic collection table is unavailable.")
            role_started = time.perf_counter()
            self.connection.executemany(
                "INSERT INTO piece_host_role_support_next("
                "piece_key, host_key, role, support) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(piece_key, host_key, role) DO UPDATE SET "
                "support = support + excluded.support",
                (
                    (identity.key, host.key, identity.role.value, value)
                    for identity, host, value in source_rows
                ),
            )
            self.telemetry.elapsed("sqlite_piece_host_role_support_upsert", role_started)
            self.telemetry.increment(
                "sqlite_piece_host_role_support_upsert_rows", len(source_rows)
            )

    def add_document_piece_host_role_support(
        self,
        support: Iterable[tuple[PieceIdentity, PhonologicalForm, float]],
    ) -> None:
        """Add optional role-bearing support already separated from pooled rows."""

        if not self.connection.in_transaction:
            raise RuntimeError("Piece host-role support requires an open transaction.")
        if not self.has_table("piece_host_role_support_next"):
            raise RuntimeError("Role-diagnostic collection table is unavailable.")
        row_count = 0

        def rows() -> Iterable[tuple[str, str, str, float]]:
            nonlocal row_count
            for identity, host, value in support:
                if value > 0.0:
                    row_count += 1
                    yield (
                        identity.key,
                        host.key,
                        identity.role.value,
                        float(value),
                    )

        started = time.perf_counter()
        self.connection.executemany(
            "INSERT INTO piece_host_role_support_next("
            "piece_key, host_key, role, support) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(piece_key, host_key, role) DO UPDATE SET "
            "support = support + excluded.support",
            rows(),
        )
        self.telemetry.elapsed("sqlite_piece_host_role_support_upsert", started)
        self.telemetry.increment(
            "sqlite_piece_host_role_support_upsert_rows", row_count
        )

    def add_document_lexical_diagnostics(
        self,
        counts: Iterable[tuple[PhonologicalForm, float]],
    ) -> None:
        if not self.connection.in_transaction:
            raise RuntimeError(
                "Document lexical diagnostics require an open transaction."
            )
        row_count = 0

        def rows() -> Iterable[tuple[str, float]]:
            nonlocal row_count
            for form, value in counts:
                if value > 0.0:
                    row_count += 1
                    yield form.key, float(value)

        started = time.perf_counter()
        self.connection.executemany(
            "INSERT INTO lexical_diagnostics_next(form_key, expected_count) "
            "VALUES (?, ?) ON CONFLICT(form_key) DO UPDATE SET "
            "expected_count = expected_count + excluded.expected_count",
            rows(),
        )
        self.telemetry.elapsed("sqlite_lexical_diagnostic_upsert", started)
        self.telemetry.increment("sqlite_lexical_diagnostic_upsert_calls")
        self.telemetry.increment("sqlite_lexical_diagnostic_upsert_rows", row_count)

    def finalize_piece_count_pass(
        self,
        *,
        checkpoint: dict[str, Any],
        objective_model: str = S1M2_REUSABLE_PIECES_V2,
    ) -> tuple[int, int, float]:
        """Freeze versioned host moments, then retire reconstructible state."""

        stored_model = self.get_metadata("piece_objective_model")
        if (
            objective_model == S1M2_REUSABLE_PIECES_V3
            and stored_model != objective_model
        ) or (
            objective_model == S1M2_REUSABLE_PIECES_V2
            and stored_model not in (None, objective_model)
        ):
            raise RuntimeError("Piece objective metadata does not match finalization.")

        row = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_count), 0.0) "
            "FROM piece_counts_next"
        ).fetchone()
        assert row is not None
        all_piece_types = int(row[0])
        if all_piece_types == 0 or float(row[1]) <= 0.0:
            raise ValueError("Piece count pass produced an empty inventory.")
        self.connection.execute("BEGIN IMMEDIATE")
        with self.connection:
            self.connection.execute(
                "UPDATE piece_counts_next SET max_host_expected_usage = "
                "COALESCE((SELECT MAX(h.support) FROM piece_host_support_next h "
                "WHERE h.piece_key = piece_counts_next.form_key), 0.0)"
            )
            if objective_model == S1M2_REUSABLE_PIECES_V3:
                self.connection.execute(
                    "UPDATE piece_counts_next SET sum_host_support_squared = "
                    "COALESCE((SELECT SUM(h.support * h.support) "
                    "FROM piece_host_support_next h "
                    "WHERE h.piece_key = piece_counts_next.form_key), 0.0)"
                )
                self._validate_cross_host_moment_source(
                    "SELECT form_key AS state_key, expected_count AS c, "
                    "sum_host_support_squared AS q FROM piece_counts_next",
                    state_name="V3 piece",
                )
                self.connection.execute(
                    "UPDATE piece_counts_next SET reusable_count = CASE "
                    "WHEN expected_count <= 0.0 THEN 0.0 "
                    "ELSE MIN(expected_count, MAX(0.0, expected_count - "
                    "sum_host_support_squared / expected_count)) END"
                )
            elif objective_model == S1M2_REUSABLE_PIECES_V2:
                self.connection.execute(
                    "UPDATE piece_counts_next SET reusable_count = "
                    "MAX(0.0, expected_count - max_host_expected_usage)"
                )
            else:
                raise ValueError(
                    f"unsupported reusable-piece objective: {objective_model}"
                )
            if self.has_table("piece_host_role_support_next"):
                role_moments = (
                    "SELECT piece_key || ':' || role AS state_key, "
                    "SUM(support) AS c, SUM(support * support) AS q "
                    "FROM piece_host_role_support_next GROUP BY piece_key, role"
                )
                self._validate_cross_host_moment_source(
                    role_moments,
                    state_name="V3 role-diagnostic",
                )
                self.connection.execute("DROP TABLE IF EXISTS piece_role_diagnostics")
                self.connection.execute(
                    "CREATE TABLE piece_role_diagnostics ("
                    "form_key TEXT NOT NULL, "
                    "role TEXT NOT NULL, "
                    "raw_expected_count REAL NOT NULL, "
                    "sum_host_support_squared REAL NOT NULL, "
                    "reusable_count REAL NOT NULL, "
                    "PRIMARY KEY(form_key, role)"
                    ") WITHOUT ROWID"
                )
                self.connection.execute(
                    "INSERT INTO piece_role_diagnostics("
                    "form_key, role, raw_expected_count, "
                    "sum_host_support_squared, reusable_count) "
                    "SELECT piece_key, role, c, q, CASE WHEN c <= 0.0 THEN 0.0 "
                    "ELSE MIN(c, MAX(0.0, c - q / c)) END FROM ("
                    "SELECT piece_key, role, SUM(support) AS c, "
                    "SUM(support * support) AS q "
                    "FROM piece_host_role_support_next GROUP BY piece_key, role)"
                )
            self.connection.execute("DROP TABLE IF EXISTS piece_inventory")
            self.connection.execute(
                "ALTER TABLE piece_counts_next RENAME TO piece_inventory"
            )
            self.connection.execute("DROP TABLE IF EXISTS piece_lexicon")
            self.connection.execute(
                "ALTER TABLE piece_inventory RENAME COLUMN expected_count "
                "TO raw_expected_count"
            )
            self.connection.execute(
                "ALTER TABLE piece_inventory RENAME TO piece_lexicon"
            )
            active = self.connection.execute(
                "SELECT COALESCE(SUM(CASE WHEN reusable_count > 0.0 THEN 1 ELSE 0 END), 0), "
                "COALESCE(SUM(reusable_count), 0.0) "
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
            retired = 0
            for table in S1M2_PASS_DIAGNOSTIC_TABLES:
                if self.has_table(table):
                    self.connection.execute(f"DROP TABLE {table}")
                    retired += 1
            self.connection.execute("DROP TABLE piece_host_support_next")
            if self.has_table("piece_host_role_support_next"):
                self.connection.execute("DROP TABLE piece_host_role_support_next")
            self._set_training_checkpoint(checkpoint)
        self.telemetry.increment(
            "sqlite_pass_diagnostic_tables_retired",
            retired,
        )
        return all_piece_types, int(active[0]), float(active[1])

    def _validate_cross_host_moment_source(
        self,
        source_sql: str,
        *,
        state_name: str,
    ) -> None:
        """Fail closed on invalid C/Q rows without materializing the inventory.

        SQLite handles the ordinary finite in-range rows. Only an out-of-range
        result near zero reaches the authoritative Python helper, which admits
        the same eight-ULP roundoff band used by diagnostics and tests.
        """

        invalid = self.connection.execute(
            "SELECT state_key, c, q FROM (" + source_sql + ") WHERE CASE "
            "WHEN c IS NULL OR q IS NULL THEN 1 "
            "WHEN typeof(c) NOT IN ('integer', 'real') "
            "OR typeof(q) NOT IN ('integer', 'real') THEN 1 "
            "WHEN ABS(c) > ? OR ABS(q) > ? THEN 1 "
            "WHEN c < 0.0 OR q < 0.0 THEN 1 "
            "WHEN c = 0.0 THEN q != 0.0 "
            "WHEN c - q / c BETWEEN 0.0 AND c THEN 0 "
            "ELSE sktlm_cross_host_moments_valid(c, q) = 0 END "
            "LIMIT 1",
            (float.fromhex("0x1.fffffffffffffp+1023"),) * 2,
        ).fetchone()
        if invalid is not None:
            raise ValueError(
                f"Invalid {state_name} moments for {invalid[0]!r}: "
                f"C={invalid[1]!r}, Q={invalid[2]!r}."
            )

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
        objective_model: str = S1M2_REUSABLE_PIECES_V2,
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
            objective_model=objective_model,
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
                "store_lookups": scorer.store_lookups,
                "cache_size": scorer.cache_size,
                "cache_entries": len(scorer._cache),
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
                "DROP TABLE IF EXISTS inspection_piece_host_support"
            )
            self.connection.execute(
                "CREATE TABLE inspection_piece_counts ("
                "form_key TEXT PRIMARY KEY, "
                "expected_count REAL NOT NULL, "
                "host_type_support INTEGER NOT NULL DEFAULT 0"
                ") WITHOUT ROWID"
            )
            self.connection.execute(
                "CREATE TABLE inspection_piece_host_support ("
                "piece_key TEXT NOT NULL, host_key TEXT NOT NULL, "
                "support REAL NOT NULL, PRIMARY KEY(piece_key, host_key)"
                ") WITHOUT ROWID"
            )

    def add_inspection_piece_counts(
        self,
        counts: Iterable[tuple[PieceIdentity, float]],
    ) -> None:
        rows = [
            (identity.key, float(value))
            for identity, value in counts
            if value > 0.0
        ]
        with self.connection:
            self.connection.executemany(
                "INSERT INTO inspection_piece_counts("
                "form_key, expected_count"
                ") VALUES (?, ?) ON CONFLICT(form_key) DO UPDATE SET "
                "expected_count = expected_count + excluded.expected_count",
                rows,
            )

    def add_inspection_piece_host_support(
        self,
        support: Iterable[tuple[PieceIdentity, PhonologicalForm, float]],
    ) -> None:
        rows = [
            (identity.key, host.key, float(value))
            for identity, host, value in support
            if value > 0.0
        ]
        with self.connection:
            self.connection.executemany(
                "INSERT INTO inspection_piece_host_support("
                "piece_key, host_key, support) VALUES (?, ?, ?) "
                "ON CONFLICT(piece_key, host_key) DO UPDATE SET "
                "support = support + excluded.support",
                rows,
            )

    def finalize_piece_inspection_support(self, *, threshold: float) -> None:
        """Materialize distinct qualifying host-type counts after streaming."""

        if threshold <= 0.0:
            raise ValueError("threshold must be > 0")

        with self.connection:
            self.connection.execute(
                "UPDATE inspection_piece_counts SET host_type_support = ("
                "SELECT COUNT(*) FROM inspection_piece_host_support h "
                "WHERE h.piece_key = inspection_piece_counts.form_key "
                "AND h.support >= ?)",
                (threshold,),
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

    def merge_inspection_shard(
        self,
        path: Path,
        *,
        row_counts: dict[str, int],
    ) -> None:
        """Merge one ordered worker aggregate without Python row materialization."""

        if self.connection.in_transaction:
            raise RuntimeError("Cannot attach an inspection shard in a transaction.")
        alias = "inspection_shard"
        self.connection.execute(f"ATTACH DATABASE ? AS {alias}", (str(path),))
        started = time.perf_counter()
        try:
            with self.connection:
                self.connection.execute(
                    f"INSERT INTO inspection_counts(form_key, expected_count) "
                    f"SELECT form_key, expected_count FROM {alias}.count_rows "
                    "WHERE expected_count > 0.0 ORDER BY row_number "
                    "ON CONFLICT(form_key) DO UPDATE SET expected_count = "
                    "expected_count + excluded.expected_count"
                )
                if self.has_table("inspection_piece_counts"):
                    self.connection.execute(
                        "INSERT INTO inspection_piece_counts("
                        "form_key, expected_count) "
                        f"SELECT form_key, expected_count "
                        f"FROM {alias}.piece_rows WHERE expected_count > 0.0 "
                        "ORDER BY row_number "
                        "ON CONFLICT(form_key) DO UPDATE SET expected_count = "
                        "expected_count + excluded.expected_count"
                    )
                    self.connection.execute(
                        "INSERT INTO inspection_piece_host_support("
                        "piece_key, host_key, support) "
                        f"SELECT piece_key, host_key, support FROM "
                        f"{alias}.piece_host_rows WHERE support > 0.0 "
                        "ORDER BY row_number ON CONFLICT(piece_key, host_key) "
                        "DO UPDATE SET support = support + excluded.support"
                    )
                self.connection.execute(
                    "INSERT INTO surface_usage(form_key, surface, expected_mass) "
                    f"SELECT form_key, surface, expected_mass "
                    f"FROM {alias}.surface_rows WHERE 1 ORDER BY row_number "
                    "ON CONFLICT(form_key, surface) DO UPDATE SET "
                    "expected_mass = expected_mass + excluded.expected_mass"
                )
                self.connection.execute(
                    "INSERT INTO context_usage(form_key, context, expected_mass) "
                    f"SELECT form_key, context, expected_mass "
                    f"FROM {alias}.context_rows WHERE 1 ORDER BY row_number "
                    "ON CONFLICT(form_key, context) DO UPDATE SET "
                    "expected_mass = expected_mass + excluded.expected_mass"
                )
        finally:
            self.connection.execute(f"DETACH DATABASE {alias}")
        self.telemetry.elapsed("sqlite_inspection_shard_merge", started)
        self.telemetry.increment("sqlite_inspection_shard_merge_calls")
        self.telemetry.increment(
            "sqlite_inspection_shard_merge_rows",
            sum(int(value) for value in row_counts.values()),
        )

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
            "SELECT COALESCE(SUM(reusable_count), 0.0) FROM piece_lexicon"
        ).fetchone()
        assert active_row is not None
        denominator = float(active_row[0]) + alpha
        base = GeometricPhonemeBaseMeasure(base_stop_probability)
        query = (
            "SELECT i.form_key, i.expected_count, i.host_type_support, "
            "a.raw_expected_count, a.max_host_expected_usage, a.reusable_count "
            "FROM inspection_piece_counts i "
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
                    "raw_expected_count_inspection",
                    "host_type_support",
                    "active",
                    "raw_expected_count_training",
                    "max_host_expected_usage_training",
                    "reusable_count_training",
                    "model_probability",
                    "model_log_score",
                )
            )
            for key, expected, support, active_raw, max_host, reusable in self.connection.execute(query):
                piece = PhonologicalForm.from_key(str(key))
                active_count = 0.0 if reusable is None else float(reusable)
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
                        int(active_count > 0.0),
                        active_raw,
                        max_host,
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
            "SELECT COALESCE(SUM(CASE WHEN reusable_count > 0.0 THEN 1 ELSE 0 END), 0), "
            "COALESCE(SUM(reusable_count), 0.0) FROM piece_lexicon"
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
            "SELECT host_type_support, COUNT(*) FROM inspection_piece_counts "
            "GROUP BY host_type_support"
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
            "SELECT form_key, reusable_count FROM piece_lexicon "
            "WHERE reusable_count > 0.0"
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
            "piece_types_by_host_type_support": reuse_distribution,
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

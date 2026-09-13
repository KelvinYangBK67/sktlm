from __future__ import annotations

import inspect
from pathlib import Path

from sktlm.latent import training
from sktlm.latent.store import LexiconStore


PIECE_ROWS = (
    ("V_A", 2.0, 0),
    ("C_K.C_T", 3.0, 1),
    ("C_K.C_P", 4.0, 2),
    ("C_M.C_N", 0.0, 10),
    ("C_S.C_H", 5.0, 3),
)


def _checkpoint() -> dict[str, object]:
    return {
        "completed_passes": 1,
        "active_pass": None,
        "next_document_index": 0,
        "active_metrics": None,
        "history": [{}],
    }


def _populate_pass(store: LexiconStore, checkpoint: dict[str, object]) -> None:
    store.begin_piece_count_pass(resume=False, checkpoint=checkpoint)
    with store.connection:
        store.connection.executemany(
            "INSERT INTO piece_counts_next("
            "form_key, expected_count, occurrence_support) VALUES (?, ?, ?)",
            PIECE_ROWS,
        )
        store.connection.executemany(
            "INSERT INTO lexical_diagnostics_next(form_key, expected_count) "
            "VALUES (?, ?)",
            ((key, count) for key, count, _support in PIECE_ROWS if count > 0.0),
        )


def test_in_place_piece_finalize_matches_reference_and_avoids_active_copy(
    tmp_path: Path,
) -> None:
    store = LexiconStore(tmp_path / "learner.sqlite")
    checkpoint = _checkpoint()
    statements: list[str] = []
    try:
        _populate_pass(store, checkpoint)
        store.connection.set_trace_callback(statements.append)

        result = store.finalize_piece_count_pass(
            min_reuse_occurrences=2,
            checkpoint=checkpoint,  # type: ignore[arg-type]
        )

        expected_rows = tuple(
            row
            for row in PIECE_ROWS
            if row[1] > 0.0 and ("." not in row[0] or row[2] >= 2)
        )
        actual_rows = tuple(
            store.connection.execute(
                "SELECT form_key, expected_count, occurrence_support "
                "FROM piece_lexicon ORDER BY form_key"
            )
        )
        expected_rows = tuple(sorted(expected_rows))
        assert actual_rows == expected_rows
        assert result == (
            len(PIECE_ROWS),
            len(expected_rows),
            sum(row[1] for row in expected_rows),
        )
        assert checkpoint["history"] == [
            {
                "piece_types": len(PIECE_ROWS),
                "active_piece_types": len(expected_rows),
                "active_piece_count_total": sum(row[1] for row in expected_rows),
            }
        ]
        assert store.load_training_checkpoint() == checkpoint
        assert not store.has_table("piece_inventory")
        assert not store.has_table("lexical_diagnostics")
        assert not store.has_table("lexical_diagnostics_next")
        schema = store.connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'piece_lexicon'"
        ).fetchone()
        assert schema is not None and "WITHOUT ROWID" in str(schema[0])

        normalized = tuple(statement.upper() for statement in statements)
        assert any("DELETE FROM PIECE_INVENTORY" in item for item in normalized)
        assert any(
            "ALTER TABLE PIECE_INVENTORY RENAME TO PIECE_LEXICON" in item
            for item in normalized
        )
        assert not any("CREATE TABLE PIECE_LEXICON" in item for item in normalized)
        assert not any("INSERT INTO PIECE_LEXICON" in item for item in normalized)
    finally:
        store.close()


def test_pass_boundary_wal_truncate_preserves_rows_checkpoint_and_connection(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learner.sqlite"
    store = LexiconStore(path)
    checkpoint = _checkpoint()
    try:
        store.begin_piece_count_pass(resume=False, checkpoint=checkpoint)
        with store.connection:
            store.connection.executemany(
                "INSERT INTO piece_counts_next("
                "form_key, expected_count, occurrence_support) VALUES (?, ?, ?)",
                ((f"V_A_{index:05d}", 1.0, 1) for index in range(500)),
            )
        store.finalize_piece_count_pass(
            min_reuse_occurrences=2,
            checkpoint=checkpoint,  # type: ignore[arg-type]
        )
        rows_before = tuple(store.connection.execute("SELECT * FROM piece_lexicon"))
        checkpoint_before = store.load_training_checkpoint()

        result = store.checkpoint_and_truncate_wal_at_pass_boundary()

        assert result["sqlite_result"][0] == 0
        assert result["after_bytes"]["wal"] <= result["before_bytes"]["wal"]
        assert tuple(store.connection.execute("SELECT * FROM piece_lexicon")) == rows_before
        assert store.load_training_checkpoint() == checkpoint_before
        store.set_metadata("post_checkpoint_probe", "ok")
        assert store.get_metadata("post_checkpoint_probe") == "ok"
        assert (
            store.telemetry.timings["sqlite_pass_boundary_wal_checkpoint_seconds"]
            >= 0.0
        )
        assert store.telemetry.counters["sqlite_pass_boundary_wal_checkpoints"] == 1
    finally:
        store.close()

    reopened = LexiconStore(path)
    try:
        assert reopened.load_training_checkpoint() == checkpoint
        assert tuple(reopened.connection.execute("SELECT * FROM piece_lexicon"))
    finally:
        reopened.close()


def test_wal_checkpoint_is_pass_boundary_only_and_document_commit_is_unchanged() -> None:
    pass_source = inspect.getsource(training._training_pass)
    commit_source = inspect.getsource(LexiconStore.commit_document)
    assert pass_source.count("checkpoint_and_truncate_wal_at_pass_boundary") == 1
    assert pass_source.index("finalize_piece_count_pass") < pass_source.index(
        "checkpoint_and_truncate_wal_at_pass_boundary"
    )
    assert "checkpoint_and_truncate_wal_at_pass_boundary" not in commit_source

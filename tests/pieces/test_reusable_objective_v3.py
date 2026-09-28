from __future__ import annotations

import itertools
import math
import sqlite3
from dataclasses import replace

import pytest

from sktlm.latent.phonology import host_blob_to_key, pack_host_key, parse_iast_form
from sktlm.latent.store import (
    TRANSIENT_SUPPORT_BLOB_V1,
    TRANSIENT_SUPPORT_SCHEMA_KEY,
    TRANSIENT_SUPPORT_TEXT_V1,
    LexiconStore,
)
from sktlm.latent.training import TrainingConfig, _config_signature
from sktlm.pieces import (
    PieceIdentity,
    PieceRole,
    ProductionPieceConfig,
    S1M2_REUSABLE_PIECES_V2,
    S1M2_REUSABLE_PIECES_V3,
    cross_host_reusable_count,
    cross_host_support_moments,
    fit_production_piece_model,
    select_cross_host_reusable_inventory,
)


@pytest.mark.parametrize(
    ("support", "expected"),
    [
        ([1000.0], 0.0),
        ([1000.0, 1.0], 1.998001998001996),
        ([10.0, 10.0], 10.0),
        ([10.0, 10.0, 10.0], 20.0),
        ([100.0, 8.0, 7.0, 6.0], 37.123966942148755),
        ([], 0.0),
    ],
)
def test_cross_host_examples(support: list[float], expected: float) -> None:
    hosts = [parse_iast_form(text) for text in ("deva", "devam", "devina", "devau")]
    raw, squared, _maximum, reusable = cross_host_support_moments(
        zip(hosts, support)
    )
    assert reusable == pytest.approx(expected)
    assert reusable == pytest.approx(cross_host_reusable_count(raw, squared))


def test_cross_host_invariants_and_host_aggregation_before_square() -> None:
    a, b, c = (parse_iast_form(text) for text in ("deva", "devam", "devina"))
    raw, squared, maximum, reusable = cross_host_support_moments(
        [(a, 2.0), (a, 3.0), (b, 1.0)]
    )
    assert (raw, squared, maximum, reusable) == pytest.approx((6, 26, 5, 10 / 6))
    assert squared != pytest.approx(2**2 + 3**2 + 1**2)

    values = [100.0, 8.0, 7.0, 6.0]
    expected = cross_host_support_moments(zip((a, b, c, parse_iast_form("devau")), values))[3]
    for permutation in itertools.permutations(values):
        hosts = tuple(
            parse_iast_form(text)
            for text in ("deva", "devam", "devina", "devau")
        )
        assert cross_host_support_moments(zip(hosts, permutation))[3] == pytest.approx(
            expected
        )
    scaled = cross_host_support_moments([(a, 20), (b, 6), (c, 4)])[3]
    base = cross_host_support_moments([(a, 10), (b, 3), (c, 2)])[3]
    assert scaled == pytest.approx(2 * base)
    assert cross_host_support_moments([(a, 10), (b, 3), (c, 2), (a, 0)])[3] == pytest.approx(base)
    assert cross_host_support_moments([(a, 10), (b, 3), (c, 2), (b, 1)])[3] >= base

    assert cross_host_reusable_count(1.0, 1.0 + 2e-16) == 0.0
    assert cross_host_reusable_count(1.0, 0.0) == 1.0
    with pytest.raises(ValueError, match="Q must be zero"):
        cross_host_reusable_count(0.0, 1.0)
    with pytest.raises(ValueError, match="valid cross-host moments"):
        cross_host_reusable_count(1.0, 2.0)


def test_v3_host_identity_discards_derivation_path_before_square() -> None:
    host = parse_iast_form("devasya")
    path_support = (
        ("direct-boundary-path", host, 2.0),
        ("sandhi-inversion-path", host, 3.0),
    )
    raw, squared, maximum, reusable = cross_host_support_moments(
        (wordform, support) for _path_id, wordform, support in path_support
    )
    assert (raw, squared, maximum, reusable) == pytest.approx((5, 25, 5, 0))


def test_v3_distinct_phonological_wordform_hosts_remain_distinct() -> None:
    raw, squared, maximum, reusable = cross_host_support_moments(
        [
            (parse_iast_form("deva"), 2.0),
            (parse_iast_form("devam"), 3.0),
        ]
    )
    assert (raw, squared, maximum, reusable) == pytest.approx((5, 13, 3, 2.4))


def test_reference_v3_inventory_is_form_keyed_and_wordform_hosted() -> None:
    piece = parse_iast_form("dev")
    deva, devam, devina = (
        parse_iast_form(text) for text in ("deva", "devam", "devina")
    )
    raw, squared, maximum, reusable = select_cross_host_reusable_inventory(
        {
            (piece, deva): 2.0,
            (piece, devam): 3.0,
            (piece, devina): 4.0,
        }
    )
    assert (raw[piece], squared[piece], maximum[piece], reusable[piece]) == pytest.approx(
        (9, 29, 4, 52 / 9)
    )
    assert {PieceIdentity(piece, role).key for role in PieceRole} == {piece.key}


def test_production_reference_selects_explicit_v2_or_v3_semantics() -> None:
    v2_config = ProductionPieceConfig()
    v3_config = ProductionPieceConfig(objective_model=S1M2_REUSABLE_PIECES_V3)
    assert v2_config.payload()["objective_model"] == S1M2_REUSABLE_PIECES_V2
    assert v2_config.payload()["learned_count_semantics"].startswith("R(q)=C(q)-max_h")
    assert v3_config.payload()["objective_model"] == S1M2_REUSABLE_PIECES_V3
    assert v3_config.payload()["learned_count_semantics"] == (
        "R_cross(q)=0 if C(q)=0 else "
        "C(q)-sum_h S(q,h)^2/C(q); q=phonological_form"
    )

    occurrences = tuple(
        parse_iast_form(text)
        for text in ("gacchati", "gacchati", "bhavati", "vadati")
    )
    piece = parse_iast_form("ti")
    v2 = fit_production_piece_model(occurrences, passes=1, config=v2_config)
    v3 = fit_production_piece_model(occurrences, passes=1, config=v3_config)
    v2_pass, v3_pass = v2.history[0], v3.history[0]
    assert v2.objective_model == S1M2_REUSABLE_PIECES_V2
    assert v3.objective_model == S1M2_REUSABLE_PIECES_V3
    assert v2_pass.sum_host_support_squared is None
    assert v3_pass.sum_host_support_squared is not None
    assert v2_pass.reusable_counts[piece] == pytest.approx(
        v2_pass.raw_expected_counts[piece] - v2_pass.max_host_expected_usage[piece]
    )
    assert v3_pass.reusable_counts[piece] == pytest.approx(
        cross_host_reusable_count(
            v3_pass.raw_expected_counts[piece],
            v3_pass.sum_host_support_squared[piece],
        )
    )
    assert v3_pass.reusable_counts[piece] != pytest.approx(
        v3_pass.raw_expected_counts[piece] - v3_pass.max_host_expected_usage[piece]
    )

    with pytest.raises(ValueError, match="unsupported reusable-piece objective"):
        ProductionPieceConfig(objective_model="reusable_pieces_v4")


def test_v3_roles_pool_for_learned_identity_and_remain_diagnostic(tmp_path) -> None:
    store = LexiconStore(tmp_path / "v3.sqlite")
    checkpoint = {"history": [{}]}
    piece = parse_iast_form("ti")
    a, b = parse_iast_form("gacchati"), parse_iast_form("bhavati")
    try:
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
            collect_role_diagnostics=True,
        )
        store.begin_document_counts()
        store.add_document_piece_counts(
            [(PieceIdentity(piece, PieceRole.RIGHT), 16), (PieceIdentity(piece, PieceRole.LEFT), 4)]
        )
        store.add_document_piece_host_support(
            [
                (PieceIdentity(piece, PieceRole.RIGHT), a, 6),
                (PieceIdentity(piece, PieceRole.LEFT), a, 4),
                (PieceIdentity(piece, PieceRole.RIGHT), b, 10),
            ],
            collect_roles=True,
        )
        store.commit_document(checkpoint)
        store.finalize_piece_count_pass(
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        assert store.connection.execute(
            "SELECT raw_expected_count, sum_host_support_squared, "
            "max_host_expected_usage, reusable_count FROM piece_lexicon"
        ).fetchone() == pytest.approx((20, 200, 10, 10))
        role_rows = store.connection.execute(
            "SELECT role, raw_expected_count, sum_host_support_squared, reusable_count "
            "FROM piece_role_diagnostics ORDER BY role"
        ).fetchall()
        assert role_rows == [
            ("LEFT", 4.0, 16.0, 0.0),
            ("RIGHT", 16.0, 136.0, 7.5),
        ]
        assert sum(row[1] for row in role_rows) == pytest.approx(20)

        scorer = store.piece_scorer(
            alpha=0.1,
            complexity_weight=0.5,
            complexity_kappa=1,
            complexity_beta=0.25,
            complexity_tau=1,
            base_stop_probability=0.5,
            cache_size=8,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        assert scorer.total_count == pytest.approx(10)
        assert scorer._lookup(piece.key) == pytest.approx(10)
        assert scorer.score_piece(piece, PieceRole.LEFT) == scorer.score_piece(
            piece, PieceRole.RIGHT
        )
        score_before = scorer.score(piece)
        with store.connection:
            store.connection.execute(
                "UPDATE piece_lexicon SET sum_host_support_squared=999, "
                "max_host_expected_usage=999"
            )
        scorer_after_diagnostic_change = store.piece_scorer(
            alpha=0.1,
            complexity_weight=0.5,
            complexity_kappa=1,
            complexity_beta=0.25,
            complexity_tau=1,
            base_stop_probability=0.5,
            cache_size=8,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        assert scorer_after_diagnostic_change.score(piece) == pytest.approx(score_before)
        with pytest.raises(RuntimeError, match="V3 piece state"):
            store.piece_scorer(
                alpha=0.1,
                complexity_weight=0.5,
                complexity_kappa=1,
                complexity_beta=0.25,
                complexity_tau=1,
                base_stop_probability=0.5,
                cache_size=8,
                objective_model=S1M2_REUSABLE_PIECES_V2,
            )
    finally:
        store.close()


def test_v3_sqlite_finalization_accepts_only_roundoff_clamping(tmp_path) -> None:
    store = LexiconStore(tmp_path / "roundoff.sqlite")
    checkpoint = {"history": [{}]}
    piece = parse_iast_form("ti")
    host = parse_iast_form("gacchati")
    try:
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        with store.connection:
            store.connection.execute(
                "INSERT INTO piece_counts_next(form_key, expected_count) VALUES (?, ?)",
                (piece.key, 1.0),
            )
            store.connection.execute(
                "INSERT INTO piece_host_support_next(piece_key, host_key, support) "
                "VALUES (?, ?, ?)",
                (piece.key, host.key, math.nextafter(1.0, math.inf)),
            )
        store.finalize_piece_count_pass(
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        assert store.connection.execute(
            "SELECT raw_expected_count, sum_host_support_squared, reusable_count "
            "FROM piece_lexicon"
        ).fetchone() == pytest.approx((1.0, 1.0000000000000004, 0.0))
    finally:
        store.close()


@pytest.mark.parametrize(
    ("raw_count", "host_support"),
    [
        (0.0, 1.0),
        (-1.0, 0.0),
        (1.0, math.sqrt(2.0)),
        (math.inf, 0.0),
    ],
)
def test_v3_sqlite_finalization_rejects_invalid_moments(
    tmp_path, raw_count: float, host_support: float
) -> None:
    store = LexiconStore(tmp_path / "invalid.sqlite")
    checkpoint = {"history": [{}]}
    piece = parse_iast_form("ti")
    host = parse_iast_form("gacchati")
    filler = parse_iast_form("a")
    try:
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        with store.connection:
            store.connection.executemany(
                "INSERT INTO piece_counts_next(form_key, expected_count) VALUES (?, ?)",
                [(piece.key, raw_count), (filler.key, 2.0)],
            )
            if host_support:
                store.connection.execute(
                    "INSERT INTO piece_host_support_next(piece_key, host_key, support) "
                    "VALUES (?, ?, ?)",
                    (piece.key, host.key, host_support),
                )
        with pytest.raises(ValueError, match="Invalid V3 piece moments"):
            store.finalize_piece_count_pass(
                checkpoint=checkpoint,
                objective_model=S1M2_REUSABLE_PIECES_V3,
            )
    finally:
        store.close()


@pytest.mark.parametrize(
    ("raw_count", "squared_sum"),
    [(-1.0, 0.0), (1.0, -1.0), (0.0, 1.0), (1.0, 2.0), (1.0, math.inf)],
)
def test_sqlite_moment_validator_rejects_corrupt_direct_state(
    tmp_path, raw_count: float, squared_sum: float
) -> None:
    store = LexiconStore(tmp_path / "validator.sqlite")
    try:
        store.connection.execute(
            "CREATE TEMP TABLE moment_fixture(state_key TEXT, c REAL, q REAL)"
        )
        store.connection.execute(
            "INSERT INTO moment_fixture VALUES ('piece', ?, ?)",
            (raw_count, squared_sum),
        )
        with pytest.raises(ValueError, match="Invalid fixture moments"):
            store._validate_cross_host_moment_source(
                "SELECT state_key, c, q FROM moment_fixture",
                state_name="fixture",
            )
    finally:
        store.close()


def test_v2_v3_identity_and_default_role_collection_are_isolated(tmp_path) -> None:
    v2 = TrainingConfig(model=S1M2_REUSABLE_PIECES_V2)
    v3 = TrainingConfig(model=S1M2_REUSABLE_PIECES_V3)
    assert v2.payload()["model"] == S1M2_REUSABLE_PIECES_V2
    assert "piece_role_diagnostics" not in v2.payload()
    assert v3.payload()["model"] == S1M2_REUSABLE_PIECES_V3
    assert v3.payload()["piece_role_diagnostics"] is False
    assert _config_signature(v2) != _config_signature(v3)

    qualified = TrainingConfig(
        model=S1M2_REUSABLE_PIECES_V3,
        sandhi_transformation_penalty=1.0,
        piece_boundary_probability=0.4,
    )
    assert _config_signature(qualified) != _config_signature(
        replace(qualified, sandhi_transformation_penalty=0.0)
    )
    assert _config_signature(qualified) != _config_signature(
        replace(qualified, piece_boundary_probability=0.5)
    )

    store = LexiconStore(tmp_path / "identity.sqlite")
    try:
        checkpoint = {"history": [{}]}
        store.begin_piece_count_pass(resume=False, checkpoint=checkpoint)
        assert not store.has_table("piece_host_role_support_next")
        with pytest.raises(RuntimeError, match="another model"):
            store.begin_piece_count_pass(
                resume=True,
                checkpoint=checkpoint,
                objective_model=S1M2_REUSABLE_PIECES_V3,
            )
        piece = parse_iast_form("ti")
        host = parse_iast_form("gacchati")
        store.begin_document_counts()
        store.add_document_piece_counts(
            [(PieceIdentity(piece, PieceRole.RIGHT), 1.0)]
        )
        store.add_document_piece_host_support(
            [(PieceIdentity(piece, PieceRole.RIGHT), host, 1.0)]
        )
        store.commit_document(checkpoint)
        store.finalize_piece_count_pass(checkpoint=checkpoint)
        with pytest.raises(RuntimeError, match="V2 piece state"):
            store.piece_scorer(
                alpha=0.1,
                complexity_weight=0.5,
                complexity_kappa=1,
                complexity_beta=0.25,
                complexity_tau=1,
                base_stop_probability=0.5,
                cache_size=8,
                objective_model=S1M2_REUSABLE_PIECES_V3,
            )
    finally:
        store.close()


def test_default_v3_host_support_consumes_source_once_and_streams_rows(tmp_path) -> None:
    store = LexiconStore(tmp_path / "streaming.sqlite")
    checkpoint = {"history": [{}]}
    piece = PieceIdentity(parse_iast_form("ti"), PieceRole.RIGHT)
    hosts = (parse_iast_form("gacchati"), parse_iast_form("bhavati"))
    yielded: list[str] = []

    def rows():
        for index, host in enumerate(hosts, start=1):
            yielded.append(host.key)
            yield piece, host, float(index)

    try:
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        store.begin_document_counts()
        store.add_document_piece_host_support(rows(), collect_roles=False)
        observed = store.connection.execute(
            "SELECT host_key, support FROM piece_host_support_next "
            "ORDER BY host_key"
        ).fetchall()
        observed = [(host_blob_to_key(row[0]), row[1]) for row in observed]
        store.rollback_document()
    finally:
        store.close()

    assert yielded == [host.key for host in hosts]
    assert observed == sorted(
        [(hosts[0].key, 1.0), (hosts[1].key, 2.0)]
    )


def test_raw_key_store_apis_match_object_apis_exactly(tmp_path) -> None:
    piece = PieceIdentity(parse_iast_form("ti"), PieceRole.RIGHT)
    host = parse_iast_form("gacchati")

    def populate(store: LexiconStore, *, raw: bool) -> tuple[tuple[object, ...], ...]:
        checkpoint = {"history": [{}]}
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
            collect_role_diagnostics=True,
        )
        store.begin_document_counts()
        if raw:
            store.add_document_lexical_diagnostic_keys([(host.key, 1.25)])
            store.add_document_piece_count_keys([(piece.key, 2.5)])
            store.add_document_piece_host_support_keys(
                [(piece.key, host.key, 2.5)]
            )
            store.add_document_piece_host_role_support_keys(
                [(piece.key, piece.role.value, host.key, 2.5)]
            )
        else:
            store.add_document_lexical_diagnostics([(host, 1.25)])
            store.add_document_piece_counts([(piece, 2.5)])
            store.add_document_piece_host_support([(piece, host, 2.5)])
            store.add_document_piece_host_role_support([(piece, host, 2.5)])
        rows: list[tuple[object, ...]] = []
        for table in (
            "lexical_diagnostics_next",
            "piece_counts_next",
            "piece_host_support_next",
            "piece_host_role_support_next",
        ):
            rows.extend(
                (table, *row)
                for row in store.connection.execute(
                    f"SELECT * FROM {table} ORDER BY 1, 2"
                )
            )
        store.rollback_document()
        return tuple(rows)

    object_store = LexiconStore(tmp_path / "objects.sqlite")
    raw_store = LexiconStore(tmp_path / "keys.sqlite")
    try:
        assert populate(raw_store, raw=True) == populate(object_store, raw=False)
    finally:
        raw_store.close()
        object_store.close()


def test_transient_blob_schema_rolls_back_commits_reopens_and_resumes(tmp_path) -> None:
    path = tmp_path / "resume.sqlite"
    checkpoint = {"history": [{}], "next_document_index": 0}
    piece = "C_T.V_I"
    host = "C_G.V_A.C_C.C_CH.V_A.C_T.V_I"
    store = LexiconStore(path)
    try:
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        schema = {
            row[1]: row[2]
            for row in store.connection.execute(
                "PRAGMA table_info(piece_host_support_next)"
            )
        }
        assert schema["host_key"] == "BLOB"
        assert store.get_metadata(TRANSIENT_SUPPORT_SCHEMA_KEY) == (
            TRANSIENT_SUPPORT_BLOB_V1
        )

        store.begin_document_counts()
        store.add_document_piece_host_support_keys([(piece, host, 1.25)])
        store.rollback_document()
        assert store.connection.execute(
            "SELECT COUNT(*) FROM piece_host_support_next"
        ).fetchone()[0] == 0

        committed = {**checkpoint, "next_document_index": 1}
        store.begin_document_counts()
        store.add_document_piece_host_support_keys([(piece, host, 2.5)])
        store.commit_document(committed)
    finally:
        store.close()

    reopened = LexiconStore(path)
    try:
        reopened.begin_piece_count_pass(
            resume=True,
            checkpoint=committed,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        row = reopened.connection.execute(
            "SELECT host_key, support, typeof(host_key) "
            "FROM piece_host_support_next"
        ).fetchone()
        assert row == (pack_host_key(host), 2.5, "blob")
        assert reopened.load_training_checkpoint() == committed
        assert reopened.runtime_payload()["sqlite_journal_mode"] == "wal"
        assert reopened.runtime_payload()["sqlite_synchronous"] == "normal"
    finally:
        reopened.close()


def test_transient_schema_metadata_mismatch_fails_closed(tmp_path) -> None:
    path = tmp_path / "mismatch.sqlite"
    checkpoint = {"history": [{}]}
    store = LexiconStore(path)
    try:
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        store.set_metadata(TRANSIENT_SUPPORT_SCHEMA_KEY, TRANSIENT_SUPPORT_TEXT_V1)
    finally:
        store.close()

    reopened = LexiconStore(path)
    try:
        with pytest.raises(RuntimeError, match="metadata conflicts"):
            reopened.begin_piece_count_pass(
                resume=True,
                checkpoint=checkpoint,
                objective_model=S1M2_REUSABLE_PIECES_V3,
            )
    finally:
        reopened.close()


def test_legacy_text_transient_schema_resumes_explicitly_and_matches_blob_final_state(
    tmp_path,
) -> None:
    piece = "C_T.V_I"
    hosts = ("C_G.V_A.C_C.C_CH.V_A.C_T.V_I", "C_BH.V_A.C_V.V_A.C_T.V_I")
    checkpoint = {"history": [{}]}

    def prepare(path, *, legacy_text: bool) -> LexiconStore:
        store = LexiconStore(path)
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        if legacy_text:
            with store.connection:
                store.connection.execute("DROP TABLE piece_host_support_next")
                store.connection.execute(
                    "CREATE TABLE piece_host_support_next ("
                    "piece_key TEXT NOT NULL, host_key TEXT NOT NULL, "
                    "support REAL NOT NULL, PRIMARY KEY(piece_key, host_key)"
                    ") WITHOUT ROWID"
                )
                store.connection.execute(
                    "DELETE FROM metadata WHERE key = ?",
                    (TRANSIENT_SUPPORT_SCHEMA_KEY,),
                )
            store.begin_piece_count_pass(
                resume=True,
                checkpoint=checkpoint,
                objective_model=S1M2_REUSABLE_PIECES_V3,
            )
            assert store.get_metadata(TRANSIENT_SUPPORT_SCHEMA_KEY) == (
                TRANSIENT_SUPPORT_TEXT_V1
            )
        return store

    blob = prepare(tmp_path / "blob.sqlite", legacy_text=False)
    text = prepare(tmp_path / "text.sqlite", legacy_text=True)
    try:
        for store in (blob, text):
            store.begin_document_counts()
            store.add_document_piece_count_keys([(piece, 10.0)])
            store.add_document_piece_host_support_keys(
                [
                    (piece, pack_host_key(hosts[0]), 4.0),
                    (piece, pack_host_key(hosts[1]), 6.0),
                ]
            )
            store.commit_document(checkpoint)
            store.finalize_piece_count_pass(
                checkpoint=checkpoint,
                objective_model=S1M2_REUSABLE_PIECES_V3,
            )
        assert tuple(blob.connection.execute("SELECT * FROM piece_lexicon")) == tuple(
            text.connection.execute("SELECT * FROM piece_lexicon")
        )
        assert blob.load_training_checkpoint() == text.load_training_checkpoint()
    finally:
        blob.close()
        text.close()


def test_bounded_multirow_upserts_match_ordered_executemany_across_batches(
    tmp_path,
) -> None:
    store = LexiconStore(tmp_path / "batched.sqlite")
    reference = sqlite3.connect(tmp_path / "reference.sqlite")
    checkpoint = {"history": [{}]}
    try:
        store.begin_piece_count_pass(
            resume=False,
            checkpoint=checkpoint,
            objective_model=S1M2_REUSABLE_PIECES_V3,
        )
        reference.executescript(
            "CREATE TABLE piece_counts_next(form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL) WITHOUT ROWID;"
            "CREATE TABLE lexical_diagnostics_next(form_key TEXT PRIMARY KEY, expected_count REAL NOT NULL) WITHOUT ROWID;"
            "CREATE TABLE piece_host_support_next(piece_key TEXT NOT NULL, host_key BLOB NOT NULL, support REAL NOT NULL, PRIMARY KEY(piece_key, host_key)) WITHOUT ROWID;"
        )
        piece_rows = [(f"piece-{index % 470:04d}", float(index % 7 + 1)) for index in range(940)]
        lexical_rows = [(f"host-{index % 460:04d}", float(index % 5 + 1)) for index in range(920)]
        host_rows = [
            (
                f"piece-{index % 310:04d}",
                pack_host_key("V_A" if index % 2 else "C_K.V_A"),
                float(index % 11 + 1),
            )
            for index in range(930)
        ]

        store.begin_document_counts()
        store.add_document_piece_count_keys(piece_rows)
        store.add_document_lexical_diagnostic_keys(lexical_rows)
        store.add_document_piece_host_support_keys(host_rows)
        store.commit_document(checkpoint)

        reference.executemany(
            "INSERT INTO piece_counts_next VALUES (?, ?) ON CONFLICT(form_key) DO UPDATE SET expected_count=expected_count+excluded.expected_count",
            piece_rows,
        )
        reference.executemany(
            "INSERT INTO lexical_diagnostics_next VALUES (?, ?) ON CONFLICT(form_key) DO UPDATE SET expected_count=expected_count+excluded.expected_count",
            lexical_rows,
        )
        reference.executemany(
            "INSERT INTO piece_host_support_next VALUES (?, ?, ?) ON CONFLICT(piece_key, host_key) DO UPDATE SET support=support+excluded.support",
            host_rows,
        )
        reference.commit()

        for table, columns, order in (
            ("piece_counts_next", "form_key, expected_count", "form_key"),
            ("lexical_diagnostics_next", "*", "form_key"),
            ("piece_host_support_next", "*", "piece_key, host_key"),
        ):
            assert tuple(store.connection.execute(f"SELECT {columns} FROM {table} ORDER BY {order}")) == tuple(
                reference.execute(f"SELECT {columns} FROM {table} ORDER BY {order}")
            )
        assert store.telemetry.counters["sqlite_piece_count_batch_calls"] == 3
        assert store.telemetry.counters["sqlite_lexical_diagnostic_batch_calls"] == 3
        assert store.telemetry.counters["sqlite_piece_host_support_batch_calls"] == 4
        assert store.telemetry.gauges["sqlite_piece_count_batch_max_rows"] == 450
        assert store.telemetry.gauges["sqlite_piece_host_support_batch_max_rows"] == 300
    finally:
        reference.close()
        store.close()

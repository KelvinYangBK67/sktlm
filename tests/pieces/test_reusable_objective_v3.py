from __future__ import annotations

import itertools
import math

import pytest

from sktlm.latent.phonology import parse_iast_form
from sktlm.latent.store import LexiconStore
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
    assert v3_config.payload()["learned_count_semantics"].startswith(
        "R_cross(q)=C(q)-sum_h"
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


def test_v3_sqlite_moments_role_shadow_and_scorer_are_separate(tmp_path) -> None:
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

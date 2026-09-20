from __future__ import annotations

import pytest

from sktlm.latent.phonology import parse_iast_form
from sktlm.latent.store import LexiconStore
from sktlm.latent.training import S1M2_MODEL, TrainingConfig
from sktlm.pieces import (
    BaseMeasurePieceScorer,
    PieceIdentity,
    PieceModel,
    PieceRole,
    build_piece_lattice,
    fit_production_piece_model,
    select_reusable_inventory,
)


def test_self_repetition_and_cross_host_reuse() -> None:
    whole = parse_iast_form("gacchati")
    few = fit_production_piece_model((whole,) * 2, passes=1).history[0]
    many = fit_production_piece_model((whole,) * 20, passes=1).history[0]
    for state in (few, many):
        assert state.raw_expected_counts[whole] > 0
        assert state.max_host_expected_usage[whole] == pytest.approx(
            state.raw_expected_counts[whole]
        )
        assert state.reusable_counts[whole] == pytest.approx(0)

    shared = parse_iast_form("ti")
    hosts = tuple(parse_iast_form(text) for text in ("gacchati", "bhavati", "vadati"))
    two = fit_production_piece_model(hosts[:2], passes=1).history[0]
    three = fit_production_piece_model(hosts, passes=1).history[0]
    assert two.reusable_counts[shared] > 0
    assert three.reusable_counts[shared] > two.reusable_counts[shared]


def test_dominant_host_and_role_collapse() -> None:
    piece = parse_iast_form("deva")
    a, b = parse_iast_form("deva"), parse_iast_form("devam")
    raw, maximum, reusable = select_reusable_inventory({(piece, a): 1000, (piece, b): 1})
    assert (raw[piece], maximum[piece], reusable[piece]) == (1001, 1000, 1)

    identities = tuple(PieceIdentity(piece, role) for role in PieceRole)
    assert {identity.key for identity in identities} == {piece.key}
    raw, maximum, reusable = select_reusable_inventory({(piece, a): 3, (piece, b): 4})
    assert (raw[piece], maximum[piece], reusable[piece]) == (7, 4, 3)


def test_role_collapsed_host_support_conserves_posterior_expected_count() -> None:
    hosts = tuple(parse_iast_form(text) for text in ("devam", "madeva", "devadeva"))
    model = PieceModel.neutral()
    support = {}
    ordinary = {}
    for host in hosts:
        for identity, usage in model.evaluate(host).expected_piece_counts.items():
            support[(identity.piece, host)] = support.get((identity.piece, host), 0) + usage
            ordinary[identity.piece] = ordinary.get(identity.piece, 0) + usage
    raw, _, _ = select_reusable_inventory(support)
    assert raw == pytest.approx(ordinary, rel=1e-10, abs=1e-12)


def test_scorer_uses_reusable_count_for_probability_and_complexity() -> None:
    a, b = parse_iast_form("deva"), parse_iast_form("rāma")
    assert len(a.symbols) == len(b.symbols)
    # Both pieces can have raw C=100, while different strongest hosts give
    # R=0 and R=50. The scorer receives only the learned R map.
    scorer = BaseMeasurePieceScorer(
        {a: 0.0, b: 50.0}, alpha=0.1, lambda_=0.5,
        kappa=1.0, beta=0.25, tau=1.0,
    )
    assert scorer.probability(b) > scorer.probability(a)
    assert scorer.complexity_increment(b) < scorer.complexity_increment(a)
    assert scorer.score_piece(b, PieceRole.LEFT) == scorer.score_piece(b, PieceRole.WHOLE)
    with pytest.raises(TypeError, match="phonological form"):
        BaseMeasurePieceScorer(
            {PieceIdentity(a, PieceRole.LEFT): 50.0}, alpha=0.1,
            lambda_=0.5, kappa=1.0, beta=0.25, tau=1.0,
        )


def test_sqlite_finalization_stores_c_m_r_and_scores_rolelessly(tmp_path) -> None:
    store = LexiconStore(tmp_path / "learner.sqlite")
    checkpoint = {"history": [{}]}
    piece = parse_iast_form("ti")
    a, b = parse_iast_form("gacchati"), parse_iast_form("bhavati")
    try:
        store.begin_piece_count_pass(resume=False, checkpoint=checkpoint)
        with store.connection:
            store.connection.execute("BEGIN IMMEDIATE")
            store.add_document_piece_counts([
                (PieceIdentity(piece, PieceRole.RIGHT), 1000),
                (PieceIdentity(piece, PieceRole.LEFT), 1),
            ])
            store.add_document_piece_host_support([
                (PieceIdentity(piece, PieceRole.RIGHT), a, 1000),
                (PieceIdentity(piece, PieceRole.LEFT), b, 1),
            ])
        assert store.connection.execute(
            "SELECT SUM(support) FROM piece_host_support_next WHERE piece_key=?",
            (piece.key,),
        ).fetchone()[0] == 1001
        assert store.finalize_piece_count_pass(checkpoint=checkpoint) == (1, 1, 1)
        row = store.connection.execute(
            "SELECT form_key, raw_expected_count, max_host_expected_usage, "
            "reusable_count FROM piece_lexicon"
        ).fetchone()
        assert row == (piece.key, 1001, 1000, 1)
        scorer = store.piece_scorer(
            alpha=0.1, complexity_weight=0.5, complexity_kappa=1,
            complexity_beta=0.25, complexity_tau=1,
            base_stop_probability=0.5, cache_size=8,
        )
        assert scorer.score_piece(piece, PieceRole.LEFT) == scorer.score_piece(
            piece, PieceRole.RIGHT
        )
        assert scorer._lookup(piece.key) == 1
    finally:
        store.close()


def test_v1_state_cannot_score_or_resume_as_v2(tmp_path) -> None:
    assert S1M2_MODEL == "reusable_pieces_v2"
    assert TrainingConfig(model="reusable_pieces_v2").payload()["model"] == S1M2_MODEL
    with pytest.raises(ValueError, match="unsupported model"):
        TrainingConfig(model="reusable_pieces_v1")
    store = LexiconStore(tmp_path / "legacy.sqlite")
    try:
        store.connection.execute(
            "CREATE TABLE piece_lexicon(form_key TEXT PRIMARY KEY, expected_count REAL)"
        )
        with pytest.raises(RuntimeError, match="V1 piece state"):
            store.piece_scorer(
                alpha=0.1, complexity_weight=0.5, complexity_kappa=1,
                complexity_beta=0.25, complexity_tau=1,
                base_stop_probability=0.5, cache_size=8,
            )
    finally:
        store.close()


def test_long_whole_form_fallback_remains_legal() -> None:
    form = parse_iast_form("mahābhārata")
    lattice = build_piece_lattice(form, max_piece_length=3)
    assert any(
        edge.start == 0 and edge.end == len(form.symbols)
        and edge.piece == form and edge.role is PieceRole.WHOLE
        for edge in lattice.edges
    )

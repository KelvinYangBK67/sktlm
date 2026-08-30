from __future__ import annotations

import math

import pytest

from sktlm.sandhi.dp import (
    count_paths,
    forward_log_partition,
    forward_log_scores,
    kind_bias_log_score,
    uniform_edge_log_score,
    viterbi_best_path,
)
from sktlm.sandhi.lattice import (
    build_external_sandhi_lattice,
    iter_paths,
)


def test_count_paths_matches_explicit_enumeration_on_tiny_example() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    explicit = tuple(
        iter_paths(
            lattice,
            max_paths=100000,
        )
    )

    assert count_paths(lattice) == len(explicit)


def test_uniform_forward_partition_equals_log_path_count() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    n_paths = count_paths(lattice)

    log_z = forward_log_partition(
        lattice,
        uniform_edge_log_score,
    )

    assert log_z == pytest.approx(
        math.log(n_paths),
    )


def test_forward_scores_start_at_log_one() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    alpha = forward_log_scores(
        lattice,
        uniform_edge_log_score,
    )

    assert alpha[0] == 0.0
    assert len(alpha) == lattice.num_nodes


def test_forward_partition_is_finite() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    log_z = forward_log_partition(
        lattice,
        uniform_edge_log_score,
    )

    assert math.isfinite(log_z)


def test_identity_bias_can_make_identity_path_viterbi_best() -> None:
    surface = "devo'pi"

    lattice = build_external_sandhi_lattice(
        surface,
    )

    scorer = kind_bias_log_score(
        identity_log_score=1.0,
        sandhi_log_score=-100.0,
    )

    _, path = viterbi_best_path(
        lattice,
        scorer,
    )

    assert all(
        edge.kind == "identity"
        for edge in path
    )

    assert "".join(
        edge.surface
        for edge in path
    ) == surface


def test_sandhi_bias_can_select_a_sandhi_path_for_debugging() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    scorer = kind_bias_log_score(
        identity_log_score=0.0,
        sandhi_log_score=100.0,
    )

    _, path = viterbi_best_path(
        lattice,
        scorer,
    )

    assert any(
        edge.kind == "sandhi"
        for edge in path
    )


def test_viterbi_score_is_not_greater_than_log_partition() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    scorer = kind_bias_log_score(
        identity_log_score=-0.2,
        sandhi_log_score=-0.7,
    )

    best_score, _ = viterbi_best_path(
        lattice,
        scorer,
    )

    log_z = forward_log_partition(
        lattice,
        scorer,
    )

    assert best_score <= log_z


def test_count_paths_is_at_least_one() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    assert count_paths(lattice) >= 1


def test_uniform_partition_for_identity_only_surface_is_zero_log_one() -> None:
    lattice = build_external_sandhi_lattice(
        "☃",
    )

    assert count_paths(lattice) == 1

    log_z = forward_log_partition(
        lattice,
        uniform_edge_log_score,
    )

    assert log_z == pytest.approx(0.0)

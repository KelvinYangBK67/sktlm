from __future__ import annotations

import pytest

from sktlm.sandhi.lattice import (
    build_external_sandhi_lattice,
    iter_paths,
    path_latent_pieces,
)


def test_lattice_has_one_node_per_surface_offset() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    assert lattice.num_nodes == len("devo'pi") + 1


def test_lattice_always_contains_complete_identity_path() -> None:
    surface = "devo'pi"

    lattice = build_external_sandhi_lattice(
        surface,
    )

    identity = lattice.identity_edges()

    assert len(identity) == len(surface)
    assert "".join(edge.surface for edge in identity) == surface


def test_devo_pi_lattice_contains_deva_visarga_api_sandhi_edge() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    assert any(
        edge.kind == "sandhi"
        and edge.surface == "o'"
        and edge.left_underlying == "aḥ"
        and edge.right_underlying == "a"
        for edge in lattice.sandhi_edges()
    )


def test_sandhi_edge_records_rule_provenance() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    edge = next(
        edge
        for edge in lattice.sandhi_edges()
        if edge.surface == "o'"
        and edge.left_underlying == "aḥ"
        and edge.right_underlying == "a"
    )

    assert edge.rule_id
    assert edge.variant is not None
    assert edge.rule_surface == "o'"


def test_sandhi_edge_exposes_underlying_boundary_pieces() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    edge = next(
        edge
        for edge in lattice.sandhi_edges()
        if edge.surface == "o'"
        and edge.left_underlying == "aḥ"
        and edge.right_underlying == "a"
    )

    assert edge.latent_pieces == (
        "aḥ",
        "#",
        "a",
    )


def test_identity_and_sandhi_paths_compete() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    paths = tuple(
        iter_paths(
            lattice,
            max_paths=1000,
        )
    )

    assert len(paths) > 1

    # Literal identity path survives.
    assert any(
        "".join(edge.surface for edge in path) == "devo'pi"
        and all(edge.kind == "identity" for edge in path)
        for path in paths
    )

    # At least one complete path uses the aḥ + a -> o' analysis.
    assert any(
        any(
            edge.kind == "sandhi"
            and edge.left_underlying == "aḥ"
            and edge.right_underlying == "a"
            for edge in path
        )
        for path in paths
    )


def test_latent_path_can_contain_deva_visarga_boundary_api_material() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    paths = tuple(
        iter_paths(
            lattice,
            max_paths=1000,
        )
    )

    latent_paths = tuple(
        path_latent_pieces(path)
        for path in paths
    )

    assert any(
        ("aḥ", "#", "a") == latent[i:i + 3]
        for latent in latent_paths
        for i in range(max(0, len(latent) - 2))
    )


def test_lattice_is_acyclic_and_forward_only() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    assert all(
        edge.start < edge.end
        for edge in lattice.edges
    )


def test_surviving_surface_boundary_is_available_as_sandhi_edge() -> None:
    lattice = build_external_sandhi_lattice(
        "deva kim",
    )

    assert any(
        edge.kind == "sandhi"
        and " " in edge.surface
        for edge in lattice.sandhi_edges()
    )


def test_empty_surface_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="surface must be non-empty",
    ):
        build_external_sandhi_lattice("")


def test_iter_paths_rejects_nonpositive_limit() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    with pytest.raises(
        ValueError,
        match="max_paths must be >= 1",
    ):
        tuple(
            iter_paths(
                lattice,
                max_paths=0,
            )
        )


def test_outgoing_rejects_invalid_node() -> None:
    lattice = build_external_sandhi_lattice(
        "devo'pi",
    )

    with pytest.raises(IndexError):
        lattice.outgoing(-1)

    with pytest.raises(IndexError):
        lattice.outgoing(lattice.num_nodes)

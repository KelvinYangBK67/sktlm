"""Tests for the approved surface-only IAST lattice contract."""

import hashlib
import math

from sktlm.tokenizers.base import validate_surface_spans
from sktlm.tokenizers.surface_lattice import (
    atomize_iast_surface,
    train_surface_lattice,
)


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _training_texts():
    corpus = (
        "rāma rāmasya rāmeṇa",
        "rāma rāma rāmaḥ",
        "rāmo 'pi vanaṃ gacchati",
        "rāmāyaṇaṃ ramate",
        "devaś ca rāmaś ca",
    )
    return iter(corpus * 30)


def test_iast_surface_atoms_keep_accents_and_isolate_barriers() -> None:
    text = "rāmo 'pi a\u0301"
    atoms = atomize_iast_surface(text)
    assert [atom.text for atom in atoms] == [
        "r",
        "ā",
        "m",
        "o",
        " ",
        "'",
        "p",
        "i",
        " ",
        "a\u0301",
    ]
    assert [atom.mergeable for atom in atoms] == [
        True,
        True,
        True,
        True,
        False,
        False,
        True,
        True,
        False,
        True,
    ]


def test_surface_lattice_is_connected_ambiguous_barrier_safe_and_lossless(tmp_path) -> None:
    tokenizer = train_surface_lattice(
        _training_texts,
        tmp_path / "model",
        vocab_size=64,
        max_piece_atoms=8,
    )
    text = "rāma 'pi rāmasya"
    lattice = tokenizer.build_lattice(text)
    encoding, stats = tokenizer.encode_with_lattice(text)

    assert lattice.node_offsets == tuple(
        [0, *(atom.end for atom in atomize_iast_surface(text))]
    )
    assert all(arc.start_node < arc.end_node for arc in lattice.arcs)
    assert all(lattice.arcs_from(node) for node in range(lattice.node_count - 1))
    assert stats.arc_count == len(lattice.arcs)
    assert stats.ambiguous_node_count > 0
    assert math.isfinite(stats.log_probability)

    atoms = atomize_iast_surface(text)
    for arc in lattice.arcs:
        covered = atoms[arc.start_node : arc.end_node]
        if not covered[0].mergeable:
            assert len(covered) == 1
        assert not (
            any(atom.mergeable for atom in covered)
            and any(not atom.mergeable for atom in covered)
        )

    validate_surface_spans(text, encoding)
    assert tokenizer.decode(encoding.ids) == text
    assert all(
        text[start:end] == piece
        for piece, (start, end) in zip(encoding.pieces, encoding.spans)
    )


def test_surface_lattice_has_explicit_unknown_arc_and_deterministic_model(tmp_path) -> None:
    model_dir = tmp_path / "model"
    first = train_surface_lattice(_training_texts, model_dir, vocab_size=48)
    first_hashes = (_sha256(first.model_path), _sha256(first.metadata_path))

    lattice = first.build_lattice("Ω")
    assert len(lattice.arcs) == 1
    assert lattice.arcs[0].token_id == 0
    assert lattice.arcs[0].log_score == -20.0
    encoding, stats = first.encode_with_lattice("Ω")
    assert encoding.ids == (0,)
    assert stats.log_probability == -20.0

    second = train_surface_lattice(_training_texts, model_dir, vocab_size=48)
    assert (_sha256(second.model_path), _sha256(second.metadata_path)) == first_hashes

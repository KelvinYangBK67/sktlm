"""Contract and model tests for the approved Devanagari Akṣara-safe BPE."""

import hashlib

from sktlm.tokenizers.aksara_bpe import (
    atomize_devanagari_aksaras,
    train_aksara_safe_bpe,
)
from sktlm.tokenizers.base import validate_surface_spans


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _training_texts():
    corpus = (
        "क्षेत्रं गच्छति॥",
        "गच्छति क्षेत्रं।",
        "रामोऽपि धावति।",
    )
    return iter(corpus * 8)


def test_aksara_atomizer_profiles_conjuncts_join_controls_and_barriers() -> None:
    text = "क्षेत्रं गच्छति॥"
    atoms = atomize_devanagari_aksaras(text)
    assert [atom.text for atom in atoms] == [
        "क्षे",
        "त्रं",
        " ",
        "ग",
        "च्छ",
        "ति",
        "॥",
    ]
    assert [atom.mergeable for atom in atoms] == [True, True, False, True, True, True, False]

    assert [atom.text for atom in atomize_devanagari_aksaras("क्\u200dषि")] == [
        "क्\u200dषि"
    ]
    zwnj_atoms = atomize_devanagari_aksaras("क्\u200cषि")
    assert [atom.text for atom in zwnj_atoms] == ["क्\u200c", "षि"]
    assert [atom.mergeable for atom in zwnj_atoms] == [False, True]
    avagraha_atoms = atomize_devanagari_aksaras("रामोऽपि")
    assert [atom.text for atom in avagraha_atoms] == ["रा", "मो", "ऽ", "पि"]
    assert not avagraha_atoms[2].mergeable


def test_aksara_safe_bpe_round_trips_and_never_splits_an_atom(tmp_path) -> None:
    tokenizer = train_aksara_safe_bpe(
        _training_texts,
        tmp_path / "model",
        vocab_size=64,
        max_piece_atoms=4,
    )
    text = "क्षेत्रं गच्छति॥"
    encoding = tokenizer.encode(text)
    validate_surface_spans(text, encoding)
    assert tokenizer.decode(encoding.ids) == text

    atom_boundaries = {
        boundary
        for atom in atomize_devanagari_aksaras(text)
        for boundary in (atom.start, atom.end)
    }
    assert all(start in atom_boundaries and end in atom_boundaries for start, end in encoding.spans)
    assert all(
        text[start:end] == piece
        for piece, (start, end) in zip(encoding.pieces, encoding.spans)
    )
    assert tokenizer.fingerprint_payload()["atomizer"] == "devanagari_aksara_bpe_v1"


def test_aksara_training_is_byte_deterministic_at_the_same_location(tmp_path) -> None:
    model_dir = tmp_path / "model"
    first = train_aksara_safe_bpe(_training_texts, model_dir, vocab_size=48)
    first_hashes = (_sha256(first.model_path), _sha256(first.metadata_path))
    second = train_aksara_safe_bpe(_training_texts, model_dir, vocab_size=48)
    assert (_sha256(second.model_path), _sha256(second.metadata_path)) == first_hashes

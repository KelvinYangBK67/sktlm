"""Akṣara-safe BPE over an explicit Devanagari orthographic profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sktlm.tokenizers._surrogate import (
    SurfaceAtom,
    SurrogateSentencePieceTokenizer,
    TrainingTextFactory,
    train_surrogate_sentencepiece,
)
from sktlm.tokenizers.base import Encoding


AKSARA_CONTRACT = "devanagari_aksara_bpe_v1"
VIRAMA = "\u094d"
NUKTA = "\u093c"
ZWJ = "\u200d"
ZWNJ = "\u200c"


def _in_ranges(codepoint: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= codepoint <= end for start, end in ranges)


def _is_consonant(char: str) -> bool:
    return _in_ranges(
        ord(char),
        (
            (0x0915, 0x0939),
            (0x0958, 0x095F),
            (0x0978, 0x097F),
        ),
    )


def _is_independent_base(char: str) -> bool:
    codepoint = ord(char)
    return (
        _in_ranges(codepoint, ((0x0904, 0x0914), (0x0960, 0x0961), (0x0972, 0x0977)))
        or codepoint == 0x0950
    )


def _is_trailing_mark(char: str) -> bool:
    codepoint = ord(char)
    if char == VIRAMA:
        return False
    return _in_ranges(
        codepoint,
        (
            (0x0900, 0x0903),
            (0x093A, 0x093C),
            (0x093E, 0x094C),
            (0x094E, 0x094F),
            (0x0951, 0x0957),
            (0x0962, 0x0963),
            (0x1CD0, 0x1CFF),
            (0xA8E0, 0xA8FF),
        ),
    )


def atomize_devanagari_aksaras(text: str) -> tuple[SurfaceAtom, ...]:
    """Apply the frozen v1 Devanagari akṣara and barrier rules."""
    atoms: list[SurfaceAtom] = []
    index = 0
    while index < len(text):
        start = index
        char = text[index]
        if _is_consonant(char):
            index += 1
            if index < len(text) and text[index] == NUKTA:
                index += 1
            mergeable = True
            while index < len(text) and text[index] == VIRAMA:
                index += 1
                if index < len(text) and text[index] == ZWNJ:
                    index += 1
                    mergeable = False
                    break
                if index < len(text) and text[index] == ZWJ:
                    index += 1
                if index < len(text) and _is_consonant(text[index]):
                    index += 1
                    if index < len(text) and text[index] == NUKTA:
                        index += 1
                    continue
                break
            while index < len(text) and _is_trailing_mark(text[index]):
                index += 1
            atoms.append(SurfaceAtom(text[start:index], start, index, mergeable))
            continue

        if _is_independent_base(char):
            index += 1
            while index < len(text) and _is_trailing_mark(text[index]):
                index += 1
            atoms.append(SurfaceAtom(text[start:index], start, index, True))
            continue

        index += 1
        atoms.append(SurfaceAtom(char, start, index, False))
    return tuple(atoms)


class AksaraSafeBPETokenizer(SurrogateSentencePieceTokenizer):
    """BPE whose internal symbols are complete Devanagari akṣara atoms."""

    name = "aksara_safe_bpe"
    unknown_semantics = "unseen_train_vocabulary_devanagari_aksara_atom"

    def __init__(self, model_path: Path) -> None:
        super().__init__(model_path, expected_contract=AKSARA_CONTRACT)
        self.unknown_semantics = type(self).unknown_semantics

    def encode(self, text: str) -> Encoding:
        atoms = atomize_devanagari_aksaras(text)
        ids: list[int] = []
        pieces: list[str] = []
        spans: list[tuple[int, int]] = []
        mergeable: list[SurfaceAtom] = []

        def append_encoding(encoding: Encoding) -> None:
            ids.extend(encoding.ids)
            pieces.extend(encoding.pieces)
            spans.extend(encoding.spans)

        def flush_mergeable() -> None:
            if mergeable:
                append_encoding(self._encode_known_atoms(mergeable))
                mergeable.clear()

        for atom in atoms:
            known = atom.text in self.atom_to_symbol
            if atom.mergeable and known:
                mergeable.append(atom)
                continue
            flush_mergeable()
            append_encoding(
                self._encode_known_atoms([atom]) if known else self._unknown_atom(atom)
            )
        flush_mergeable()
        return Encoding(tuple(ids), tuple(pieces), tuple(spans))

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            **super().fingerprint_payload(),
            "type": self.name,
            "atomizer": AKSARA_CONTRACT,
        }


def train_aksara_safe_bpe(
    texts: TrainingTextFactory,
    model_dir: Path,
    *,
    vocab_size: int,
    max_piece_atoms: int = 16,
) -> AksaraSafeBPETokenizer:
    """Fit one independent deterministic Akṣara-safe BPE model."""
    model_path = train_surrogate_sentencepiece(
        texts,
        model_dir / f"aksara_safe_bpe_{vocab_size}",
        atomizer=atomize_devanagari_aksaras,
        contract=AKSARA_CONTRACT,
        model_type="bpe",
        vocab_size=vocab_size,
        max_piece_atoms=max_piece_atoms,
        metadata={
            "atomizer": AKSARA_CONTRACT,
            "zwj_policy": "continue_conjunct",
            "zwnj_policy": "close_atom_and_barrier",
        },
    )
    return AksaraSafeBPETokenizer(model_path)

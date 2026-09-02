"""Deterministic Unicode code-point tokenizer baseline."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sktlm.tokenizers.base import Encoding, Tokenizer


SPECIAL_PIECES = ("<unk>", "<s>", "</s>", "<pad>")


class CharacterTokenizer(Tokenizer):
    name = "character"
    bos_id = 1
    eos_id = 2
    unknown_id = 0
    unknown_semantics = "unseen_train_vocabulary_unicode_codepoint"

    def __init__(self, vocabulary: Iterable[str]) -> None:
        pieces = list(SPECIAL_PIECES) + sorted(set(vocabulary))
        self._pieces = tuple(pieces)
        self._ids = {piece: index for index, piece in enumerate(self._pieces)}

    @classmethod
    def train(cls, texts: Iterable[str]) -> "CharacterTokenizer":
        return cls(char for text in texts for char in text)

    @property
    def vocab_size(self) -> int:
        return len(self._pieces)

    def encode(self, text: str) -> Encoding:
        ids = tuple(self._ids.get(char, 0) for char in text)
        return Encoding(ids=ids, pieces=tuple(text), spans=tuple((index, index + 1) for index in range(len(text))))

    def decode(self, ids: list[int] | tuple[int, ...]) -> str:
        output: list[str] = []
        for token_id in ids:
            if token_id == 0:
                output.append("�")
            elif token_id >= len(SPECIAL_PIECES) and token_id < len(self._pieces):
                output.append(self._pieces[token_id])
        return "".join(output)

    def fingerprint_payload(self) -> dict[str, Any]:
        return {**super().fingerprint_payload(), "pieces": list(self._pieces)}

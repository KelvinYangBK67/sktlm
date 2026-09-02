"""Unicode extended-grapheme-cluster tokenizer baseline."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import regex

from sktlm.tokenizers.base import Encoding, Tokenizer
from sktlm.tokenizers.character import SPECIAL_PIECES


class GraphemeTokenizer(Tokenizer):
    name = "grapheme"
    bos_id = 1
    eos_id = 2
    unknown_id = 0
    unknown_semantics = "unseen_train_vocabulary_extended_grapheme_cluster"

    def __init__(self, vocabulary: Iterable[str]) -> None:
        self._pieces = tuple(list(SPECIAL_PIECES) + sorted(set(vocabulary)))
        self._ids = {piece: index for index, piece in enumerate(self._pieces)}

    @staticmethod
    def graphemes(text: str) -> list[str]:
        return regex.findall(r"\X", text)

    @classmethod
    def train(cls, texts: Iterable[str]) -> "GraphemeTokenizer":
        return cls(cluster for text in texts for cluster in cls.graphemes(text))

    @property
    def vocab_size(self) -> int:
        return len(self._pieces)

    def encode(self, text: str) -> Encoding:
        matches = list(regex.finditer(r"\X", text))
        pieces = tuple(match.group(0) for match in matches)
        ids = tuple(self._ids.get(piece, 0) for piece in pieces)
        spans = tuple(match.span() for match in matches)
        return Encoding(ids, pieces, spans)

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

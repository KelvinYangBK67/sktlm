"""UTF-8 byte tokenizer with byte spans mapped back to character spans."""

from __future__ import annotations

from sktlm.tokenizers.base import Encoding, Tokenizer


BYTE_OFFSET = 4


class ByteTokenizer(Tokenizer):
    name = "byte"
    bos_id = 1
    eos_id = 2

    @property
    def vocab_size(self) -> int:
        return BYTE_OFFSET + 256

    def encode(self, text: str) -> Encoding:
        ids: list[int] = []
        pieces: list[str] = []
        spans: list[tuple[int, int]] = []
        byte_spans: list[tuple[int, int]] = []
        byte_offset = 0
        for char_index, char in enumerate(text):
            encoded = char.encode("utf-8")
            for local_offset, value in enumerate(encoded):
                ids.append(BYTE_OFFSET + value)
                pieces.append(f"<0x{value:02X}>")
                spans.append((char_index, char_index + 1))
                byte_spans.append((byte_offset + local_offset, byte_offset + local_offset + 1))
            byte_offset += len(encoded)
        return Encoding(tuple(ids), tuple(pieces), tuple(spans), tuple(byte_spans))

    def decode(self, ids: list[int] | tuple[int, ...]) -> str:
        values = bytes(token_id - BYTE_OFFSET for token_id in ids if BYTE_OFFSET <= token_id < self.vocab_size)
        return values.decode("utf-8")

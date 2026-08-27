"""Existing token-stream dataset helpers for tiny Sanskrit LM experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

import torch
from torch.utils.data import Dataset

from sktlm.data.representations.canonical import RepresentedSegment
from sktlm.tokenizers.base import Tokenizer


def read_corpus_texts(data_dir: Path) -> list[str]:
    """Read all processed .txt files in deterministic order."""
    texts: list[str] = []
    for path in sorted(data_dir.rglob("*.txt")):
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                texts.append(text)
    return texts


def encode_corpus(
    data_dir: Path,
    tokenizer_path: Path,
    max_tokens: int | None = None,
) -> torch.Tensor:
    """Legacy compatibility: encode a directory into one token stream."""
    import sentencepiece as spm

    processor = spm.SentencePieceProcessor(model_file=str(tokenizer_path))
    ids: list[int] = []
    eos_id = processor.eos_id()
    for text in read_corpus_texts(data_dir):
        ids.extend(processor.encode(text, out_type=int))
        if eos_id >= 0:
            ids.append(eos_id)
        if max_tokens is not None and len(ids) >= max_tokens:
            ids = ids[:max_tokens]
            break
    if len(ids) < 2:
        raise ValueError("encoded corpus is too small for language-model training")
    return torch.tensor(ids, dtype=torch.long)


def split_train_val(tokens: torch.Tensor, train_fraction: float) -> tuple[torch.Tensor, torch.Tensor]:
    """Split one token stream into train and validation streams."""
    split_at = max(1, min(len(tokens) - 1, int(len(tokens) * train_fraction)))
    return tokens[:split_at], tokens[split_at:]


class BlockDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """Legacy fixed-length blocks from one already-split token stream."""

    def __init__(self, tokens: torch.Tensor, context_length: int) -> None:
        if len(tokens) <= context_length:
            raise ValueError("token stream must be longer than context length")
        self.tokens = tokens
        self.context_length = context_length

    def __len__(self) -> int:
        return len(self.tokens) - self.context_length

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        chunk = self.tokens[index : index + self.context_length + 1]
        return chunk[:-1], chunk[1:]


@dataclass(frozen=True, slots=True)
class EncodedSegment:
    """Token IDs tied to the text identity selected before tokenization."""

    segment_id: str
    split: str
    text: str
    ids: tuple[int, ...]


def encode_segments(
    segments: Sequence[RepresentedSegment],
    tokenizer: Tokenizer,
    *,
    prepend_bos: bool = True,
    append_eos: bool = True,
) -> list[EncodedSegment]:
    """Encode fixed represented segments with explicit sequence delimiters."""
    encoded: list[EncodedSegment] = []
    for segment in segments:
        ids = list(tokenizer.encode(segment.text).ids)
        if prepend_bos and tokenizer.bos_id is not None:
            ids.insert(0, tokenizer.bos_id)
        if append_eos and tokenizer.eos_id is not None:
            ids.append(tokenizer.eos_id)
        encoded.append(EncodedSegment(segment.segment_id, segment.split, segment.text, tuple(ids)))
    return encoded


class SegmentBlockDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """Next-token blocks that never cross a canonical segment boundary."""

    def __init__(self, segments: Sequence[EncodedSegment], context_length: int) -> None:
        self.segments = list(segments)
        self.context_length = context_length
        self._positions: list[tuple[int, int]] = []
        for segment_index, segment in enumerate(self.segments):
            self._positions.extend(
                (segment_index, start)
                for start in range(max(0, len(segment.ids) - context_length))
            )
        if not self._positions:
            raise ValueError("no encoded segment is longer than context_length")

    def __len__(self) -> int:
        return len(self._positions)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        segment_index, start = self._positions[index]
        ids = self.segments[segment_index].ids
        chunk = torch.tensor(ids[start : start + self.context_length + 1], dtype=torch.long)
        return chunk[:-1], chunk[1:]

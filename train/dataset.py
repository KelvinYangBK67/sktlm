"""Dataset helpers for tiny Sanskrit language-model experiments."""

from __future__ import annotations

from pathlib import Path

import sentencepiece as spm
import torch
from torch.utils.data import Dataset


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
    """Encode the processed corpus into one token stream."""
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
    """Fixed-length next-token prediction blocks from a token stream."""

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


"""Config-driven construction of the supported tokenizer baselines."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from sktlm.tokenizers.base import Tokenizer
from sktlm.tokenizers.byte import ByteTokenizer
from sktlm.tokenizers.character import CharacterTokenizer
from sktlm.tokenizers.grapheme import GraphemeTokenizer
from sktlm.tokenizers.sentencepiece import (
    SentencePieceBPETokenizer,
    SentencePieceUnigramTokenizer,
    train_sentencepiece_from_texts,
)


TOKENIZER_TYPES = {"bpe", "unigram", "character", "byte", "grapheme"}


def build_tokenizer(
    config: Mapping[str, Any],
    training_texts: Iterable[str] = (),
    *,
    model_dir: Path | None = None,
) -> Tokenizer:
    """Build one of five controlled baselines from a shallow config mapping."""
    tokenizer_type = str(config["type"])
    if tokenizer_type not in TOKENIZER_TYPES:
        raise ValueError(f"unsupported tokenizer type: {tokenizer_type}")
    if tokenizer_type == "byte":
        return ByteTokenizer()
    if tokenizer_type == "character":
        return CharacterTokenizer.train(training_texts)
    if tokenizer_type == "grapheme":
        return GraphemeTokenizer.train(training_texts)

    model_path = config.get("model_path")
    if not model_path:
        if model_dir is None:
            raise ValueError(
                f"{tokenizer_type} tokenizer requires model_path or a model_dir for train-split fitting"
            )
        vocab_size = int(config.get("vocab_size", 24000))
        model_path = train_sentencepiece_from_texts(
            training_texts,
            model_dir / f"{tokenizer_type}_{vocab_size}",
            vocab_size,
            tokenizer_type,
        )
    if tokenizer_type == "bpe":
        return SentencePieceBPETokenizer(Path(str(model_path)))
    return SentencePieceUnigramTokenizer(Path(str(model_path)))

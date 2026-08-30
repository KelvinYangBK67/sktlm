"""Integration checks for the tracked 24k SentencePiece artifacts."""

from pathlib import Path

import pytest
import sentencepiece as spm

from sktlm.tokenizers.base import validate_surface_spans
from sktlm.tokenizers.sentencepiece import SentencePieceBPETokenizer, SentencePieceUnigramTokenizer


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "model_name",
    [
        "weighted_bpe_24000_danda_split.model",
        "weighted_unigram_24000_danda_split.model",
    ],
)
def test_existing_24k_model_loads_and_encodes(model_name: str) -> None:
    processor = spm.SentencePieceProcessor(model_file=str(REPO_ROOT / "tokenizer" / model_name))
    assert processor.vocab_size() == 24000
    assert (processor.unk_id(), processor.bos_id(), processor.eos_id(), processor.pad_id()) == (0, 1, 2, 3)
    assert processor.encode("रामः गच्छति।", out_type=int)


@pytest.mark.parametrize(
    ("adapter", "model_name"),
    [
        (SentencePieceBPETokenizer, "weighted_bpe_24000_danda_split.model"),
        (SentencePieceUnigramTokenizer, "weighted_unigram_24000_danda_split.model"),
    ],
)
def test_existing_24k_adapter_tracks_surface_spans(adapter, model_name: str) -> None:
    text = "रामः गच्छति।"
    tokenizer = adapter(REPO_ROOT / "tokenizer" / model_name)
    encoding = tokenizer.encode(text)
    assert tokenizer.vocab_size == 24000
    assert len(encoding.ids) == len(encoding.pieces) == len(encoding.spans)
    validate_surface_spans(text, encoding)
    assert tokenizer.decode(encoding.ids) == text

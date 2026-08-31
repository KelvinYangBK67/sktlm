"""Unified encode/decode/span tests for non-SentencePiece baselines."""

import pytest

from sktlm.tokenizers.base import validate_surface_spans
from sktlm.tokenizers.byte import ByteTokenizer
from sktlm.tokenizers.character import CharacterTokenizer
from sktlm.tokenizers.factory import build_tokenizer
from sktlm.tokenizers.grapheme import GraphemeTokenizer


@pytest.mark.parametrize("tokenizer_type", ["character", "byte", "grapheme"])
def test_baseline_factory_and_round_trip(tokenizer_type: str) -> None:
    text = "देवोऽपि rāmaḥ"
    tokenizer = build_tokenizer({"type": tokenizer_type}, training_texts=[text])
    encoding = tokenizer.encode(text)
    validate_surface_spans(text, encoding)
    assert tokenizer.decode(encoding.ids) == text


def test_character_spans_are_unicode_code_points() -> None:
    text = "कि"
    encoding = CharacterTokenizer.train([text]).encode(text)
    assert encoding.pieces == ("क", "ि")
    assert encoding.spans == ((0, 1), (1, 2))


def test_byte_spans_map_each_utf8_byte_to_character() -> None:
    text = "aक"
    encoding = ByteTokenizer().encode(text)
    assert len(encoding.ids) == len(text.encode("utf-8")) == 4
    assert encoding.spans == ((0, 1), (1, 2), (1, 2), (1, 2))
    assert encoding.byte_spans == ((0, 1), (1, 2), (2, 3), (3, 4))


def test_grapheme_tokenizer_keeps_devanagari_cluster_whole() -> None:
    text = "कि"
    encoding = GraphemeTokenizer.train([text]).encode(text)
    assert encoding.pieces == (text,)
    assert encoding.spans == ((0, 2),)


@pytest.mark.parametrize("tokenizer_type", ["bpe", "unigram"])
def test_sentencepiece_factory_can_fit_fixed_training_texts(tmp_path, tokenizer_type: str) -> None:
    texts = ["rāmaḥ gacchati", "sītā vanaṃ gacchati", "devo'pi dhāvati"]
    tokenizer = build_tokenizer(
        {"type": tokenizer_type, "vocab_size": 32},
        training_texts=texts,
        model_dir=tmp_path,
    )

    encoding = tokenizer.encode(texts[0])
    validate_surface_spans(texts[0], encoding)
    assert all(0 <= begin <= end <= len(texts[0]) for begin, end in encoding.spans)
    assert tokenizer.decode(encoding.ids) == texts[0]
    assert (tmp_path / f"{tokenizer_type}_32.model").is_file()

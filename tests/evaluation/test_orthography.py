"""Tests for orthographic and tokenizer occupancy diagnostics."""

from sktlm.evaluation.orthography import (
    ends_with_virama,
    grapheme_split_rate,
    invalid_grapheme_boundary_rate,
    starts_with_dependent_vowel,
)
from sktlm.evaluation.tokenizer import evaluate_tokenizer
from sktlm.tokenizers.base import Encoding
from sktlm.tokenizers.character import CharacterTokenizer
from sktlm.tokenizers.grapheme import GraphemeTokenizer


def test_dependent_vowel_and_virama_detection() -> None:
    assert starts_with_dependent_vowel("▁ात")
    assert not starts_with_dependent_vowel("▁कात")
    assert ends_with_virama("त्")
    assert not ends_with_virama("त")


def test_character_tokenizer_splits_a_devanagari_grapheme() -> None:
    text = "कि"
    encoding = CharacterTokenizer.train([text]).encode(text)
    assert grapheme_split_rate(text, encoding) == 1.0
    assert invalid_grapheme_boundary_rate(text, encoding) == 1.0


def test_grapheme_tokenizer_has_no_invalid_grapheme_boundary() -> None:
    text = "कि"
    encoding = GraphemeTokenizer.train([text]).encode(text)
    assert grapheme_split_rate(text, encoding) == 0.0
    assert invalid_grapheme_boundary_rate(text, encoding) == 0.0


def test_sandhi_fragment_metric_is_explicitly_pattern_based() -> None:
    text = "देवोऽपि"
    encoding = Encoding(ids=(5,), pieces=(text,), spans=((0, len(text)),))
    metrics = evaluate_tokenizer([(text, encoding)])
    assert metrics["suspect_token_count"] == 1
    assert metrics["frequency_weighted_suspect_occupancy"] == 1.0
    assert "ोऽपि" in metrics["sandhi_patterns"]

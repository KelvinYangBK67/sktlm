"""Tests for clean transliteration and the explicit legacy spacing condition."""

from sktlm.representations.devanagari import (
    iast_to_devanagari,
    tokenize_iast,
    transliterate_iast_to_devanagari,
)
from sktlm.representations.spacing import apply_spacing, remove_joining_rule_spaces


def test_iast_to_devanagari_regression_examples() -> None:
    expected = {
        "rāmo 'sti |": "रामो ऽस्ति ।",
        "tat tvam asi ||": "तत् त्वम् असि ॥",
        "agnim īḷe purohitaṃ |": "अग्निम् ईऌए पुरोहितं ।",
    }
    assert {text: iast_to_devanagari(text) for text in expected} == expected


def test_joining_rule_drops_vowel_avagraha_space() -> None:
    assert remove_joining_rule_spaces(tokenize_iast("a 'a")) == ["a", "'", "a"]
    assert apply_spacing("a 'a", "legacy_joined", "iast") == "a'a"
    assert transliterate_iast_to_devanagari("a 'a") == "अ ऽअ"


def test_joining_rule_drops_consonant_consonant_space() -> None:
    assert remove_joining_rule_spaces(tokenize_iast("t t")) == ["t", "t"]
    assert apply_spacing("t t", "legacy_joined", "iast") == "tt"
    assert iast_to_devanagari("t t") == "त् त्"


def test_joining_rule_drops_consonant_vowel_space() -> None:
    assert remove_joining_rule_spaces(tokenize_iast("t a")) == ["t", "a"]
    assert apply_spacing("t a", "legacy_joined", "iast") == "ta"
    assert iast_to_devanagari("t a") == "त् अ"


def test_joining_rule_keeps_other_space() -> None:
    assert remove_joining_rule_spaces(tokenize_iast("a t")) == ["a", " ", "t"]
    assert iast_to_devanagari("a t") == "अ त्"

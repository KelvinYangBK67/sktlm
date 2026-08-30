"""Invariance and regression tests for experimental representations."""

import unicodedata

from sktlm.representations.canonical import CanonicalSegment
from sktlm.representations.script import (
    RepresentationConfig,
    derive_representation,
    transform_script,
    transliterate_devanagari_to_iast,
    whitespace_signature,
)
from sktlm.representations.devanagari import transliterate_iast_to_devanagari
from sktlm.representations.spacing import apply_spacing


def make_segment(text: str = "devaś ca rāmaś ca dhāvanti") -> CanonicalSegment:
    return CanonicalSegment(
        document_id="doc_1",
        segment_id="doc_1:l00000001",
        split="test",
        canonical_text=text,
        source="gretil",
        layer="epic",
        canonical_script="iast",
    )


def test_script_transform_preserves_whitespace_pattern() -> None:
    text = "devaś  ca\trāmaś ca\ndhāvanti"
    converted = transliterate_iast_to_devanagari(text)
    assert whitespace_signature(converted) == whitespace_signature(text)


def test_transliteration_does_not_perform_legacy_joining() -> None:
    assert transliterate_iast_to_devanagari("tat tvam asi") == "तत् त्वम् असि"


def test_legacy_joined_reproduces_historical_seams() -> None:
    assert apply_spacing("tat tvam asi", "legacy_joined", "iast") == "tattvamasi"
    assert apply_spacing("तत् त्वम् असि", "legacy_joined", "devanagari") == "तत्त्वमसि"


def test_legacy_joined_does_not_classify_anusvara_or_visarga_as_consonants() -> None:
    assert apply_spacing("aṃ ka", "legacy_joined", "iast") == "aṃ ka"
    assert apply_spacing("aḥ a", "legacy_joined", "iast") == "aḥ a"


def test_legacy_joined_removes_vowel_avagraha_space() -> None:
    assert apply_spacing("a 'sti", "legacy_joined", "iast") == "a'sti"


def test_continuous_spacing_is_deterministic_and_keeps_lines() -> None:
    text = "devaś ca  rāmaś ca\ndhāvanti iti"
    expected = "devaścarāmaśca\ndhāvantiiti"
    assert apply_spacing(text, "continuous", "iast") == expected
    assert apply_spacing(text, "continuous", "iast") == expected


def test_continuous_iast_preserves_exact_danda_spacing_and_lf() -> None:
    text = "rāmaḥ gacchati | sītā tiṣṭhati\nrāmaḥ gacchati ||\n"
    expected = "rāmaḥgacchati | sītātiṣṭhati\nrāmaḥgacchati ||\n"
    assert apply_spacing(text, "continuous", "iast") == expected


def test_continuous_devanagari_preserves_exact_danda_spacing_and_lf() -> None:
    text = "रामः गच्छति । सीता तिष्ठति\nरामः गच्छति ॥\n"
    expected = "रामःगच्छति। सीतातिष्ठति\nरामःगच्छति॥\n"
    assert apply_spacing(text, "continuous", "devanagari") == expected

def test_continuous_devanagari_recomposes_consonant_vowel_boundaries() -> None:
    cases = {
        "तद् अस्ति": "तदस्ति",
        "तद् इति": "तदिति",
        "तद् उक्तम्": "तदुक्तम्",
        "तद् एव": "तदेव",
        "तद् अभ्यस्राम्यद् अभ्यतपत् समतपत्":
            "तदभ्यस्राम्यदभ्यतपत्समतपत्",
    }

    for source, expected in cases.items():
        assert apply_spacing(source, "continuous", "devanagari") == expected


def test_devanagari_surface_word_only_normalizes_danda_spacing() -> None:
    text = "रामः  गच्छति ।  सीता तिष्ठति ॥\n"
    expected = "रामः  गच्छति। सीता तिष्ठति॥\n"
    assert apply_spacing(text, "surface_word", "devanagari") == expected


def test_devanagari_legacy_joined_then_normalizes_danda_spacing() -> None:
    text = "तत् त्वम् असि ।  रामः ॥\n"
    expected = "तत्त्वमसि। रामः॥\n"
    assert apply_spacing(text, "legacy_joined", "devanagari") == expected


def test_round_trip_for_supported_common_orthography() -> None:
    devanagari = "देवोऽपि रामः।\nसीता गच्छति॥"
    iast = transliterate_devanagari_to_iast(devanagari)
    assert transliterate_iast_to_devanagari(iast) == devanagari


def test_unicode_output_is_nfc() -> None:
    converted = transform_script("ra\u0304ma", "iast", "devanagari")
    assert unicodedata.is_normalized("NFC", converted)


def test_same_segment_identity_across_all_representations() -> None:
    segment = make_segment()
    conditions = [
        RepresentationConfig("iast", "observed"),
        RepresentationConfig("iast", "continuous"),
        RepresentationConfig("devanagari", "observed"),
        RepresentationConfig("devanagari", "continuous"),
        RepresentationConfig("devanagari", "legacy_joined"),
    ]
    represented = [derive_representation(segment, condition) for condition in conditions]
    assert {item.segment_id for item in represented} == {segment.segment_id}
    assert {item.split for item in represented} == {segment.split}

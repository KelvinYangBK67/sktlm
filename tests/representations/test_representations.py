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


def test_continuous_spacing_is_deterministic_and_keeps_lines() -> None:
    text = "devaś ca  rāmaś ca\ndhāvanti iti"
    expected = "devaścarāmaśca\ndhāvantiiti"
    assert apply_spacing(text, "continuous", "iast") == expected
    assert apply_spacing(text, "continuous", "iast") == expected


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

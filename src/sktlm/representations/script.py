"""Configurable script conditions over shared canonical text segments."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from sktlm.representations.canonical import CanonicalSegment, RepresentedSegment, SUPPORTED_SCRIPTS
from sktlm.representations.devanagari import (
    CONSONANTS,
    INDEPENDENT_VOWELS,
    SIGNS,
    VIRAMA,
    VOWEL_MARKS,
    transliterate_iast_to_devanagari,
)
from sktlm.representations.spacing import SPACING_CONDITIONS, apply_spacing


DEVANAGARI_CONSONANTS = {value: key for key, value in CONSONANTS.items()}
DEVANAGARI_INDEPENDENT_VOWELS = {value: key for key, value in INDEPENDENT_VOWELS.items()}
DEVANAGARI_VOWEL_MARKS = {value: key for key, value in VOWEL_MARKS.items() if value}
DEVANAGARI_SIGNS = {value: key for key, value in SIGNS.items()}


@dataclass(frozen=True, slots=True)
class RepresentationConfig:
    """The two independent axes used to derive a text representation."""

    script: str
    spacing: str

    def __post_init__(self) -> None:
        if self.script not in SUPPORTED_SCRIPTS:
            raise ValueError(f"unsupported script condition: {self.script}")
        if self.spacing not in SPACING_CONDITIONS:
            raise ValueError(f"unsupported spacing condition: {self.spacing}")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RepresentationConfig":
        return cls(script=str(value["script"]), spacing=str(value["spacing"]))

    def as_dict(self) -> dict[str, str]:
        return {"script": self.script, "spacing": self.spacing}


def transliterate_devanagari_to_iast(text: str) -> str:
    """Mechanically convert supported Devanagari characters to NFC IAST."""
    text = unicodedata.normalize("NFC", text)
    output: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in DEVANAGARI_CONSONANTS:
            output.append(DEVANAGARI_CONSONANTS[char])
            following = text[index + 1] if index + 1 < len(text) else ""
            if following == VIRAMA:
                index += 2
                continue
            if following in DEVANAGARI_VOWEL_MARKS:
                output.append(DEVANAGARI_VOWEL_MARKS[following])
                index += 2
                continue
            output.append("a")
            index += 1
            continue
        if char in DEVANAGARI_INDEPENDENT_VOWELS:
            output.append(DEVANAGARI_INDEPENDENT_VOWELS[char])
        elif char in DEVANAGARI_VOWEL_MARKS:
            output.append(DEVANAGARI_VOWEL_MARKS[char])
        elif char in DEVANAGARI_SIGNS:
            output.append(DEVANAGARI_SIGNS[char])
        else:
            output.append(char)
        index += 1
    return unicodedata.normalize("NFC", "".join(output))


def transform_script(text: str, source_script: str, target_script: str) -> str:
    """Change only script, leaving whitespace and punctuation positions untouched."""
    if source_script not in SUPPORTED_SCRIPTS or target_script not in SUPPORTED_SCRIPTS:
        raise ValueError(f"unsupported script transform: {source_script} -> {target_script}")
    text = unicodedata.normalize("NFC", text)
    if source_script == target_script:
        return text
    if source_script == "iast":
        return transliterate_iast_to_devanagari(text)
    return transliterate_devanagari_to_iast(text)


def whitespace_signature(text: str) -> tuple[str, ...]:
    """Return whitespace code points in order for script invariance checks."""
    return tuple(char for char in text if char.isspace())


def derive_representation(segment: CanonicalSegment, config: RepresentationConfig) -> RepresentedSegment:
    """Derive a configured view without changing canonical identity or split."""
    scripted = transform_script(segment.canonical_text, segment.canonical_script, config.script)
    represented = apply_spacing(scripted, config.spacing, config.script)
    return RepresentedSegment(
        document_id=segment.document_id,
        segment_id=segment.segment_id,
        split=segment.split,
        text=represented,
        source=segment.source,
        layer=segment.layer,
        script=config.script,
        spacing=config.spacing,
    )


def derive_representations(
    segments: list[CanonicalSegment],
    config: RepresentationConfig,
) -> list[RepresentedSegment]:
    """Derive one representation for every segment without filtering identities."""
    return [derive_representation(segment, config) for segment in segments]

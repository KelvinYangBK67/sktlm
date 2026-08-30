"""Canonical text segments shared by every experimental representation."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace


SUPPORTED_SCRIPTS = {"iast", "devanagari"}


@dataclass(frozen=True, slots=True)
class CanonicalSegment:
    """Stable pre-tokenization identity for one Sanskrit surface segment."""

    document_id: str
    segment_id: str
    split: str
    canonical_text: str
    source: str
    layer: str
    canonical_script: str

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("document_id must not be empty")
        if not self.segment_id:
            raise ValueError("segment_id must not be empty")
        if self.canonical_script not in SUPPORTED_SCRIPTS:
            raise ValueError(f"unsupported canonical script: {self.canonical_script}")
        normalized = unicodedata.normalize("NFC", self.canonical_text)
        if normalized != self.canonical_text:
            object.__setattr__(self, "canonical_text", normalized)


@dataclass(frozen=True, slots=True)
class RepresentedSegment:
    """A deterministic experimental view of a canonical segment."""

    document_id: str
    segment_id: str
    split: str
    text: str
    source: str
    layer: str
    script: str
    spacing: str


def with_canonical_text(segment: CanonicalSegment, text: str) -> CanonicalSegment:
    """Return a segment with corrected canonical text but unchanged identity."""
    return replace(segment, canonical_text=unicodedata.normalize("NFC", text))

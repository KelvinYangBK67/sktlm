"""Orthographic diagnostics defined over tokenizer surface spans."""

from __future__ import annotations

import regex

from sktlm.tokenizers.review import DEPENDENT_VOWELS, SPACE_MARK, VIRAMA
from sktlm.tokenizers.base import Encoding


def clean_token_surface(piece: str) -> str:
    """Remove SentencePiece's visible word-start marker for script checks."""
    return piece.lstrip(SPACE_MARK)


def starts_with_dependent_vowel(piece: str) -> bool:
    clean = clean_token_surface(piece)
    return bool(clean) and clean[0] in DEPENDENT_VOWELS


def ends_with_virama(piece: str) -> bool:
    return clean_token_surface(piece).endswith(VIRAMA)


def grapheme_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return Unicode extended grapheme-cluster character ranges."""
    return tuple(match.span() for match in regex.finditer(r"\X", text))


def internal_token_boundaries(text: str, encoding: Encoding) -> set[int]:
    """Return unique token boundary positions internal to the surface text."""
    boundaries: set[int] = set()
    for start, end in encoding.spans:
        if 0 < start < len(text):
            boundaries.add(start)
        if 0 < end < len(text):
            boundaries.add(end)
    return boundaries


def invalid_grapheme_boundaries(text: str, encoding: Encoding) -> set[int]:
    """Return token boundaries that fall inside an extended grapheme cluster."""
    valid = {0, len(text)}
    for start, end in grapheme_spans(text):
        valid.add(start)
        valid.add(end)
    return internal_token_boundaries(text, encoding) - valid


def invalid_grapheme_boundary_rate(text: str, encoding: Encoding) -> float:
    boundaries = internal_token_boundaries(text, encoding)
    return len(invalid_grapheme_boundaries(text, encoding)) / len(boundaries) if boundaries else 0.0


def grapheme_split_rate(text: str, encoding: Encoding) -> float:
    """Return the fraction of grapheme clusters split by at least one token boundary."""
    clusters = grapheme_spans(text)
    if not clusters:
        return 0.0
    boundaries = internal_token_boundaries(text, encoding)
    split_clusters = sum(1 for start, end in clusters if any(start < point < end for point in boundaries))
    return split_clusters / len(clusters)

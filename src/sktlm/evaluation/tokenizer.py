"""Corpus-level tokenizer diagnostics with explicit scientific scope."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sktlm.evaluation.orthography import (
    ends_with_virama,
    grapheme_spans,
    internal_token_boundaries,
    invalid_grapheme_boundaries,
    starts_with_dependent_vowel,
)
from sktlm.tokenizers.base import Encoding


DEFAULT_SANDHI_PATTERNS = ("ोऽपि", "ोऽ", "ेऽ")


@dataclass(frozen=True, slots=True)
class SandhiFragmentConfig:
    """Illustrative Devanagari patterns, never gold linguistic annotation."""

    patterns: tuple[str, ...] = DEFAULT_SANDHI_PATTERNS
    profile: str = "devanagari_avagraha_fragment_v1"


def _surface_for_token(text: str, encoding: Encoding, index: int) -> str:
    start, end = encoding.spans[index]
    return text[start:end] if end > start else encoding.pieces[index]


def evaluate_tokenizer(
    encoded_texts: Iterable[tuple[str, Encoding]],
    sandhi_config: SandhiFragmentConfig | None = None,
    *,
    script: str,
    unknown_id: int | None,
    unknown_semantics: str,
) -> dict[str, Any]:
    """Evaluate script-neutral metrics and scoped Devanagari diagnostics."""
    if script not in {"iast", "devanagari"}:
        raise ValueError(f"tokenizer diagnostics require a formal script, found {script}")
    sandhi_config = sandhi_config or SandhiFragmentConfig()
    devanagari_applicable = script == "devanagari"
    token_count = 0
    unknown_count = 0
    dependent_count = 0
    virama_count = 0
    invalid_boundaries = 0
    token_boundaries = 0
    split_graphemes = 0
    grapheme_count = 0
    piece_frequencies: Counter[str] = Counter()
    suspect_occurrences = 0
    suspect_pieces: set[str] = set()

    for text, encoding in encoded_texts:
        boundaries = internal_token_boundaries(text, encoding)
        invalid_boundaries += len(invalid_grapheme_boundaries(text, encoding))
        token_boundaries += len(boundaries)
        clusters = grapheme_spans(text)
        grapheme_count += len(clusters)
        split_graphemes += sum(
            1 for start, end in clusters if any(start < point < end for point in boundaries)
        )

        for index, (token_id, piece) in enumerate(zip(encoding.ids, encoding.pieces)):
            surface = _surface_for_token(text, encoding, index)
            check_value = surface or piece
            token_count += 1
            unknown_count += int(unknown_id is not None and token_id == unknown_id)
            piece_frequencies[piece] += 1
            if not devanagari_applicable:
                continue
            dependent_count += int(starts_with_dependent_vowel(check_value))
            virama_count += int(ends_with_virama(check_value))
            if any(pattern in check_value for pattern in sandhi_config.patterns):
                suspect_occurrences += 1
                suspect_pieces.add(piece)

    occupied_types = len(piece_frequencies)
    script_scope = {
        "profile": sandhi_config.profile,
        "scope": "illustrative_script_specific",
        "applicability": "applicable" if devanagari_applicable else "not_applicable",
        "comparable_scripts": ["devanagari"],
        "paired_script_claim_allowed": False,
    }
    return {
        "token_count": token_count,
        "occupied_token_types": occupied_types,
        "unk_count": unknown_count,
        "unk_rate": unknown_count / token_count if token_count else 0.0,
        "unknown_id": unknown_id,
        "unknown_semantics": unknown_semantics,
        "dependent_vowel_start_count": dependent_count if devanagari_applicable else None,
        "dependent_vowel_start_rate": (
            dependent_count / token_count if token_count else 0.0
        ) if devanagari_applicable else None,
        "virama_end_count": virama_count if devanagari_applicable else None,
        "virama_end_rate": (
            virama_count / token_count if token_count else 0.0
        ) if devanagari_applicable else None,
        "grapheme_split_rate": split_graphemes / grapheme_count if grapheme_count else 0.0,
        "invalid_grapheme_boundary_rate": (
            invalid_boundaries / token_boundaries if token_boundaries else 0.0
        ),
        "suspect_token_count": len(suspect_pieces) if devanagari_applicable else None,
        "suspect_token_proportion": (
            len(suspect_pieces) / occupied_types if occupied_types else 0.0
        ) if devanagari_applicable else None,
        "frequency_weighted_suspect_occupancy": (
            suspect_occurrences / token_count if token_count else 0.0
        ) if devanagari_applicable else None,
        "suspect_sandhi_fragment_rate": (
            suspect_occurrences / token_count if token_count else 0.0
        ) if devanagari_applicable else None,
        "sandhi_patterns": list(sandhi_config.patterns) if devanagari_applicable else [],
        "script_specific_diagnostic": script_scope,
    }

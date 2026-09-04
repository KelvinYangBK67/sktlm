"""IAST normalization used by the existing GRETIL preprocessing pipeline."""

from __future__ import annotations

import unicodedata


def _normalize_iast_equivalents(
    text: str,
    *,
    preserve_m0_prime_diphthongs: bool,
) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if char not in {"\u0301", "\u0300"})
    text = unicodedata.normalize("NFC", text)
    replacements = {
        "r̥̄": "ṝ",
        "r̥": "ṛ",
        "l̥̄": "ḹ",
        "l̥": "ḷ",
        "ṁ": "ṃ",
    }
    if not preserve_m0_prime_diphthongs:
        replacements.update({"ē": "e", "ō": "o"})
    for old, new in replacements.items():
        text = text.replace(old, new)
    return unicodedata.normalize("NFC", text)


def normalize_iast_equivalents(text: str) -> str:
    """Normalize accents and equivalent ordinary-IAST spellings."""
    return _normalize_iast_equivalents(text, preserve_m0_prime_diphthongs=False)


def normalize_m0_prime_iast(text: str) -> str:
    """Normalize derived M0-prime IAST while preserving ``ē`` and ``ō``."""
    return _normalize_iast_equivalents(text, preserve_m0_prime_diphthongs=True)

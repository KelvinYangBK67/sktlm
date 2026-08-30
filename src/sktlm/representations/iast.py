"""IAST normalization used by the existing GRETIL preprocessing pipeline."""

from __future__ import annotations

import unicodedata


def normalize_iast_equivalents(text: str) -> str:
    """Normalize accents and equivalent IAST spellings before tokenization."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if char not in {"\u0301", "\u0300"})
    text = unicodedata.normalize("NFC", text)
    replacements = {
        "r̥̄": "ṝ",
        "r̥": "ṛ",
        "l̥̄": "ḹ",
        "l̥": "ḷ",
        "ṁ": "ṃ",
        "ē": "e",
        "ō": "o",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return unicodedata.normalize("NFC", text)

"""Explicit, deterministic spacing conditions."""

from __future__ import annotations

import re
import unicodedata


IAST_CONSONANTS = {
    "kh", "gh", "ch", "jh", "ṭh", "ḍh", "th", "dh", "ph", "bh",
    "k", "g", "ṅ", "h", "c", "j", "ñ", "y", "ś", "ṭ", "ḍ", "ṇ",
    "r", "ṣ", "t", "d", "n", "l", "s", "p", "b", "m", "v",
}
IAST_VOWELS = {"a", "ā", "i", "ī", "u", "ū", "ṛ", "ṝ", "ḷ", "ḹ", "e", "ai", "o", "au"}
IAST_EDGE_TOKENS = tuple(sorted(IAST_CONSONANTS | IAST_VOWELS | {"'"}, key=len, reverse=True))

DEVANAGARI_CONSONANTS = set("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहळ")
DEVANAGARI_INDEPENDENT_VOWELS = set("अआइईउऊऋॠऌॡएऐओऔ")
DEVANAGARI_VOWEL_MARKS = set("ािीुूृॄॢॣेैोौ")
DEVANAGARI_INDEPENDENT_TO_MARK = {
    "अ": "", "आ": "ा", "इ": "ि", "ई": "ी", "उ": "ु", "ऊ": "ू",
    "ऋ": "ृ", "ॠ": "ॄ", "ऌ": "ॢ", "ॡ": "ॣ", "ए": "े", "ऐ": "ै",
    "ओ": "ो", "औ": "ौ",
}
DEVANAGARI_VIRAMA = "्"
DEVANAGARI_AVAGRAHA = "ऽ"

SPACING_CONDITIONS = {
    "observed",
    "surface_word",
    "continuous",
    "lexical_boundary",
    "legacy_joined",
}


def remove_joining_rule_spaces(tokens: list[str]) -> list[str]:
    """Reproduce the historical token-level V+', C+C, and C+V joining."""
    joined: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token != " ":
            joined.append(token)
            index += 1
            continue

        next_index = index + 1
        while next_index < len(tokens) and tokens[next_index] == " ":
            next_index += 1

        previous = joined[-1] if joined else ""
        next_token = tokens[next_index] if next_index < len(tokens) else ""
        should_drop = (
            (previous in IAST_VOWELS and next_token == "'")
            or (previous in IAST_CONSONANTS and next_token in IAST_CONSONANTS)
            or (previous in IAST_CONSONANTS and next_token in IAST_VOWELS)
        )
        if not should_drop:
            joined.append(" ")
        index = next_index
    return joined


def _without_whitespace(text: str) -> str:
    return "".join(character for character in text if not character.isspace())


def _continuous_devanagari_segment(text: str) -> str:
    """Remove lexical whitespace while recomposing Devanagari C+V boundaries."""

    output: list[str] = []
    index = 0

    while index < len(text):
        character = text[index]

        if not character.isspace():
            output.append(character)
            index += 1
            continue

        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1

        # If removing the boundary creates:
        #
        #     consonant + virama + independent vowel
        #
        # recompose it as normal Devanagari orthography:
        #
        #     द् + अ -> द
        #     द् + इ -> दि
        #     द् + उ -> दु
        #
        # This is graphemic recomposition, not sandhi.
        if (
            len(output) >= 2
            and output[-1] == DEVANAGARI_VIRAMA
            and output[-2] in DEVANAGARI_CONSONANTS
            and next_index < len(text)
            and text[next_index] in DEVANAGARI_INDEPENDENT_VOWELS
        ):
            output.pop()  # remove virama
            mark = DEVANAGARI_INDEPENDENT_TO_MARK[text[next_index]]
            if mark:
                output.append(mark)
            next_index += 1  # consume the independent vowel

        index = next_index

    return "".join(output)


def _continuous_line(line: str, script: str) -> str:
    if script == "iast":
        danda_pattern = r"(\|\|?)"
        danda_tokens = {"|", "||"}
    elif script == "devanagari":
        danda_pattern = r"(॥|।)"
        danda_tokens = {"।", "॥"}
    else:
        raise ValueError(f"unsupported script for continuous spacing: {script}")

    parts = re.split(danda_pattern, line)
    cleaned: list[str] = []
    for part in parts:
        if part in danda_tokens:
            cleaned.append(part)
        elif script == "devanagari":
            cleaned.append(_continuous_devanagari_segment(part))
        else:
            cleaned.append(_without_whitespace(part))
    output: list[str] = []
    for index, part in enumerate(cleaned):
        if part not in danda_tokens:
            output.append(part)
            continue

        if script == "iast" and index > 0 and cleaned[index - 1]:
            output.append(" ")
        output.append(part)
        if index + 1 < len(cleaned) and cleaned[index + 1]:
            output.append(" ")
    return "".join(output)


def continuous_spacing(text: str, script: str = "iast") -> str:
    """Remove lexical spaces, preserving LF and script-specific daṇḍa spacing."""
    return "\n".join(_continuous_line(line, script) for line in text.split("\n"))


def devanagari_danda_spacing(text: str) -> str:
    """Normalize only whitespace immediately adjacent to Devanagari daṇḍas."""

    normalized_lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"\s*([।॥])", r"\1", line)
        line = re.sub(r"([।॥])\s*(?=[^।॥\s])", r"\1 ", line)
        line = re.sub(r"([।॥])\s*$", r"\1", line)
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _iast_edge_token(text: str, *, from_end: bool) -> str:
    lowered = text.lower()
    for token in IAST_EDGE_TOKENS:
        if (from_end and lowered.endswith(token)) or (not from_end and lowered.startswith(token)):
            return token
    return ""


def _legacy_join_iast(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\n":
            output.append(char)
            index += 1
            continue
        if not char.isspace():
            output.append(char)
            index += 1
            continue

        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace() and text[next_index] != "\n":
            next_index += 1
        previous = _iast_edge_token("".join(output[-2:]), from_end=True)
        following = _iast_edge_token(text[next_index : next_index + 2], from_end=False)
        should_drop = (
            (previous in IAST_VOWELS and following == "'")
            or (previous in IAST_CONSONANTS and following in IAST_CONSONANTS)
            or (previous in IAST_CONSONANTS and following in IAST_VOWELS)
        )
        if not should_drop:
            output.append(" ")
        index = next_index
    return "".join(output)


def _devanagari_previous_class(text: str) -> str:
    if not text:
        return ""
    last = text[-1]
    if last in DEVANAGARI_INDEPENDENT_VOWELS or last in DEVANAGARI_VOWEL_MARKS:
        return "V"
    if last == DEVANAGARI_VIRAMA and len(text) >= 2 and text[-2] in DEVANAGARI_CONSONANTS:
        return "C"
    if last in DEVANAGARI_CONSONANTS:
        return "V"  # A bare Devanagari consonant carries inherent /a/.
    return ""


def _devanagari_next_class(text: str) -> str:
    if not text:
        return ""
    first = text[0]
    if first == DEVANAGARI_AVAGRAHA:
        return "'"
    if first in DEVANAGARI_CONSONANTS:
        return "C"
    if first in DEVANAGARI_INDEPENDENT_VOWELS:
        return "V"
    return ""


def _legacy_join_devanagari(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\n":
            output.append(char)
            index += 1
            continue
        if not char.isspace():
            output.append(char)
            index += 1
            continue

        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace() and text[next_index] != "\n":
            next_index += 1
        previous = _devanagari_previous_class("".join(output[-2:]))
        following = _devanagari_next_class(text[next_index : next_index + 1])
        should_drop = (
            (previous == "V" and following == "'")
            or (previous == "C" and following == "C")
            or (previous == "C" and following == "V")
        )
        if previous == "C" and following == "V":
            output.pop()  # Remove virāma and compose the following vowel as a mark.
            mark = DEVANAGARI_INDEPENDENT_TO_MARK[text[next_index]]
            if mark:
                output.append(mark)
            next_index += 1
        if not should_drop:
            output.append(" ")
        index = next_index
    return "".join(output)


def legacy_joined_spacing(text: str, script: str) -> str:
    """Apply only the historical joining rule as an explicit condition."""
    if script == "iast":
        return _legacy_join_iast(text)
    if script == "devanagari":
        return _legacy_join_devanagari(text)
    raise ValueError(f"unsupported script for legacy joining: {script}")


def apply_spacing(text: str, condition: str, script: str) -> str:
    """Derive one configured spacing condition without changing script."""
    if condition not in SPACING_CONDITIONS:
        raise ValueError(f"unsupported spacing condition: {condition}")
    text = unicodedata.normalize("NFC", text)
    if condition in {"observed", "surface_word"}:
        spaced = text
    elif condition in {"continuous", "lexical_boundary"}:
        spaced = continuous_spacing(text, script)
    else:
        spaced = legacy_joined_spacing(text, script)

    if script == "devanagari" and condition in {
        "surface_word",
        "legacy_joined",
        "continuous",
    }:
        return devanagari_danda_spacing(spaced)
    return spaced

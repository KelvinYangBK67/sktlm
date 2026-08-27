"""First-pass text normalization for classical Sanskrit data.

The implementation follows ``spec/normalization_v1.md`` conservatively. It is
intended to be readable and easy to revise as real corpus issues appear.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path


DEVANAGARI_START = "\u0900"
DEVANAGARI_END = "\u097f"
DIGITS_TO_DELETE = str.maketrans("", "", "0123456789०१२३४५६७८९")

BRACKETS_AND_QUOTES = str.maketrans("", "", "()[]{}<>\"'`“”‘’«»‹›")
EDITORIAL_MARKS = str.maketrans("", "", "*†‡§#@^~=+\\/")
SENTENCE_FINAL_PUNCTUATION = re.compile(r"[.!?;]+")
HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
DIGIT_CHARS = set("0123456789०१२३४५६७८९")
NUMBERING_ONLY_LINE = re.compile(r"^[0-9०-९।॥.\s]+$")
TRAILER_KEYWORDS = (
    "encoding:",
    "electronic text",
    "file name",
    "text title",
    "latest update",
    "send corrections",
    "questions, comments",
    "from https://",
    "from http://",
    "copyright",
    "all rights reserved",
    "author:",
    "language:",
    "prepared by",
    "encoded by",
    "input by",
    "proofread",
    "updated",
)
TIMESTAMP_LINE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?$")
EMAIL_LIKE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")


def normalize_unicode(text: str) -> str:
    """Normalize all text to NFC."""
    return unicodedata.normalize("NFC", text)


def remove_invisible_chars(text: str) -> str:
    """Remove invisible formatting characters and non-whitespace controls."""
    kept: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if char in "\n\r\t":
            kept.append(char)
        elif category in {"Cf", "Cc", "Cs", "Co", "Cn"}:
            continue
        else:
            kept.append(char)
    return "".join(kept)


def strip_metadata_trailer(text: str) -> str:
    """Strip a trailing footer or metadata block before regular normalization.

    The scan is intentionally one-way from the file end. Obvious metadata lines
    are removed only while they are part of the final trailer block.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = len(lines) - 1
    found_trailer = False

    while index >= 0:
        stripped = lines[index].strip()
        if not stripped:
            index -= 1
            continue
        if is_metadata_trailer_line(stripped):
            found_trailer = True
            index -= 1
            continue
        if found_trailer and is_ascii_note_line(stripped):
            index -= 1
            continue
        break

    if not found_trailer:
        return text
    return "\n".join(lines[: index + 1]).rstrip()


def is_metadata_trailer_line(line: str) -> bool:
    """Return true for obvious footer or metadata lines."""
    lowered = line.lower()
    if line.startswith("%"):
        return True
    if TIMESTAMP_LINE.fullmatch(line):
        return True
    if EMAIL_LIKE.search(line):
        return True
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        return True
    return any(keyword in lowered for keyword in TRAILER_KEYWORDS)


def is_ascii_note_line(line: str) -> bool:
    """Return true for ASCII-heavy note lines after trailer stripping starts."""
    if any(DEVANAGARI_START <= char <= DEVANAGARI_END for char in line):
        return False
    visible = [char for char in line if not char.isspace()]
    if not visible:
        return False
    ascii_count = sum(1 for char in visible if ord(char) < 128)
    letter_count = sum(1 for char in visible if char.isalpha())
    return ascii_count / len(visible) >= 0.8 and letter_count > 0


def normalize_whitespace(text: str) -> str:
    """Normalize newlines, horizontal whitespace, and blank paragraphs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    chars: list[str] = []
    for char in text:
        if char == "\n":
            chars.append(char)
        elif char.isspace():
            chars.append(" ")
        else:
            chars.append(char)

    text = "".join(chars)
    text = HORIZONTAL_SPACE.sub(" ", text)
    lines = [line.strip(" ") for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def remove_editorial_noise(text: str) -> str:
    """Remove obvious layout residue and first-pass editorial markers.

    This is deliberately conservative: it drops standalone page-like lines,
    common English page/header/footer labels, bracket and quote characters, and
    simple critical-apparatus symbols. It does not try to infer complex layout.
    """
    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if re.fullmatch(r"[-–— ]*(?:page|p\.)?\s*[0-9०-९ivxlcdmIVXLCDM]+[-–— ]*", stripped):
            continue
        if re.fullmatch(r"(?:page|header|footer)\s+[0-9०-९ivxlcdmIVXLCDM]*", stripped, re.IGNORECASE):
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = text.translate(BRACKETS_AND_QUOTES)
    text = text.translate(EDITORIAL_MARKS)
    text = re.sub(r"(?<=\S)[¹²³⁴⁵⁶⁷⁸⁹⁰]+", "", text)
    return text


def remove_numbering_noise(text: str) -> str:
    """Remove numeric labels while preserving danda boundary marks."""
    text = normalize_ascii_danda(text)
    text = re.sub(r"॥\s*[0-9०-९]+\s*॥", "॥", text)
    text = re.sub(r"(?<=\S)[¹²³⁴⁵⁶⁷⁸⁹⁰]+", "", text)

    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and any(char in DIGIT_CHARS for char in stripped) and NUMBERING_ONLY_LINE.fullmatch(stripped):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def normalize_punctuation(text: str) -> str:
    """Normalize Sanskrit punctuation and selected Western punctuation."""
    text = normalize_ascii_danda(text)
    text = text.replace(",", "").replace(":", "")
    text = SENTENCE_FINAL_PUNCTUATION.sub("।", text)

    text = normalize_double_danda(text)

    text = re.sub(r" *(?<!।)।(?!।)[ \t\f\v]*(?=\n|$)", "।", text)
    text = re.sub(r" *(?<!।)।(?!।)[ \t\f\v]*(?=\S)", "। ", text)
    return text


def remove_standalone_danda_lines(text: str) -> str:
    """Remove lines that contain only a single danda or double danda."""
    kept: list[str] = []
    for line in text.split("\n"):
        if line.strip() in {"।", "॥"}:
            continue
        kept.append(line)
    return "\n".join(kept)


def normalize_ascii_danda(text: str) -> str:
    """Map ASCII danda notation to Devanagari danda notation."""
    text = text.replace("||", "॥")
    return text.replace("|", "।")


def normalize_double_danda(text: str) -> str:
    """Normalize double danda spacing and prevent same-line body continuation."""
    text = re.sub(r" *॥[ \t\f\v]*(?=\n|$)", "॥", text)
    text = re.sub(r"॥[ \t\f\v]+॥", "॥", text)
    return re.sub(r" *॥[ \t\f\v]*(?=\S)", "॥\n", text)


def remove_digits(text: str) -> str:
    """Delete Arabic and Devanagari digits."""
    return text.translate(DIGITS_TO_DELETE)


def filter_non_devanagari_noise(text: str) -> str:
    """Keep Devanagari text, ordinary spaces, and newlines; drop other noise."""
    kept: list[str] = []
    for char in text:
        if char in {" ", "\n"} or DEVANAGARI_START <= char <= DEVANAGARI_END:
            kept.append(char)
    return "".join(kept)


def normalize_text(text: str) -> str:
    """Apply the first-pass normalization pipeline."""
    text = strip_metadata_trailer(text)
    text = normalize_unicode(text)
    text = remove_invisible_chars(text)
    text = normalize_whitespace(text)
    text = remove_editorial_noise(text)
    text = remove_numbering_noise(text)
    text = remove_digits(text)
    text = normalize_punctuation(text)
    text = filter_non_devanagari_noise(text)
    text = normalize_whitespace(text)
    text = normalize_punctuation(text)
    text = remove_standalone_danda_lines(text)
    text = normalize_whitespace(text)
    return text


def parse_args() -> argparse.Namespace:
    """Parse a minimal CLI for file-based or stdin/stdout normalization."""
    parser = argparse.ArgumentParser(description="Normalize Sanskrit text.")
    parser.add_argument("--input", type=Path, help="Input text file. Defaults to stdin.")
    parser.add_argument("--output", type=Path, help="Output text file. Defaults to stdout.")
    return parser.parse_args()


def main() -> None:
    """Run normalization from stdin/stdout or --input/--output paths."""
    args = parse_args()

    if args.input:
        text = args.input.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    normalized = normalize_text(text)

    if args.output:
        args.output.write_text(normalized, encoding="utf-8")
    else:
        sys.stdout.buffer.write(normalized.encode("utf-8"))


if __name__ == "__main__":
    main()

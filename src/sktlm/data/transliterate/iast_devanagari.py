"""Mechanically convert IAST script to Devanagari without changing boundaries.

This is a small rule-based transliterator for the intermediate
data/processed/gretil_raw corpus. It follows notes/IAST_to_Devanagari.txt and
intentionally does not perform spacing or lexical-boundary manipulation.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

from sktlm.data.normalize.iast import normalize_iast_equivalents
from sktlm.data.representations.spacing import remove_joining_rule_spaces


CONSONANTS = {
    "kh": "ख",
    "gh": "घ",
    "ch": "छ",
    "jh": "झ",
    "ṭh": "ठ",
    "ḍh": "ढ",
    "th": "थ",
    "dh": "ध",
    "ph": "फ",
    "bh": "भ",
    "k": "क",
    "g": "ग",
    "ṅ": "ङ",
    "h": "ह",
    "c": "च",
    "j": "ज",
    "ñ": "ञ",
    "y": "य",
    "ś": "श",
    "ṭ": "ट",
    "ḍ": "ड",
    "ṇ": "ण",
    "r": "र",
    "ṣ": "ष",
    "t": "त",
    "d": "द",
    "n": "न",
    "l": "ल",
    "s": "स",
    "p": "प",
    "b": "ब",
    "m": "म",
    "v": "व",
}

INDEPENDENT_VOWELS = {
    "a": "अ",
    "ā": "आ",
    "i": "इ",
    "ī": "ई",
    "u": "उ",
    "ū": "ऊ",
    "ṛ": "ऋ",
    "ṝ": "ॠ",
    "ḷ": "ऌ",
    "ḹ": "ॡ",
    "e": "ए",
    "ai": "ऐ",
    "o": "ओ",
    "au": "औ",
}

VOWEL_MARKS = {
    "a": "",
    "ā": "ा",
    "i": "ि",
    "ī": "ी",
    "u": "ु",
    "ū": "ू",
    "ṛ": "ृ",
    "ṝ": "ॄ",
    "ḷ": "ॢ",
    "ḹ": "ॣ",
    "e": "े",
    "ai": "ै",
    "o": "ो",
    "au": "ौ",
}

SIGNS = {
    "ṃ": "ं",
    "ḥ": "ः",
    "'": "ऽ",
    "|": "।",
    "||": "॥",
    "ॐ": "ॐ",
}

VIRAMA = "्"
LONG_TOKENS = ("ṭh", "ḍh", "kh", "gh", "ch", "jh", "th", "dh", "ph", "bh", "ai", "au", "||")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Convert cleaned IAST text to Devanagari.")
    parser.add_argument("--input", type=Path, help="Single input .txt file.")
    parser.add_argument("--output", type=Path, help="Single output .txt file.")
    parser.add_argument("--input-dir", type=Path, help="Input directory for batch conversion.")
    parser.add_argument("--output-dir", type=Path, help="Output directory for batch conversion.")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/_reports/gretil_devanagari_summary.txt"),
        help="Batch conversion report path.",
    )
    return parser.parse_args()


def tokenize_iast(text: str) -> list[str]:
    """Split IAST with longest-match priority while preserving every other character."""
    text = normalize_iast_equivalents(text)
    text = re.sub(r"(?<!\S)oṃ(?!\S)", "ॐ", text)
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            tokens.append(char)
            index += 1
            continue
        lowered = text[index : index + 2].lower()
        if lowered in LONG_TOKENS:
            tokens.append(lowered)
            index += 2
            continue
        lowered_char = char.lower()
        if lowered_char in CONSONANTS or lowered_char in INDEPENDENT_VOWELS or lowered_char in SIGNS:
            tokens.append(char if char == "ॐ" else lowered_char)
        else:
            tokens.append(char)
        index += 1
    return tokens


def transliterate_tokens(tokens: list[str]) -> str:
    """Convert token script while leaving whitespace and unsupported symbols in place."""
    output: list[str] = []
    previous_was_open_consonant = False

    for index, token in enumerate(tokens):
        if token in CONSONANTS:
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
            output.append(CONSONANTS[token])
            previous_was_open_consonant = next_token in INDEPENDENT_VOWELS
            if not previous_was_open_consonant:
                output.append(VIRAMA)
            continue

        if token in INDEPENDENT_VOWELS:
            if previous_was_open_consonant:
                output.append(VOWEL_MARKS[token])
            else:
                output.append(INDEPENDENT_VOWELS[token])
            previous_was_open_consonant = False
            continue

        if token in SIGNS:
            output.append(SIGNS[token])
        else:
            output.append(token)
        previous_was_open_consonant = False

    return "".join(output)


def normalize_devanagari_text(text: str) -> str:
    """Apply light post-normalization from the IAST conversion note."""
    lines: list[str] = []
    blank_count = 0
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(raw_line.split())
        line = line.lstrip(" ।,")
        line = re.sub(r"\s+,", ",", line)
        line = line.replace(" ।", "।").replace(" ॥", "॥")
        line = line.replace("।", "। ").replace("॥", "॥ ")
        line = " ".join(line.split())
        line = line.replace(" ।", "।").replace(" ॥", "॥")

        if not line:
            blank_count += 1
            continue
        if lines and blank_count >= 1:
            lines.append("")
        lines.append(line)
        blank_count = 0

    return unicodedata.normalize("NFC", "\n".join(lines).strip())


def transliterate_iast_to_devanagari(text: str) -> str:
    """Convert only script representation, preserving whitespace and line boundaries."""
    return unicodedata.normalize("NFC", transliterate_tokens(tokenize_iast(text)))


def iast_to_devanagari(text: str) -> str:
    """Compatibility alias for clean script-only transliteration."""
    return transliterate_iast_to_devanagari(text)


def main() -> None:
    """Run conversion for one file or a directory tree."""
    args = parse_args()

    if args.input_dir or args.output_dir:
        if not args.input_dir or not args.output_dir:
            raise SystemExit("--input-dir and --output-dir must be used together.")
        batch_convert(args.input_dir, args.output_dir, args.report)
        return

    if not args.input or not args.output:
        raise SystemExit("Use --input/--output for one file, or --input-dir/--output-dir for a batch.")

    converted = convert_file(args.input, args.output)
    print(f"Wrote: {args.output}")
    print(f"Characters: {len(converted)}")
    print(f"Lines: {len(converted.splitlines()) if converted else 0}")


def convert_file(input_path: Path, output_path: Path) -> str:
    """Convert one IAST file and write the Devanagari result."""
    text = input_path.read_text(encoding="utf-8")
    converted = iast_to_devanagari(text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(converted, encoding="utf-8")
    return converted


def batch_convert(input_dir: Path, output_dir: Path, report_path: Path) -> None:
    """Convert a directory tree of cleaned IAST files."""
    input_files = sorted(path for path in input_dir.rglob("*.txt") if path.is_file())
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    successes: list[tuple[Path, int, int]] = []
    failures: list[tuple[Path, str]] = []
    for input_path in input_files:
        relative = input_path.relative_to(input_dir)
        output_path = output_dir / relative
        try:
            converted = convert_file(input_path, output_path)
            successes.append((relative, len(converted), len(converted.splitlines()) if converted else 0))
        except Exception as exc:  # noqa: BLE001 - keep the batch moving.
            failures.append((relative, f"{type(exc).__name__}: {exc}"))

    lines = [
        "GRETIL IAST to Devanagari Summary",
        "",
        f"Input .txt files: {len(input_files)}",
        f"Successful files: {len(successes)}",
        f"Failed files: {len(failures)}",
        f"Total output characters: {sum(item[1] for item in successes)}",
        f"Total output lines: {sum(item[2] for item in successes)}",
        "",
        "Shortest outputs:",
    ]
    for path, chars, line_count in sorted(successes, key=lambda item: item[1])[:10]:
        lines.append(f"- {path}: {chars} chars, {line_count} lines")
    lines.extend(["", "Longest outputs:"])
    for path, chars, line_count in sorted(successes, key=lambda item: item[1], reverse=True)[:10]:
        lines.append(f"- {path}: {chars} chars, {line_count} lines")
    lines.extend(["", "Failures:"])
    if failures:
        for path, error in failures:
            lines.append(f"- {path}: {error}")
    else:
        lines.append("- none")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Input files: {len(input_files)}")
    print(f"Successful files: {len(successes)}")
    print(f"Failed files: {len(failures)}")
    print(f"Output directory: {output_dir}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()

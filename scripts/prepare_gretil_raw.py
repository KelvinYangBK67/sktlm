"""Prepare raw GRETIL HTML files as plain IAST-ish text.

This is intentionally separate from tokenizer.normalize because GRETIL input is
not Devanagari yet. The output is an intermediate raw text corpus for later
transliteration/normalization work.
"""

from __future__ import annotations

import argparse
import html
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path


HR_MARK = "__GRETIL_HR__"
BLOCK_TAGS = {"br", "p", "div", "tr", "li", "blockquote"}
SKIP_TAGS = {"head", "style", "script", "table"}
TRAILER_PATTERNS = (
    "this gretil",
    "copyright",
    "terms of usage",
    "text converted",
    "comprehensive list",
    "utf-8",
    "description:",
    "multibyte sequence",
)

FORBIDDEN_ASCII = set("qwfzx")
VOWEL_CHARS = set("aāiīuūṛṝḷḹeo")
CONSONANT_TOKENS = {
    "k",
    "g",
    "ṅ",
    "h",
    "c",
    "j",
    "ñ",
    "y",
    "ś",
    "ṭ",
    "ḍ",
    "ṇ",
    "r",
    "ṣ",
    "t",
    "d",
    "n",
    "l",
    "s",
    "p",
    "b",
    "m",
    "v",
}


def normalize_iast_equivalents(text: str) -> str:
    """Normalize accents and equivalent IAST spellings before cleaning."""
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


class GretilHTMLToText(HTMLParser):
    """Small HTML-to-text parser that preserves line breaks and HR markers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "hr":
            self.parts.append(f"\n{HR_MARK}\n")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in {"p", "div", "tr", "li", "blockquote"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        """Return parsed text."""
        return "".join(self.parts)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Convert GRETIL .htm files to raw .txt.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw/gretil"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/gretil_raw"))
    parser.add_argument("--report", type=Path, default=Path("data/_reports/gretil_raw_summary.txt"))
    parser.add_argument("--skip-existing", action="store_true", help="Reuse existing output files.")
    return parser.parse_args()


def should_skip_input(path: Path) -> bool:
    """Return true for known non-corpus GRETIL inputs."""
    return path.name.lower().startswith("rvpp")


def html_to_text(raw_html: str) -> str:
    """Convert one HTML document to rough text."""
    parser = GretilHTMLToText()
    parser.feed(raw_html)
    parser.close()
    return html.unescape(parser.text())


def strip_header(text: str) -> str:
    """Remove GRETIL header/metadata, conservatively using HR boundaries."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    tei_text_start = find_tei_text_start(lines)
    if tei_text_start is not None:
        return "\n".join(lines[tei_text_start:])
    hr_indexes = [index for index, line in enumerate(lines) if line == HR_MARK]
    if hr_indexes:
        # Usually the second HR ends the GRETIL notice/encoding table. If there
        # is only one HR, it is still a better body boundary than the document top.
        start = hr_indexes[1] + 1 if len(hr_indexes) >= 2 else hr_indexes[0] + 1
        lines = lines[start:]
        body_marker = find_body_marker(lines)
        if body_marker is not None:
            lines = lines[body_marker:]
        lines = strip_leading_editorial_notes(lines)
    else:
        lines = strip_leading_metadata_lines(lines)
        lines = strip_leading_editorial_notes(lines)
    return "\n".join(lines)


def find_body_marker(lines: list[str]) -> int | None:
    """Find an explicit body marker after edition notes."""
    for index, line in enumerate(lines[:200]):
        if line.strip() in {"###", "TEXT", "Text"}:
            return index + 1
    return None


def find_tei_text_start(lines: list[str]) -> int | None:
    """Find the start of TEI HTML body text after frontmatter/header sections."""
    first_nonempty = next((line.lower() for line in lines if line), "")
    leading_text = "\n".join(lines[:80]).lower()
    if (
        first_nonempty not in {"frontmatter", "header"}
        and "frontmatter" not in leading_text
        and "header" not in leading_text
        and "contents of" not in leading_text
    ):
        return None
    for index, line in enumerate(lines):
        if line.strip().lower() in {"text", "body"}:
            return index + 1
    return None


def strip_leading_metadata_lines(lines: list[str]) -> list[str]:
    """Fallback for files without HR markers."""
    start = 0
    for index, line in enumerate(lines):
        lowered = line.lower()
        if not line:
            continue
        if any(pattern in lowered for pattern in TRAILER_PATTERNS):
            start = index + 1
            continue
        if looks_like_text_line(line):
            start = index
            break
    return lines[start:]


def strip_leading_editorial_notes(lines: list[str]) -> list[str]:
    """Drop English explanatory notes that appear between header and body."""
    start = 0
    saw_note = False
    for index, line in enumerate(lines[:160]):
        stripped = line.strip()
        if not stripped:
            continue
        if looks_like_body_start(stripped):
            start = index
            break
        if looks_like_english_note(stripped):
            saw_note = True
            start = index + 1
            continue
        if saw_note:
            start = index + 1
            continue
        break
    return lines[start:]


def looks_like_body_start(line: str) -> bool:
    """Return true for likely Sanskrit/IAST body starts."""
    if "|" in line or "/" in line:
        return True
    return bool(re.search(r"[āīūṛṝḷḹṅñṭḍṇśṣṃḥ]", line))


def looks_like_english_note(line: str) -> bool:
    """Return true for leading English editorial explanation lines."""
    lowered = line.lower()
    note_words = (
        "there are",
        "numbering",
        "material",
        "organized",
        "those numbers",
        "editions",
        "edition",
        "texts without",
        "alternative",
        "attempt",
        "readings",
        "input by",
        "edited",
        "symbols",
        "letters",
        "manuscript",
        "accent marks",
        "no match",
        "columns",
        "beginning with",
        "underlined",
        "published text",
        "double svarita",
        "parallel vertical",
        "compare",
        "unusual accents",
        "published",
        "variant",
        "translated",
        "english",
        "accent",
        "irregular",
        "tempted",
        "change",
        "hymn",
        "intended",
        "presumably",
        "recitation",
        "guide",
        "corrected",
        "unintelligible",
        "goswami",
        "mayapur",
    )
    if any(word in lowered for word in note_words) or lowered.startswith(("-", "ed ")):
        return True
    if re.search(r"[āīūṛṝḷḹṅñṭḍṇśṣṃḥ|/]", line):
        return False
    return False


def strip_trailing_metadata(text: str) -> str:
    """Remove trailing HTML/GRETIL residue if present."""
    kept: list[str] = []
    for line in text.split("\n"):
        lowered = line.lower().strip()
        if lowered in {"", HR_MARK.lower()}:
            kept.append(line)
            continue
        if any(pattern in lowered for pattern in TRAILER_PATTERNS):
            continue
        if lowered.startswith(("http://", "https://", "www.")):
            continue
        kept.append(line)
    return "\n".join(kept)


def looks_like_text_line(line: str) -> bool:
    """Heuristic for IAST/Sanskrit-ish body lines."""
    if len(line) < 3:
        return False
    if re.search(r"[āīūṛṝḷḹṅñṭḍṇśṣṃḥĀĪŪṚṜḶḸṄÑṬḌṆŚṢṂḤ]", line):
        return True
    return bool(re.search(r"\b[a-z]{3,}\b", line))


def normalize_slash_danda(line: str) -> str:
    """Map GRETIL slash danda markers to ASCII danda markers."""
    line = re.sub(r"\s*//\s*", " || ", line)
    line = re.sub(r"\s*/\s*", " | ", line)
    return line


def remove_numbering(line: str) -> str:
    """Remove common GRETIL paragraph/verse numbering."""
    line = re.sub(r"\([^)]*[0-9][^)]*\)", "", line)
    line = re.sub(r"\([^)]*\)", "", line)
    line = re.sub(r"\[[^\]]*[0-9][^\]]*\]", "", line)
    line = re.sub(r"\[[^\]]*\]", "", line)
    line = re.sub(r"\b[A-Za-z][A-Za-z0-9]*_[0-9][A-Za-z0-9_.-]*\b", "", line)
    line = re.sub(r"\S*_[0-9]\S*", "", line)
    line = re.sub(r"^\s*[0-9]+(?:[.:][0-9]+)*(?:[a-z])?[\).:]?\s*", "", line)
    line = re.sub(r"\s+[0-9]+(?:[.:][0-9]+)*(?:[a-z])?\s*$", "", line)
    line = re.sub(r"(?<=\|\|)\s*[0-9]+(?:[.:][0-9]+)*\s*(?=\|\|)", "", line)
    line = re.sub(r"(?<=\|)\s*[0-9]+(?:[.:][0-9]+)*\s*(?=\|)", "", line)
    line = re.sub(r"\b[0-9]+(?:[.:][0-9]+)*(?:[a-z])?\b", "", line)
    line = re.sub(r"[0-9]+", "", line)
    line = re.sub(r"(?<=\s)[.:]+(?=\s|$)", "", line)
    return line


def remove_edition_references(line: str) -> str:
    """Remove edition/page labels that are not body text."""
    line = re.sub(r"\(\s*ed\.?\s+Speyer[^)]*\)", "", line, flags=re.IGNORECASE)
    line = re.sub(
        r"^\s*-+\s*Vaidya\s*,?\s*p\.?\s*[0-9.:-]*[A-Za-z]?\s*-+\s*",
        "",
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(r"^\s*Vaidya\s*,?\s*p\.?\s*(?:[0-9.:-]+[A-Za-z]?)?\s*", "", line, flags=re.IGNORECASE)
    line = re.sub(r"\s*\|\s*ed\s+Speyer\s*,?\s*vol\s+[IVXLCDM]+\s*$", "", line, flags=re.IGNORECASE)
    if re.fullmatch(r"(?:Vaidya|Speyer|ed\s+Speyer|Ed|Ms|Ch|J)\s*,?\s*(?:p|vol)?\.?\s*", line.strip(), re.IGNORECASE):
        return ""
    return line


def is_editorial_noise_line(line: str) -> bool:
    """Detect English editorial/commentary notes outside the Sanskrit body."""
    stripped = line.strip()
    if not stripped:
        return False
    if looks_like_english_note(stripped):
        return True
    lowered = stripped.lower()
    if re.search(r"\b(ed|edition|edited|reads?|restored|according to|cf|compare|pp|text|rv|vs|ts|ms|ks|śb|tb|ta)\b", lowered):
        latin_words = re.findall(r"\b[a-zA-Z]{3,}\b", stripped)
        iast_marks = re.findall(r"[āīūṛṝḷḹṅñṭḍṇśṣṃḥ]", stripped)
        uppercase_words = re.findall(r"\b\w*[A-Z]\w*\b", stripped)
        forbidden_words = re.findall(r"\b\w*[qwfzxQWFZX]\w*\b", stripped)
        return (
            len(latin_words) >= 3
            or bool(uppercase_words)
            or bool(forbidden_words)
            or len(latin_words) > len(iast_marks) * 2
        )
    return False


def is_reference_only_line(line: str) -> bool:
    """Detect manuscript/page/chapter reference lines before digit stripping."""
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 160:
        return False
    if not re.search(r"\d", stripped):
        return False
    rough = re.sub(r"[()\[\];,.:_-]", " ", stripped)
    tokens = rough.split()
    if not tokens:
        return True
    sigla = {"ms", "j", "ch", "p", "fol", "r", "v", "a", "b", "c"}
    for token in tokens:
        lowered = token.lower()
        if lowered in sigla:
            continue
        if re.fullmatch(r"[ivxlcdm]+", lowered):
            continue
        if re.fullmatch(r"[a-z0-9]+", lowered) and any(char.isdigit() for char in lowered):
            continue
        return False
    return True


def is_iast_char(char: str) -> bool:
    """Return true for Latin/IAST letters and combining accent marks."""
    if "A" <= char <= "Z" or "a" <= char <= "z":
        return True
    category = unicodedata.category(char)
    if category.startswith("M"):
        return True
    codepoint = ord(char)
    return 0x00C0 <= codepoint <= 0x024F or 0x1E00 <= codepoint <= 0x1EFF


def filter_iast_and_danda(text: str) -> str:
    """Keep IAST-ish letters, whitespace, danda markers, commas, and apostrophes."""
    kept: list[str] = []
    for char in text:
        if char in {" ", "\n", "|", ",", "'", "’"} or is_iast_char(char):
            kept.append(char)
        else:
            kept.append(" ")
    return "".join(kept)


def remove_noise_words(line: str) -> str:
    """Remove word-level noise defined in the GRETIL IAST spec."""
    words = line.split()
    noise_flags: list[bool] = []
    for word in words:
        bare = word.strip(",|'’")
        noise_flags.append(is_noise_word(bare))

    kept: list[str] = []
    for index, word in enumerate(words):
        if noise_flags[index]:
            continue
        bare = word.strip(",|'’")
        neighbor_is_noise = (index > 0 and noise_flags[index - 1]) or (
            index + 1 < len(noise_flags) and noise_flags[index + 1]
        )
        if neighbor_is_noise and is_short_ascii_fragment(bare):
            continue
        kept.append(word)
    return " ".join(kept)


def is_noise_word(word: str) -> bool:
    """Return true for word-level noise from note section 6."""
    if not word:
        return False
    if any("A" <= char <= "Z" for char in word):
        return True
    if any(char.lower() in FORBIDDEN_ASCII for char in word):
        return True
    if has_bad_vowel_run(word):
        return True
    if len(word) == 1 and word in CONSONANT_TOKENS:
        return True
    return False


def has_bad_vowel_run(word: str) -> bool:
    """Detect consecutive vowels except the valid diphthongs ai and au."""
    lowered = word.lower()
    for index, char in enumerate(lowered[:-1]):
        next_char = lowered[index + 1]
        if char in VOWEL_CHARS and next_char in VOWEL_CHARS:
            if char == "a" and next_char in {"i", "u"}:
                continue
            return True
    return False


def is_short_ascii_fragment(word: str) -> bool:
    """Return true for short English leftovers next to known noise words."""
    return bool(re.fullmatch(r"[a-z]{1,3}", word.lower()))


def normalize_danda_runs(line: str) -> str:
    """Collapse duplicate ASCII danda markers after numbering/noise removal."""
    previous = None
    while previous != line:
        previous = line
        line = re.sub(r"\|\|\s*,+\s*\|\|", "||", line)
        line = re.sub(r"\|\|\s+\|\|", "||", line)
        line = re.sub(r"(?:\|\|\s*){2,}", "||", line)
        line = re.sub(r"\|\s*,+\s*\|", "|", line)
        line = re.sub(r"\|\s+\|", "|", line)
    return line.strip()


def clean_body_text(text: str) -> str:
    """Clean body text while preserving IAST for later processing."""
    text = strip_trailing_metadata(text)
    text = normalize_iast_equivalents(text)
    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or line == HR_MARK:
            cleaned.append("")
            continue
        line = re.sub(r"<[^>]+>", " ", line)
        if is_editorial_noise_line(line):
            cleaned.append("")
            continue
        if is_reference_only_line(line):
            cleaned.append("")
            continue
        line = normalize_slash_danda(line)
        line = remove_numbering(line)
        line = remove_edition_references(line)
        line = filter_iast_and_danda(line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        line = remove_noise_words(line)
        line = re.sub(r"\s+,", ",", line)
        line = re.sub(r"\s+\|", " |", line)
        line = re.sub(r"\s+\|\|", " ||", line)
        line = re.sub(r"\|{3,}", "||", line)
        line = normalize_danda_runs(line)
        if line and line not in {"|", "||", ",", ".", ";", ":"}:
            cleaned.append(line)
        else:
            cleaned.append("")

    return normalize_body_newlines(cleaned)


def normalize_body_newlines(lines: list[str]) -> str:
    """Preserve line breaks, keeping only clear paragraph blank runs."""
    output: list[str] = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            continue
        if output and blank_count >= 2:
            output.append("")
        output.append(line)
        blank_count = 0
    return "\n".join(output).strip()


def convert_file(input_path: Path) -> str:
    """Convert one GRETIL HTML file to cleaned raw text."""
    raw_html = input_path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(raw_html)
    text = strip_header(text)
    return clean_body_text(text)


def main() -> None:
    """Batch convert all .htm files."""
    args = parse_args()
    input_files = sorted(
        path for path in args.input_dir.rglob("*.htm") if path.is_file() and not should_skip_input(path)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    successes: list[tuple[Path, int, int]] = []
    failures: list[tuple[Path, str]] = []
    for input_path in input_files:
        relative = input_path.relative_to(args.input_dir)
        output_path = (args.output_dir / relative).with_suffix(".txt")
        try:
            if args.skip_existing and output_path.exists():
                cleaned = output_path.read_text(encoding="utf-8")
            else:
                cleaned = convert_file(input_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(cleaned, encoding="utf-8")
            successes.append((relative.with_suffix(".txt"), len(cleaned), len(cleaned.splitlines()) if cleaned else 0))
        except Exception as exc:  # noqa: BLE001 - keep batch conversion running.
            failures.append((relative, f"{type(exc).__name__}: {exc}"))

    lines = [
        "GRETIL Raw Conversion Summary",
        "",
        f"Input .htm files: {len(input_files)}",
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

    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Input files: {len(input_files)}")
    print(f"Successful files: {len(successes)}")
    print(f"Failed files: {len(failures)}")
    print(f"Output directory: {args.output_dir}")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()

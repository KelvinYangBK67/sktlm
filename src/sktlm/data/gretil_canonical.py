"""Build the formal whitelist-only GRETIL canonical IAST corpus.

This module removes source infrastructure, not Sanskrit linguistic structure.
It intentionally has no dependency on transliteration or experimental spacing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any

from sktlm.data.splits import DEFAULT_SPLIT_SEED, assign_split, make_document_id


HR_MARK = "__SKTLM_GRETIL_HR__"
SKIP_TAGS = {"head", "style", "script", "nav"}
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl",
    "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "li", "main", "p", "pre", "section", "tr",
}
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
HORIZONTAL_SPACE_RE = re.compile(r"[^\S\n]+")
INVALID_HORIZONTAL_SPACE_RE = re.compile(r"\t| {2,}")
DECORATION_ONLY_RE = re.compile(r"^\s*[*=_~-]{3,}\s*$")
DECORATED_TITLE_RE = re.compile(
    r"^\s*[*=_~-]{3,}\s+(?P<body>.*?)\s+[*=_~-]{3,}\s*$"
)
BRACKETED_NUMBER_RE = re.compile(
    r"[\[(<]\s*\d+(?:[a-z]{0,2})?\s*[\])>]", re.IGNORECASE
)
STANDALONE_NUMBER_RE = re.compile(
    r"(?<!\S)\d+(?:[.,:]\d+)*(?:[a-z]{0,2})?(?!\S)", re.IGNORECASE
)
PREFIX_PATTERNS = (
    re.compile(r"^\s*[\[(]\s*(?:[A-Za-z]{1,12}[_ ]+)?\d[\w.,:/*=@-]*\s*[\])]\s*"),
    re.compile(r"^\s*[A-Za-z]{1,12}[_ ]\d[\w.,:/*=@-]*(?:/|\.)?\s+"),
    re.compile(r"^\s*\d[\dA-Za-z.,:*_=@-]*(?:/|\.)?\s+"),
    re.compile(r"^\s*\d+[a-z]{0,2}[.)]\s+", re.IGNORECASE),
)
VERSE_NUMBER_RE = re.compile(
    r"(?<!\|)(\|{1,3})\s*\d+(?:[.,:]\d+)*(?:[a-z]{0,2})?\s*(\|{1,3})\s*$",
    re.IGNORECASE,
)
END_MARKER_RE = re.compile(r"^\s*[=*_~-]*\s*end\s+of\b.*?[=*_~-]*\s*$", re.IGNORECASE)
SIGLUM_CORE = r"[^\W\d_][\w]{0,20}_\d[\w.,:\[\]/*=@-]*"
DANDA_SIGLUM_RE = re.compile(
    rf"(?P<danda>\|{{1,2}})\s*\(?{SIGLUM_CORE}\)?\s*\|{{1,2}}",
    re.IGNORECASE,
)
TRAILING_REDUNDANT_DANDA_RE = re.compile(r"(?<=\|)\s+\|{1,2}\s*$")
SIGLUM_RE = re.compile(rf"(?<!\w)\(?{SIGLUM_CORE}\)?(?!\w)", re.IGNORECASE)
PREFIX_SIGLUM_RE = re.compile(rf"^\s*\(?{SIGLUM_CORE}\)?(?:[|/.])?\s*", re.IGNORECASE)
SUFFIX_SIGLUM_RE = re.compile(rf"\s*\(?{SIGLUM_CORE}\)?\s*$", re.IGNORECASE)
COMPACT_PREFIX_RE = re.compile(
    r"^\s*(?:KAZ|div)\d[\dA-Za-z.,:\[\]_-]*(?:[|/.])?\s*", re.IGNORECASE
)
COLOPHON_PREFIX_RE = re.compile(
    r"^\s*\([^\W\d_][\w]{0,20}_(?:col|end|title)\)\s*", re.IGNORECASE
)
BOILERPLATE_SUBSTRINGS = (
    "this gretil text file is for reference purposes only",
    "copyright and terms of usage",
    "text converted to unicode",
    "comprehensive list of gretil encodings",
    "for further information see",
)
ACCENT_MARKS = {"\u0300", "\u0301", "\u0302", "\u030d", "\u030e", "\u032d", "\u0331"}
ALLOWED_COMBINING_MARKS = ACCENT_MARKS | {
    "\u0303", "\u0304", "\u0306", "\u0307", "\u0308", "\u0310", "\u0323",
    "\u0325", "\u0327", "\u0332",
}
ACCENTED_VOWELS = set(
    "\u00e0\u00e1\u00e2\u00e8\u00e9\u00ea\u00ec\u00ed\u00ee\u00f2\u00f3\u00f4\u00f9\u00fa\u00fb"
    "\u00c0\u00c1\u00c2\u00c8\u00c9\u00ca\u00cc\u00cd\u00ce\u00d2\u00d3\u00d4\u00d9\u00da\u00db"
)
ALLOWED_PUNCTUATION = set(
    " '\"|,.;:!?-()[]{}<>_*@^~=+\\/%$&#`\u00b4\u00a7\u2020\u2021\u2026\u00b7\u2013\u2014"
)
ENCODING_EQUIVALENTS = {
    "\u1e41": "\u1e43",
    "\u2019": "'",
    "\u2018": "'",
    "\u02bc": "'",
    "\uff07": "'",
    "\u201c": "\"",
    "\u201d": "\"",
    "\u2010": "-",
    "\u2011": "-",
    "\u2212": "-",
    "\u00a0": " ",
    "\u2007": " ",
    "\u202f": " ",
    "\u0964": "|",
    "\u0965": "||",
}
LAYER_NAMES = {
    "1_veda": "veda",
    "2_epic": "epic",
    "3_purana": "purana",
    "4_rellit": "religious_literature",
    "5_poetry": "poetry",
    "6_sastra": "sastra",
    "7_grammar": "grammar",
    "8_lexicon": "lexicon",
    "9_misc": "miscellaneous",
}
MANIFEST_FIELDS = (
    "source", "source_path", "relative_path", "canonical_path", "canonical_script",
    "document_id", "layer", "split", "char_count", "line_count", "segment_count",
    "has_accent", "has_unknown_chars", "source_hash", "canonical_hash",
)


class CanonicalGretilHTMLParser(HTMLParser):
    """HTML-to-text parser retaining body tables and explicit line structure."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif not self.skip_depth and tag == "hr":
            self.parts.append(f"\n{HR_MARK}\n")
        elif not self.skip_depth and tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif not self.skip_depth and tag in {"td", "th"}:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in BLOCK_TAGS | {"td", "th"}:
            self.parts.append("\n" if tag in BLOCK_TAGS else " ")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


@dataclass(frozen=True, slots=True)
class CleaningResult:
    text: str
    extracted_chars: int
    replacement_count: int


@dataclass(frozen=True, slots=True)
class BuildResult:
    rows: tuple[dict[str, str], ...]
    unknown_rows: tuple[dict[str, str], ...]
    missing_sources: tuple[str, ...]


def parse_whitelist(path: Path) -> tuple[str, ...]:
    """Return validated exact POSIX paths from a comment-aware whitelist."""
    entries: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        value = value.replace("\\", "/")
        pure = PurePosixPath(value)
        if pure.is_absolute() or re.match(r"^[A-Za-z]:", value) or ".." in pure.parts:
            raise ValueError(f"unsafe whitelist path at line {line_number}: {value}")
        if pure.suffix.lower() != ".htm":
            raise ValueError(f"whitelist entry is not an .htm file at line {line_number}: {value}")
        normalized = pure.as_posix()
        if normalized in seen:
            raise ValueError(f"duplicate whitelist entry at line {line_number}: {normalized}")
        seen.add(normalized)
        entries.append(normalized)
    if not entries:
        raise ValueError(f"whitelist contains no source paths: {path}")
    return tuple(entries)


def _source_path(source_root: Path, relative_path: str) -> Path:
    root = source_root.resolve()
    candidate = source_root.joinpath(*PurePosixPath(relative_path).parts).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"source path escapes source root: {relative_path}")
    return candidate


def find_missing_sources(source_root: Path, entries: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(entry for entry in entries if not _source_path(source_root, entry).is_file())


def extract_gretil_body(raw_html: str) -> str:
    """Extract text after GRETIL metadata separators without lexical filtering."""
    parser = CanonicalGretilHTMLParser()
    parser.feed(raw_html)
    parser.close()
    text = parser.text().replace("\r\n", "\n").replace("\r", "\n")
    parts = text.split(HR_MARK)
    if len(parts) >= 3:
        text = HR_MARK.join(parts[2:])
    elif len(parts) == 2:
        text = parts[1]
    return text.replace(HR_MARK, "\n")


def _strip_structural_prefixes(line: str) -> tuple[str, int]:
    replacements = 0
    patterns = PREFIX_PATTERNS + (COLOPHON_PREFIX_RE, COMPACT_PREFIX_RE, PREFIX_SIGLUM_RE)
    while True:
        changed = False
        for pattern in patterns:
            line, count = pattern.subn("", line, count=1)
            replacements += count
            changed = changed or bool(count)
        if not changed:
            return line, replacements


def _strip_structural_suffixes(line: str) -> tuple[str, int]:
    replacements = 0
    while True:
        changed = False
        line, count = VERSE_NUMBER_RE.subn(
            lambda match: "||" if max(len(match.group(1)), len(match.group(2))) >= 2 else "|",
            line,
        )
        replacements += count
        changed = changed or bool(count)
        line, count = DANDA_SIGLUM_RE.subn(lambda match: match.group("danda"), line)
        replacements += count
        changed = changed or bool(count)
        line, count = TRAILING_REDUNDANT_DANDA_RE.subn("", line)
        replacements += count
        changed = changed or bool(count)
        line, count = SUFFIX_SIGLUM_RE.subn("", line)
        replacements += count
        changed = changed or bool(count)
        if not changed:
            return line, replacements


def _strip_structural_residue(line: str) -> tuple[str, int]:
    """Reach a fixed point using only anchored labels and explicit number forms."""
    replacements = 0
    while True:
        before = line
        line, count = _strip_structural_suffixes(line)
        replacements += count
        line, count = BRACKETED_NUMBER_RE.subn(" ", line)
        replacements += count
        line, count = STANDALONE_NUMBER_RE.subn(" ", line)
        replacements += count
        line, count = _strip_structural_prefixes(line)
        replacements += count
        if line == before:
            return line, replacements


def normalize_canonical_iast(extracted_text: str) -> CleaningResult:
    """Normalize encoding/infrastructure while preserving source word boundaries."""
    text = extracted_text.replace("\r\n", "\n").replace("\r", "\n")
    replacements = 0
    for source, target in ENCODING_EQUIVALENTS.items():
        count = text.count(source)
        if count:
            text = text.replace(source, target)
            replacements += count
    text = unicodedata.normalize("NFC", text)

    cleaned_lines: list[str] = []
    previous_blank = True
    for original_line in text.split("\n"):
        line = original_line.replace("\ufeff", "")
        lower = line.casefold()
        if any(marker in lower for marker in BOILERPLATE_SUBSTRINGS) or END_MARKER_RE.match(line):
            replacements += 1
            continue
        line, count = URL_RE.subn(" ", line)
        replacements += count
        line, count = EMAIL_RE.subn(" ", line)
        replacements += count
        if DECORATION_ONLY_RE.match(line):
            replacements += 1
            line = ""
        else:
            decorated = DECORATED_TITLE_RE.match(line)
            if decorated and any(character.isalnum() for character in decorated.group("body")):
                line = decorated.group("body")
                replacements += 2
        line, count = _strip_structural_prefixes(line)
        replacements += count
        slash_pairs = line.count("//")
        if slash_pairs:
            line = line.replace("//", "||")
            replacements += slash_pairs
        single_slashes = line.count("/")
        if single_slashes:
            line = line.replace("/", "|")
            replacements += single_slashes
        # Number removal can expose an adjacent line label. Iterate only the
        # explicit structural rules until no further shortening occurs.
        line, count = _strip_structural_residue(line)
        replacements += count
        if DECORATION_ONLY_RE.match(line):
            replacements += 1
            line = ""
        line, count = HORIZONTAL_SPACE_RE.subn(" ", line)
        replacements += count
        line = line.strip()
        if not line:
            if not previous_blank and cleaned_lines:
                cleaned_lines.append("")
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False

    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
    cleaned = unicodedata.normalize("NFC", "\n".join(cleaned_lines))
    return CleaningResult(
        text=cleaned,
        extracted_chars=len(extracted_text),
        replacement_count=replacements,
    )


def has_accent(text: str) -> bool:
    # Do not decompose here: the acute in lexical IAST `s-acute` is not a
    # prosodic accent. NFC leaves stacked/Vedic marks explicit and composes
    # ordinary accented vowels, so the two cases can be distinguished.
    return any(character in ACCENT_MARKS or character in ACCENTED_VOWELS for character in text)


def unknown_characters(text: str) -> Counter[str]:
    """Return unexpected characters without modifying or discarding them."""
    unknown: Counter[str] = Counter()
    for character in text:
        if character.isspace():
            continue
        if character.isascii() and (character.isalnum() or character in ALLOWED_PUNCTUATION):
            continue
        name = unicodedata.name(character, "")
        category = unicodedata.category(character)
        if "LATIN" in name and category.startswith("L"):
            continue
        if category.startswith("M") and character in ALLOWED_COMBINING_MARKS:
            continue
        if character in ALLOWED_PUNCTUATION:
            continue
        unknown[character] += 1
    return unknown


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    root = repo_root.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _layer_for(relative_path: str) -> str:
    top_level = PurePosixPath(relative_path).parts[0]
    return LAYER_NAMES.get(top_level, top_level)


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _unknown_context(text: str, character: str) -> str:
    for line in text.splitlines():
        if character in line:
            return line[:160]
    return ""


def _prune_stale_outputs(canonical_root: Path, expected: set[Path]) -> int:
    if not canonical_root.exists():
        return 0
    removed = 0
    for path in canonical_root.rglob("*.txt"):
        if path.resolve() not in expected:
            path.unlink()
            removed += 1
    directories = sorted(
        (path for path in canonical_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed


def build_canonical_corpus(
    *,
    source_root: Path,
    whitelist_path: Path,
    canonical_root: Path,
    manifest_path: Path,
    report_dir: Path,
    repo_root: Path = Path("."),
    split_seed: str = DEFAULT_SPLIT_SEED,
) -> BuildResult:
    """Build the exact whitelist corpus and its deterministic audit artifacts."""
    entries = parse_whitelist(whitelist_path)
    missing = find_missing_sources(source_root, entries)
    if missing:
        details = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"{len(missing)} whitelist source(s) are missing:\n{details}")

    canonical_paths = {
        canonical_root.joinpath(*PurePosixPath(entry).with_suffix(".txt").parts).resolve()
        for entry in entries
    }
    stale_count = _prune_stale_outputs(canonical_root, canonical_paths)

    manifest_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, Any]] = []
    unknown_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "documents": set(), "path": "", "context": ""}
    )

    for relative_path in entries:
        source_path = _source_path(source_root, relative_path)
        raw_bytes = source_path.read_bytes()
        raw_html = raw_bytes.decode("utf-8", errors="replace")
        extracted = extract_gretil_body(raw_html)
        cleaning = normalize_canonical_iast(extracted)
        canonical_text = f"{cleaning.text}\n" if cleaning.text else ""
        canonical_bytes = canonical_text.encode("utf-8")

        canonical_path = canonical_root.joinpath(
            *PurePosixPath(relative_path).with_suffix(".txt").parts
        )
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_path.write_bytes(canonical_bytes)

        character_counts = unknown_characters(canonical_text)
        for character, count in character_counts.items():
            stats = unknown_stats[character]
            stats["count"] += count
            stats["documents"].add(relative_path)
            if not stats["path"]:
                stats["path"] = relative_path
                stats["context"] = _unknown_context(canonical_text, character)

        line_count = len(canonical_text.splitlines())
        document_id = make_document_id("gretil", relative_path)
        row = {
            "source": "gretil",
            "source_path": _repo_relative(source_path, repo_root),
            "relative_path": relative_path,
            "canonical_path": _repo_relative(canonical_path, repo_root),
            "canonical_script": "iast",
            "document_id": document_id,
            "layer": _layer_for(relative_path),
            "split": assign_split(document_id, seed=split_seed),
            "char_count": str(len(canonical_text)),
            "line_count": str(line_count),
            "segment_count": str(sum(bool(line.strip()) for line in canonical_text.splitlines())),
            "has_accent": str(has_accent(canonical_text)).lower(),
            "has_unknown_chars": str(bool(character_counts)).lower(),
            "source_hash": _sha256_bytes(raw_bytes),
            "canonical_hash": _sha256_bytes(canonical_bytes),
        }
        manifest_rows.append(row)
        audit_rows.append(
            {
                "source_path": row["source_path"],
                "relative_path": relative_path,
                "source_chars": len(raw_html),
                "extracted_chars": cleaning.extracted_chars,
                "canonical_chars": len(canonical_text),
                "removed_chars": len(raw_html) - len(canonical_text),
                "html_removed_chars": len(raw_html) - cleaning.extracted_chars,
                "normalization_char_delta": cleaning.extracted_chars - len(canonical_text),
                "replacement_count": cleaning.replacement_count,
                "decode_replacement_count": raw_html.count("\ufffd"),
                "unknown_character_count": sum(character_counts.values()),
            }
        )

    unknown_rows = _format_unknown_rows(unknown_stats)
    _write_csv(manifest_path, MANIFEST_FIELDS, manifest_rows)
    _write_csv(
        report_dir / "gretil_unknown_characters.csv",
        ("character", "codepoint", "unicode_name", "count", "document_count", "example_path", "example_context"),
        unknown_rows,
    )
    _write_csv(
        report_dir / "gretil_cleaning_audit.csv",
        (
            "source_path", "relative_path", "source_chars", "extracted_chars",
            "canonical_chars", "removed_chars", "replacement_count",
            "html_removed_chars", "normalization_char_delta", "decode_replacement_count",
            "unknown_character_count",
        ),
        audit_rows,
    )
    _write_summary(
        report_dir / "gretil_corpus_summary.txt",
        manifest_rows,
        unknown_rows,
        stale_count=stale_count,
    )
    return BuildResult(tuple(manifest_rows), tuple(unknown_rows), ())


def _format_unknown_rows(unknown_stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for character in sorted(unknown_stats, key=ord):
        stats = unknown_stats[character]
        rows.append(
            {
                "character": character,
                "codepoint": f"U+{ord(character):04X}",
                "unicode_name": unicodedata.name(character, "UNNAMED"),
                "count": stats["count"],
                "document_count": len(stats["documents"]),
                "example_path": stats["path"],
                "example_context": stats["context"],
            }
        )
    return rows


def _write_summary(
    path: Path,
    rows: list[dict[str, str]],
    unknown_rows: list[dict[str, Any]],
    *,
    stale_count: int,
) -> None:
    by_layer = Counter(row["layer"] for row in rows)
    by_split = Counter(row["split"] for row in rows)
    small = [row["relative_path"] for row in rows if int(row["char_count"]) < 100]
    empty = [row["relative_path"] for row in rows if int(row["char_count"]) == 0]
    lines = [
        "Formal GRETIL canonical IAST corpus",
        "=====================================",
        f"whitelist_document_count: {len(rows)}",
        f"successfully_processed_count: {len(rows)}",
        "missing_source_count: 0",
        f"total_canonical_chars: {sum(int(row['char_count']) for row in rows)}",
        f"total_canonical_lines: {sum(int(row['line_count']) for row in rows)}",
        f"nonempty_lines: {sum(int(row['segment_count']) for row in rows)}",
        f"accented_document_count: {sum(row['has_accent'] == 'true' for row in rows)}",
        f"unknown_character_count: {sum(int(row['count']) for row in unknown_rows)}",
        f"documents_with_unknown_characters: {sum(row['has_unknown_chars'] == 'true' for row in rows)}",
        f"unknown_character_types: {len(unknown_rows)}",
        f"empty_documents: {len(empty)}",
        f"suspiciously_small_files_under_100_chars: {len(small)}",
        f"stale_outputs_removed: {stale_count}",
        "selection_policy: exact paths from notes/whitelist.txt",
        "canonical_script: iast",
        "word_boundary_policy: preserve source-provided boundaries; no desandhi, inferred segmentation, joining, or transliteration",
        "accent_policy: preserve source accents",
        "unknown_character_policy: preserve and report",
        "",
        "documents_by_layer:",
    ]
    lines.extend(f"  {name}: {by_layer[name]}" for name in sorted(by_layer))
    lines.append("")
    lines.append("documents_by_split:")
    lines.extend(f"  {name}: {by_split[name]}" for name in sorted(by_split))
    if small:
        lines.extend(("", "documents_under_100_characters:"))
        lines.extend(f"  {relative_path}" for relative_path in small)
    if empty:
        lines.extend(("", "empty_documents:"))
        lines.extend(f"  {relative_path}" for relative_path in empty)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_canonical_corpus(
    *,
    source_root: Path,
    whitelist_path: Path,
    canonical_root: Path,
    manifest_path: Path,
    repo_root: Path = Path("."),
    split_seed: str = DEFAULT_SPLIT_SEED,
) -> tuple[dict[str, str], ...]:
    """Validate namespace completeness, hashes, encoding, and manifest invariants."""
    entries = parse_whitelist(whitelist_path)
    missing = find_missing_sources(source_root, entries)
    errors = [f"missing source: {entry}" for entry in missing]
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest does not exist: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    required = set(MANIFEST_FIELDS)
    if rows and not required.issubset(rows[0]):
        errors.append(f"manifest missing fields: {', '.join(sorted(required - set(rows[0])))}")
    manifest_relatives = [row.get("relative_path", "") for row in rows]
    if manifest_relatives != list(entries):
        errors.append("manifest paths/order do not exactly match the whitelist")
    if len(set(manifest_relatives)) != len(manifest_relatives):
        errors.append("manifest contains duplicate relative_path values")

    expected_outputs: set[Path] = set()
    for row in rows:
        relative_path = row.get("relative_path", "")
        if not relative_path:
            continue
        expected_relative = PurePosixPath(relative_path).with_suffix(".txt")
        expected_path = canonical_root.joinpath(*expected_relative.parts).resolve()
        expected_outputs.add(expected_path)
        recorded = Path(row.get("canonical_path", ""))
        recorded_path = recorded if recorded.is_absolute() else repo_root / recorded
        if recorded_path.resolve() != expected_path:
            errors.append(f"canonical path mismatch: {relative_path}")
        if not expected_path.is_file():
            errors.append(f"missing canonical output: {relative_path}")
            continue
        canonical_bytes = expected_path.read_bytes()
        canonical_text = canonical_bytes.decode("utf-8", errors="strict")
        if row.get("source") != "gretil" or row.get("canonical_script") != "iast":
            errors.append(f"source/script invariant failed: {relative_path}")
        if row.get("document_id") != make_document_id("gretil", relative_path):
            errors.append(f"document_id mismatch: {relative_path}")
        if row.get("layer") != _layer_for(relative_path):
            errors.append(f"layer mismatch: {relative_path}")
        if row.get("split") != assign_split(row.get("document_id", ""), seed=split_seed):
            errors.append(f"split mismatch: {relative_path}")
        if row.get("canonical_hash") != _sha256_bytes(canonical_bytes):
            errors.append(f"canonical hash mismatch: {relative_path}")
        if int(row.get("char_count", "-1")) != len(canonical_text):
            errors.append(f"character count mismatch: {relative_path}")
        if int(row.get("line_count", "-1")) != len(canonical_text.splitlines()):
            errors.append(f"line count mismatch: {relative_path}")
        segment_count = sum(bool(line.strip()) for line in canonical_text.splitlines())
        if int(row.get("segment_count", "-1")) != segment_count:
            errors.append(f"segment count mismatch: {relative_path}")
        character_counts = unknown_characters(canonical_text)
        if row.get("has_accent") != str(has_accent(canonical_text)).lower():
            errors.append(f"accent flag mismatch: {relative_path}")
        if row.get("has_unknown_chars") != str(bool(character_counts)).lower():
            errors.append(f"unknown-character flag mismatch: {relative_path}")
        if canonical_text != unicodedata.normalize("NFC", canonical_text):
            errors.append(f"non-NFC canonical text: {relative_path}")
        if re.search(r"[\u0900-\u097f]", canonical_text):
            errors.append(f"Devanagari found in IAST output: {relative_path}")
        if any(line != line.strip() for line in canonical_text.splitlines()):
            errors.append(f"leading/trailing line whitespace: {relative_path}")
        if any(INVALID_HORIZONTAL_SPACE_RE.search(line) for line in canonical_text.splitlines()):
            errors.append(f"repeated horizontal whitespace: {relative_path}")
        source_path = _source_path(source_root, relative_path)
        if row.get("source_path") != _repo_relative(source_path, repo_root):
            errors.append(f"source path mismatch: {relative_path}")
        if row.get("source_hash") != _sha256_bytes(source_path.read_bytes()):
            errors.append(f"source hash mismatch: {relative_path}")

    actual_outputs = {path.resolve() for path in canonical_root.rglob("*.txt")}
    for extra in sorted(actual_outputs - expected_outputs):
        errors.append(f"unexpected canonical output: {extra}")
    if errors:
        preview = "\n".join(f"- {error}" for error in errors[:100])
        suffix = f"\n- ... {len(errors) - 100} more" if len(errors) > 100 else ""
        raise ValueError(f"canonical corpus validation failed ({len(errors)} error(s)):\n{preview}{suffix}")
    return tuple(rows)


def _common_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source-root", type=Path, default=Path("data/raw/gretil"))
    parser.add_argument("--whitelist", type=Path, default=Path("notes/whitelist.txt"))
    parser.add_argument("--canonical-root", type=Path, default=Path("data/canonical/gretil_iast"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/canonical_corpus.csv"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _common_parser("Build the formal whitelist-only GRETIL canonical corpus")
    parser.add_argument("--report-dir", type=Path, default=Path("data/_reports"))
    parser.add_argument("--split-seed", default=DEFAULT_SPLIT_SEED)
    args = parser.parse_args(argv)
    result = build_canonical_corpus(
        source_root=args.source_root,
        whitelist_path=args.whitelist,
        canonical_root=args.canonical_root,
        manifest_path=args.manifest,
        report_dir=args.report_dir,
        repo_root=args.repo_root,
        split_seed=args.split_seed,
    )
    print(
        f"built {len(result.rows)} GRETIL documents; "
        f"{len(result.unknown_rows)} unknown character type(s) reported"
    )


def validate_main(argv: list[str] | None = None) -> None:
    parser = _common_parser("Validate the formal whitelist-only GRETIL canonical corpus")
    parser.add_argument("--split-seed", default=DEFAULT_SPLIT_SEED)
    args = parser.parse_args(argv)
    rows = validate_canonical_corpus(
        source_root=args.source_root,
        whitelist_path=args.whitelist,
        canonical_root=args.canonical_root,
        manifest_path=args.manifest,
        repo_root=args.repo_root,
        split_seed=args.split_seed,
    )
    print(f"validated {len(rows)} GRETIL canonical documents")


if __name__ == "__main__":
    main()

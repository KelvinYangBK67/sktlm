"""Read-only anomaly audit for the formal GRETIL canonical IAST corpus.

This module does not modify canonical corpus files.

It scans the generated canonical corpus for characters and editorial residue
outside a deliberately narrow lowercase Sanskrit IAST text inventory, then
writes reports for manual inspection.

The formal builder intentionally preserves some editorial repertoire for later
review. This audit is stricter than the builder's unknown-character check:
punctuation such as brackets, commas, periods, hyphens, numbering, uppercase
letters, and non-IAST Latin letters are surfaced even when they are valid
Unicode or expected source-side editorial characters.
"""

from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.corpus.gretil.build import (
    ACCENTED_VOWELS,
    ALLOWED_COMBINING_MARKS,
)


DEFAULT_CANONICAL_ROOT = Path("data/canonical/gretil_iast")
DEFAULT_REPORT_DIR = Path("reports/cleaning/generated/initial_audit")

SUMMARY_FILENAME = "gretil_canonical_anomaly_summary.txt"
INVENTORY_FILENAME = "gretil_canonical_character_inventory.csv"
FLAGGED_FILES_FILENAME = "gretil_canonical_flagged_files.csv"
FLAGGED_OCCURRENCES_FILENAME = "gretil_canonical_flagged_occurrences.csv"


# Character-level inventory only. Digraphs such as kh, gh, ch, ai, and au
# therefore require no special treatment.
LOWERCASE_IAST = set(
    "aāiīuūṛṝḷḹeo"
    "kgṅhcjñyśṭḍṇrṣtdnlspbmv"
    "ṃḥ"
)

# The formal canonical corpus preserves source accents. The builder represents
# some accented vowels as precomposed Unicode characters and others with
# combining marks.
LOWERCASE_ACCENTED_VOWELS = {
    character
    for character in ACCENTED_VOWELS
    if character.islower()
}

ALLOWED_BASIC = LOWERCASE_IAST | {
    "'",
    "|",
    " ",
    "\n",
}

ANGLE_BRACKETS = {"<", ">"}
SQUARE_BRACKETS = {"[", "]"}
CURLY_BRACKETS = {"{", "}"}
ROUND_BRACKETS = {"(", ")"}

HYPHENS = {
    "-",   # U+002D HYPHEN-MINUS
    "‐",   # U+2010 HYPHEN
    "-",   # U+2011 NON-BREAKING HYPHEN
    "–",   # U+2013 EN DASH
    "—",   # U+2014 EM DASH
    "−",   # U+2212 MINUS SIGN
}

NON_IAST_ASCII = set("qwfzx")

FLAG_TYPES = (
    "CONTROL_OR_FORMAT",
    "UPPERCASE",
    "NON_IAST_LATIN",
    "ANGLE_BRACKET",
    "SQUARE_BRACKET",
    "CURLY_BRACKET",
    "ROUND_BRACKET",
    "DOT",
    "COMMA",
    "DIGIT",
    "UNDERSCORE",
    "HYPHEN",
    "OTHER_NONCANONICAL",
)


@dataclass(frozen=True, slots=True)
class FlaggedLine:
    """One anomaly class observed on one canonical corpus line."""

    path: str
    line_number: int
    flag_type: str
    matches: tuple[str, ...]
    count: int
    line_text: str


@dataclass(frozen=True, slots=True)
class CorpusAudit:
    """Collected results from one complete canonical-corpus audit."""

    files: tuple[Path, ...]
    character_counts: Counter[str]
    character_files: dict[str, set[str]]
    file_rows: tuple[dict[str, Any], ...]
    flagged_lines: tuple[FlaggedLine, ...]


def classify_character(character: str) -> str | None:
    """Classify one character as allowed or as one anomaly type."""

    if character in ALLOWED_BASIC:
        return None

    if character in LOWERCASE_ACCENTED_VOWELS:
        return None

    if character in ALLOWED_COMBINING_MARKS:
        return None

    category = unicodedata.category(character)
    name = unicodedata.name(character, "")

    # Includes C0/C1 controls, DEL-like controls, zero-width joiners, BOM-like
    # format characters, and similar invisible infrastructure.
    if category in {"Cc", "Cf"}:
        return "CONTROL_OR_FORMAT"

    # Check uppercase before the general Latin-letter class so uppercase IAST
    # and uppercase editorial sigla are easy to isolate.
    if character.isupper():
        return "UPPERCASE"

    if character in ANGLE_BRACKETS:
        return "ANGLE_BRACKET"

    if character in SQUARE_BRACKETS:
        return "SQUARE_BRACKET"

    if character in CURLY_BRACKETS:
        return "CURLY_BRACKET"

    if character in ROUND_BRACKETS:
        return "ROUND_BRACKET"

    if character == ".":
        return "DOT"

    if character == ",":
        return "COMMA"

    if character.isdigit():
        return "DIGIT"

    if character == "_":
        return "UNDERSCORE"

    if character in HYPHENS:
        return "HYPHEN"

    if character in NON_IAST_ASCII:
        return "NON_IAST_LATIN"

    # Catch lowercase Latin letters outside the Sanskrit IAST inventory,
    # including source/editorial letters with additional diacritics.
    if category.startswith("L") and "LATIN" in name:
        return "NON_IAST_LATIN"

    return "OTHER_NONCANONICAL"


def display_character(character: str) -> str:
    """Return a CSV-friendly human-readable representation of a character."""

    special = {
        " ": "<SPACE>",
        "\n": "<LF>",
        "\r": "<CR>",
        "\t": "<TAB>",
    }

    if character in special:
        return special[character]

    category = unicodedata.category(character)

    if category in {"Cc", "Cf"}:
        return f"<U+{ord(character):04X}>"

    return character


def unicode_name(character: str) -> str:
    """Return a stable Unicode name for reporting."""

    return unicodedata.name(character, "UNNAMED")


def safe_line_text(line: str) -> str:
    """Render invisible control/format characters visibly in report context."""

    rendered: list[str] = []

    for character in line:
        category = unicodedata.category(character)

        if character == "\t":
            rendered.append("<TAB>")
        elif character == "\r":
            rendered.append("<CR>")
        elif category in {"Cc", "Cf"}:
            rendered.append(f"<U+{ord(character):04X}>")
        else:
            rendered.append(character)

    return "".join(rendered)


def _unique_in_order(values: list[str]) -> tuple[str, ...]:
    """Return first-seen unique values while preserving source order."""

    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)

    return tuple(output)


def scan_file(
    path: Path,
    canonical_root: Path,
) -> tuple[
    Counter[str],
    dict[str, int],
    list[FlaggedLine],
]:
    """Scan one UTF-8 canonical file without modifying it."""

    # Decode bytes directly rather than using text-mode universal-newline
    # conversion. This allows stray CR characters to remain visible to audit.
    text = path.read_bytes().decode("utf-8", errors="strict")

    relative_path = path.relative_to(canonical_root).as_posix()

    character_counts: Counter[str] = Counter(text)

    flag_counts = {
        flag_type: 0
        for flag_type in FLAG_TYPES
    }

    flagged_lines: list[FlaggedLine] = []

    # Split only on LF so a stray CR remains part of the line and is flagged.
    for line_number, line in enumerate(text.split("\n"), start=1):
        matches_by_type: dict[str, list[str]] = defaultdict(list)

        for character in line:
            flag_type = classify_character(character)

            if flag_type is None:
                continue

            flag_counts[flag_type] += 1
            matches_by_type[flag_type].append(character)

        for flag_type in FLAG_TYPES:
            matches = matches_by_type.get(flag_type)

            if not matches:
                continue

            flagged_lines.append(
                FlaggedLine(
                    path=relative_path,
                    line_number=line_number,
                    flag_type=flag_type,
                    matches=_unique_in_order(matches),
                    count=len(matches),
                    line_text=safe_line_text(line),
                )
            )

    return character_counts, flag_counts, flagged_lines


def audit_corpus(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> CorpusAudit:
    """Audit every canonical .txt file recursively under the formal root."""

    if not canonical_root.is_dir():
        raise FileNotFoundError(
            f"canonical corpus directory does not exist: {canonical_root}"
        )

    files = tuple(
        sorted(
            path
            for path in canonical_root.rglob("*.txt")
            if path.is_file()
        )
    )

    if not files:
        raise RuntimeError(
            f"no canonical .txt files found under: {canonical_root}"
        )

    corpus_character_counts: Counter[str] = Counter()

    character_files: dict[str, set[str]] = defaultdict(set)

    file_rows: list[dict[str, Any]] = []

    all_flagged_lines: list[FlaggedLine] = []

    for path in files:
        relative_path = path.relative_to(canonical_root).as_posix()

        (
            character_counts,
            flag_counts,
            flagged_lines,
        ) = scan_file(
            path,
            canonical_root,
        )

        corpus_character_counts.update(character_counts)

        for character in character_counts:
            character_files[character].add(relative_path)

        row: dict[str, Any] = {
            "path": relative_path,
        }

        for flag_type in FLAG_TYPES:
            row[flag_type] = flag_counts[flag_type]

        row["total_flags"] = sum(flag_counts.values())

        file_rows.append(row)
        all_flagged_lines.extend(flagged_lines)

    return CorpusAudit(
        files=files,
        character_counts=corpus_character_counts,
        character_files=dict(character_files),
        file_rows=tuple(file_rows),
        flagged_lines=tuple(all_flagged_lines),
    )


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
    """Write a deterministic UTF-8 CSV report."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def write_character_inventory(
    audit: CorpusAudit,
    output_path: Path,
) -> None:
    """Write the complete corpus-wide Unicode character inventory."""

    rows: list[dict[str, Any]] = []

    for character in sorted(
        audit.character_counts,
        key=ord,
    ):
        flag_type = classify_character(character)

        rows.append(
            {
                "character": display_character(character),
                "codepoint": f"U+{ord(character):04X}",
                "unicode_name": unicode_name(character),
                "count": audit.character_counts[character],
                "document_count": len(
                    audit.character_files.get(character, set())
                ),
                "allowed": str(flag_type is None).lower(),
                "flag_type": flag_type or "",
            }
        )

    _write_csv(
        output_path,
        (
            "character",
            "codepoint",
            "unicode_name",
            "count",
            "document_count",
            "allowed",
            "flag_type",
        ),
        rows,
    )


def write_flagged_files(
    audit: CorpusAudit,
    output_path: Path,
) -> None:
    """Write one row for every file containing at least one anomaly."""

    rows = [
        dict(row)
        for row in audit.file_rows
        if int(row["total_flags"]) > 0
    ]

    # Most contaminated files first. Ties remain deterministic by path.
    rows.sort(
        key=lambda row: (
            -int(row["total_flags"]),
            str(row["path"]),
        )
    )

    _write_csv(
        output_path,
        (
            "path",
            *FLAG_TYPES,
            "total_flags",
        ),
        rows,
    )


def write_flagged_occurrences(
    audit: CorpusAudit,
    output_path: Path,
) -> None:
    """Write one row per file × line × anomaly type."""

    rows: list[dict[str, Any]] = []

    for flagged in audit.flagged_lines:
        rows.append(
            {
                "path": flagged.path,
                "line_number": flagged.line_number,
                "flag_type": flagged.flag_type,
                "matches": " ".join(
                    display_character(character)
                    for character in flagged.matches
                ),
                "count": flagged.count,
                "line_text": flagged.line_text,
            }
        )

    _write_csv(
        output_path,
        (
            "path",
            "line_number",
            "flag_type",
            "matches",
            "count",
            "line_text",
        ),
        rows,
    )


def write_summary(
    audit: CorpusAudit,
    canonical_root: Path,
    output_path: Path,
) -> None:
    """Write a compact human-readable anomaly summary."""

    flagged_file_rows = [
        row
        for row in audit.file_rows
        if int(row["total_flags"]) > 0
    ]

    strict_clean_count = (
        len(audit.file_rows)
        - len(flagged_file_rows)
    )

    character_counts_by_type: Counter[str] = Counter()

    for row in audit.file_rows:
        for flag_type in FLAG_TYPES:
            character_counts_by_type[flag_type] += int(
                row[flag_type]
            )

    document_counts_by_type: Counter[str] = Counter()

    for row in audit.file_rows:
        for flag_type in FLAG_TYPES:
            if int(row[flag_type]) > 0:
                document_counts_by_type[flag_type] += 1

    total_flagged_characters = sum(
        character_counts_by_type.values()
    )

    lines = [
        "Formal GRETIL canonical IAST anomaly audit",
        "==========================================",
        f"canonical_root: {canonical_root}",
        f"files_scanned: {len(audit.files)}",
        f"strict_clean_files: {strict_clean_count}",
        f"flagged_files: {len(flagged_file_rows)}",
        f"flagged_character_occurrences: {total_flagged_characters}",
        f"flagged_line_groups: {len(audit.flagged_lines)}",
        "",
        "anomaly_counts:",
    ]

    for flag_type in FLAG_TYPES:
        lines.append(
            "  "
            f"{flag_type}: "
            f"{character_counts_by_type[flag_type]} occurrence(s), "
            f"{document_counts_by_type[flag_type]} document(s)"
        )

    lines.extend(
        [
            "",
            "policy:",
            "  lowercase Sanskrit IAST letters are allowed",
            "  source accent marks retained by the formal builder are allowed",
            "  ASCII apostrophe and danda marker | are allowed",
            "  ordinary ASCII space and LF newline are allowed",
            "  everything else is surfaced for review",
            "",
            "This audit is read-only.",
            "No canonical corpus file is modified.",
            "",
        ]
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_reports(
    audit: CorpusAudit,
    *,
    canonical_root: Path,
    report_dir: Path,
) -> None:
    """Write all canonical anomaly audit artifacts."""

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_summary(
        audit,
        canonical_root,
        report_dir / SUMMARY_FILENAME,
    )

    write_character_inventory(
        audit,
        report_dir / INVENTORY_FILENAME,
    )

    write_flagged_files(
        audit,
        report_dir / FLAGGED_FILES_FILENAME,
    )

    write_flagged_occurrences(
        audit,
        report_dir / FLAGGED_OCCURRENCES_FILENAME,
    )


def main(argv: list[str] | None = None) -> None:
    """Run the read-only formal canonical corpus anomaly audit."""

    parser = argparse.ArgumentParser(
        description=(
            "Audit the formal GRETIL canonical IAST corpus "
            "for suspicious textual residue"
        )
    )

    parser.add_argument(
        "--canonical-root",
        type=Path,
        default=DEFAULT_CANONICAL_ROOT,
    )

    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
    )

    args = parser.parse_args(argv)

    audit = audit_corpus(
        canonical_root=args.canonical_root,
    )

    write_reports(
        audit,
        canonical_root=args.canonical_root,
        report_dir=args.report_dir,
    )

    flagged_files = sum(
        int(row["total_flags"]) > 0
        for row in audit.file_rows
    )

    flagged_characters = sum(
        int(row["total_flags"])
        for row in audit.file_rows
    )

    print(
        f"audited {len(audit.files)} GRETIL canonical documents"
    )

    print(
        f"flagged {flagged_files} document(s), "
        f"{flagged_characters} suspicious character occurrence(s)"
    )

    print(
        f"reports written to {args.report_dir}"
    )


if __name__ == "__main__":
    main()

"""Post-Pass-3B full residual anomaly audit for the formal GRETIL corpus.

This audit does NOT modify corpus text.

It answers:
    - how many of the 246 files are already strictly clean;
    - how many still contain material outside the canonical character policy;
    - which anomaly categories remain;
    - which files contribute most of the residual material.

Default input:
    data/canonical_candidate/pass3b_v3_hyphen_normalized_gretil_iast

Canonical character policy audited here:
    - lowercase Sanskrit IAST letters;
    - Unicode combining marks used for retained accents;
    - ASCII apostrophe "'";
    - danda encoded as "|";
    - ASCII space and LF.

Everything else is reported for review. This deliberately remains a
diagnostic audit: a flagged character is not automatically deleted.

Reports:
    data/_reports/post_pass3b_full_audit/
        gretil_post_pass3b_full_audit_summary.txt
        gretil_post_pass3b_full_audit_files.csv
        gretil_post_pass3b_full_audit_examples.csv
        gretil_post_pass3b_flagged_files.txt
        gretil_post_pass3b_clean_files.txt
"""

from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMPLEMENTATION = "post-pass3b-full-audit-v1"

DEFAULT_INPUT_ROOT = Path(
    "data/canonical_candidate/pass3b_v3_hyphen_normalized_gretil_iast"
)
DEFAULT_REPORT_DIR = Path(
    "data/_reports/post_pass3b_full_audit"
)

SUMMARY_FILENAME = "gretil_post_pass3b_full_audit_summary.txt"
FILES_FILENAME = "gretil_post_pass3b_full_audit_files.csv"
EXAMPLES_FILENAME = "gretil_post_pass3b_full_audit_examples.csv"
FLAGGED_FILES_FILENAME = "gretil_post_pass3b_flagged_files.txt"
CLEAN_FILES_FILENAME = "gretil_post_pass3b_clean_files.txt"


# Exact lowercase Sanskrit IAST code points used in ordinary transliteration.
# Aspirates/diphthongs are sequences of these characters.
IAST_LOWER = frozenset(
    "aāiīuūṛṝḷḹeokgṅcjñṭḍṇtdnpbmyrlvśṣsh"
)

ALLOWED_LITERAL = frozenset(
    {
        "'",
        "|",
        " ",
        "\n",
    }
)

CATEGORIES = (
    "CONTROL_OR_FORMAT",
    "UPPERCASE",
    "NON_IAST_LATIN",
    "ANGLE",
    "SQUARE",
    "CURLY",
    "ROUND",
    "DOT",
    "COMMA",
    "DIGIT",
    "UNDERSCORE",
    "HYPHEN",
    "OTHER",
)


@dataclass(frozen=True, slots=True)
class Hit:
    path: str
    category: str
    character: str
    codepoint: str
    line_number: int
    column: int
    context: str


@dataclass(frozen=True, slots=True)
class AuditResult:
    files_processed: int
    strict_clean_files: int
    flagged_files: int
    flagged_occurrences: int


def _is_combining_mark(
    character: str,
) -> bool:
    return unicodedata.category(
        character
    ).startswith("M")


def classify_character(
    character: str,
) -> str | None:
    """Return anomaly category, or None when allowed."""

    if (
        character in IAST_LOWER
        or character in ALLOWED_LITERAL
        or _is_combining_mark(character)
    ):
        return None

    category = unicodedata.category(
        character
    )

    if category in {
        "Cc",
        "Cf",
        "Cs",
        "Co",
        "Cn",
    }:
        return "CONTROL_OR_FORMAT"

    if character in "<>":
        return "ANGLE"

    if character in "[]":
        return "SQUARE"

    if character in "{}":
        return "CURLY"

    if character in "()":
        return "ROUND"

    if character == ".":
        return "DOT"

    if character == ",":
        return "COMMA"

    if character == "_":
        return "UNDERSCORE"

    if character == "-":
        return "HYPHEN"

    if character.isdigit():
        return "DIGIT"

    if character.isalpha():
        if character.isupper():
            return "UPPERCASE"
        return "NON_IAST_LATIN"

    return "OTHER"


def _context(
    text: str,
    index: int,
    radius: int = 36,
) -> str:
    start = max(
        0,
        index - radius,
    )
    end = min(
        len(text),
        index + radius + 1,
    )

    return (
        text[start:end]
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def audit_text(
    text: str,
    relative_path: str,
) -> tuple[
    Counter[str],
    list[Hit],
]:
    counts: Counter[str] = Counter()
    hits: list[Hit] = []

    line_number = 1
    column = 1

    for index, character in enumerate(
        text
    ):
        category = classify_character(
            character
        )

        if category is not None:
            counts[category] += 1

            hits.append(
                Hit(
                    path=relative_path,
                    category=category,
                    character=character,
                    codepoint=(
                        f"U+{ord(character):04X}"
                    ),
                    line_number=line_number,
                    column=column,
                    context=_context(
                        text,
                        index,
                    ),
                )
            )

        if character == "\n":
            line_number += 1
            column = 1
        else:
            column += 1

    return counts, hits


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
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


def build_audit(
    *,
    input_root: Path,
    report_dir: Path,
    examples_per_category_per_file: int = 3,
) -> AuditResult:
    if not input_root.is_dir():
        raise FileNotFoundError(
            f"audit input root does not exist: {input_root}"
        )

    files = tuple(
        sorted(
            path
            for path in input_root.rglob(
                "*.txt"
            )
            if path.is_file()
        )
    )

    if not files:
        raise RuntimeError(
            f"no .txt files found under: {input_root}"
        )

    file_rows: list[
        dict[str, Any]
    ] = []

    all_hits: list[Hit] = []

    category_occurrences: Counter[
        str
    ] = Counter()

    category_files: dict[
        str,
        set[str],
    ] = defaultdict(set)

    flagged_files: list[str] = []
    clean_files: list[str] = []

    for source_path in files:
        relative_path = (
            source_path.relative_to(
                input_root
            ).as_posix()
        )

        text = source_path.read_text(
            encoding="utf-8",
        )

        counts, hits = audit_text(
            text,
            relative_path,
        )

        total = sum(
            counts.values()
        )

        if total:
            flagged_files.append(
                relative_path
            )
        else:
            clean_files.append(
                relative_path
            )

        for category, count in counts.items():
            category_occurrences[
                category
            ] += count

            if count:
                category_files[
                    category
                ].add(
                    relative_path
                )

        all_hits.extend(hits)

        row: dict[str, Any] = {
            "path": relative_path,
            "flagged_occurrences": total,
            "categories_present": (
                " ".join(
                    category
                    for category in CATEGORIES
                    if counts[category]
                )
            ),
        }

        for category in CATEGORIES:
            row[category] = (
                counts[category]
            )

        file_rows.append(row)

    file_rows.sort(
        key=lambda row: (
            -int(
                row[
                    "flagged_occurrences"
                ]
            ),
            str(row["path"]),
        )
    )

    _write_csv(
        report_dir / FILES_FILENAME,
        (
            "path",
            "flagged_occurrences",
            "categories_present",
            *CATEGORIES,
        ),
        file_rows,
    )

    # Keep only a few examples per file/category so the report stays human-sized.
    example_counter: Counter[
        tuple[str, str]
    ] = Counter()

    example_rows: list[
        dict[str, Any]
    ] = []

    for hit in all_hits:
        key = (
            hit.path,
            hit.category,
        )

        if (
            example_counter[key]
            >= examples_per_category_per_file
        ):
            continue

        example_counter[key] += 1

        example_rows.append(
            {
                "path": hit.path,
                "category": (
                    hit.category
                ),
                "character": (
                    hit.character
                ),
                "codepoint": (
                    hit.codepoint
                ),
                "line_number": (
                    hit.line_number
                ),
                "column": hit.column,
                "context": hit.context,
            }
        )

    example_rows.sort(
        key=lambda row: (
            str(row["category"]),
            str(row["path"]),
            int(row["line_number"]),
            int(row["column"]),
        )
    )

    _write_csv(
        report_dir / EXAMPLES_FILENAME,
        (
            "path",
            "category",
            "character",
            "codepoint",
            "line_number",
            "column",
            "context",
        ),
        example_rows,
    )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        report_dir
        / FLAGGED_FILES_FILENAME
    ).write_text(
        "\n".join(
            flagged_files
        )
        + (
            "\n"
            if flagged_files
            else ""
        ),
        encoding="utf-8",
    )

    (
        report_dir
        / CLEAN_FILES_FILENAME
    ).write_text(
        "\n".join(
            clean_files
        )
        + (
            "\n"
            if clean_files
            else ""
        ),
        encoding="utf-8",
    )

    _write_summary(
        report_dir
        / SUMMARY_FILENAME,
        input_root=input_root,
        files_processed=len(
            files
        ),
        strict_clean_files=len(
            clean_files
        ),
        flagged_files=len(
            flagged_files
        ),
        flagged_occurrences=sum(
            category_occurrences.values()
        ),
        category_occurrences=(
            category_occurrences
        ),
        category_files=(
            category_files
        ),
        top_files=file_rows[:30],
    )

    return AuditResult(
        files_processed=len(
            files
        ),
        strict_clean_files=len(
            clean_files
        ),
        flagged_files=len(
            flagged_files
        ),
        flagged_occurrences=sum(
            category_occurrences.values()
        ),
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    files_processed: int,
    strict_clean_files: int,
    flagged_files: int,
    flagged_occurrences: int,
    category_occurrences: Counter[str],
    category_files: dict[
        str,
        set[str],
    ],
    top_files: list[
        dict[str, Any]
    ],
) -> None:
    lines = [
        "Formal GRETIL post-Pass-3B full residual audit",
        "===============================================",
        (
            "implementation: "
            f"{IMPLEMENTATION}"
        ),
        f"input_root: {input_root}",
        (
            "files_processed: "
            f"{files_processed}"
        ),
        (
            "strict_clean_files: "
            f"{strict_clean_files}"
        ),
        (
            "flagged_files: "
            f"{flagged_files}"
        ),
        (
            "flagged_occurrences: "
            f"{flagged_occurrences}"
        ),
        "",
        "category totals:",
    ]

    for category in CATEGORIES:
        lines.append(
            (
                f"  {category}: "
                f"{category_occurrences[category]} "
                f"occurrences / "
                f"{len(category_files[category])} files"
            )
        )

    lines.extend(
        [
            "",
            "top flagged files:",
        ]
    )

    for row in top_files:
        lines.append(
            (
                "  "
                f"{int(row['flagged_occurrences']):>9}  "
                f"{row['path']}  "
                f"[{row['categories_present']}]"
            )
        )

    lines.extend(
        [
            "",
            "interpretation:",
            (
                "  flagged_files is the conservative upper bound "
                "on files still requiring review"
            ),
            (
                "  a flag does not itself authorize deletion or normalization"
            ),
            (
                "  source-specific cleanup should be prioritized by file "
                "and category concentration"
            ),
            "",
            "The audited corpus was not modified.",
            "",
        ]
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main(
    argv: list[str] | None = None,
) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit all residual non-canonical material "
            "after Pass 3B v3"
        )
    )

    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
    )
    parser.add_argument(
        "--examples-per-category-per-file",
        type=int,
        default=3,
    )

    args = parser.parse_args(
        argv
    )

    result = build_audit(
        input_root=args.input_root,
        report_dir=args.report_dir,
        examples_per_category_per_file=(
            args.examples_per_category_per_file
        ),
    )

    print(
        f"implementation: {IMPLEMENTATION}"
    )
    print(
        f"files processed: "
        f"{result.files_processed}"
    )
    print(
        f"strict clean files: "
        f"{result.strict_clean_files}"
    )
    print(
        f"flagged files: "
        f"{result.flagged_files}"
    )
    print(
        f"flagged occurrences: "
        f"{result.flagged_occurrences}"
    )


if __name__ == "__main__":
    main()

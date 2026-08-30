"""Filter pluta-bearing documents from the GRETIL canonical candidate corpus.

This step is deliberately file-level.

A Sanskrit pluta marker such as::

    ā3
    nā3
    o3m
    parā3ṅ

is linguistic material, not an ordinary structural digit. Therefore this tool
does NOT delete the digit ``3`` from the text. Instead, any document containing
a high-confidence pluta pattern is excluded from the next candidate corpus and
reported for corpus-membership review.

The input corpus is never modified.

Default pipeline::

    data/intermediate/gretil/pass1_gretil_iast
        ->
    data/intermediate/gretil/pass1_no_pluta_gretil_iast
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.corpus.gretil.build import ACCENTED_VOWELS


DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pass1_gretil_iast"
)

DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pass1_no_pluta_gretil_iast"
)

DEFAULT_REPORT_DIR = Path(
    "reports/cleaning/generated/pluta_filter"
)

SUMMARY_FILENAME = "gretil_pluta_filter_summary.txt"
EXCLUDED_FILENAME = "gretil_pluta_excluded_files.csv"
OCCURRENCES_FILENAME = "gretil_pluta_occurrences.csv"


BASE_VOWELS = set(
    "aāiīuūṛṝḷḹeo"
)

ACCENTED_LOWERCASE_VOWELS = {
    character
    for character in ACCENTED_VOWELS
    if character.islower()
}

PLUTA_VOWELS = (
    BASE_VOWELS
    | ACCENTED_LOWERCASE_VOWELS
)

PLUTA_VOWEL_CLASS = "".join(
    sorted(
        (
            re.escape(character)
            for character in PLUTA_VOWELS
        ),
        key=len,
        reverse=True,
    )
)

# Combining accents are permitted between the vowel and the pluta digit.
#
# Examples:
#   ā3
#   á3
#   ā́3
#
# We intentionally do NOT match arbitrary "letter + 3", because:
#
#   1.2.3
#   ||31||
#   HV App.I,3.14
#
# are structural numbering rather than pluta.
PLUTA_RE = re.compile(
    rf"[{PLUTA_VOWEL_CLASS}]"
    rf"[\u0300-\u036f]*"
    rf"3"
)


@dataclass(frozen=True, slots=True)
class PlutaOccurrence:
    path: str
    line_number: int
    column: int
    match: str
    line_text: str


@dataclass(frozen=True, slots=True)
class PlutaFilterResult:
    files_scanned: int
    files_kept: int
    files_excluded: int
    pluta_occurrences: int


def find_pluta_occurrences(
    text: str,
    relative_path: str,
) -> list[PlutaOccurrence]:
    """Find high-confidence Sanskrit pluta markers in one document."""

    occurrences: list[PlutaOccurrence] = []

    for line_number, line in enumerate(
        text.split("\n"),
        start=1,
    ):
        for match in PLUTA_RE.finditer(line):
            occurrences.append(
                PlutaOccurrence(
                    path=relative_path,
                    line_number=line_number,
                    column=match.start() + 1,
                    match=match.group(0),
                    line_text=line,
                )
            )

    return occurrences


def _validate_roots(
    input_root: Path,
    output_root: Path,
) -> None:
    source = input_root.resolve()
    destination = output_root.resolve()

    if source == destination:
        raise ValueError(
            "output root must not equal input root"
        )

    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError(
            "output root must not be inside input root"
        )


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


def filter_pluta_documents(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
) -> PlutaFilterResult:
    """Build a candidate corpus excluding all pluta-bearing documents."""

    if not input_root.is_dir():
        raise FileNotFoundError(
            f"input corpus does not exist: {input_root}"
        )

    _validate_roots(
        input_root,
        output_root,
    )

    files = tuple(
        sorted(
            path
            for path in input_root.rglob("*.txt")
            if path.is_file()
        )
    )

    if not files:
        raise RuntimeError(
            f"no .txt files found under: {input_root}"
        )

    if output_root.exists():
        shutil.rmtree(output_root)

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    excluded_rows: list[dict[str, Any]] = []
    occurrence_rows: list[dict[str, Any]] = []

    files_kept = 0
    files_excluded = 0
    total_occurrences = 0

    for source_path in files:
        relative_path = source_path.relative_to(
            input_root
        )

        relative_string = relative_path.as_posix()

        raw_bytes = source_path.read_bytes()

        text = raw_bytes.decode(
            "utf-8",
            errors="strict",
        )

        occurrences = find_pluta_occurrences(
            text,
            relative_string,
        )

        if occurrences:
            files_excluded += 1
            total_occurrences += len(
                occurrences
            )

            unique_forms = sorted(
                {
                    occurrence.match
                    for occurrence in occurrences
                }
            )

            excluded_rows.append(
                {
                    "path": relative_string,
                    "pluta_occurrences": len(
                        occurrences
                    ),
                    "pluta_forms": " ".join(
                        unique_forms
                    ),
                }
            )

            for occurrence in occurrences:
                occurrence_rows.append(
                    {
                        "path": occurrence.path,
                        "line_number": (
                            occurrence.line_number
                        ),
                        "column": occurrence.column,
                        "match": occurrence.match,
                        "line_text": (
                            occurrence.line_text
                        ),
                    }
                )

            continue

        destination = (
            output_root
            / relative_path
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Preserve retained candidate files byte-identically.
        destination.write_bytes(
            raw_bytes
        )

        files_kept += 1

    excluded_rows.sort(
        key=lambda row: (
            -int(row["pluta_occurrences"]),
            str(row["path"]),
        )
    )

    occurrence_rows.sort(
        key=lambda row: (
            str(row["path"]),
            int(row["line_number"]),
            int(row["column"]),
        )
    )

    _write_csv(
        report_dir / EXCLUDED_FILENAME,
        (
            "path",
            "pluta_occurrences",
            "pluta_forms",
        ),
        excluded_rows,
    )

    _write_csv(
        report_dir / OCCURRENCES_FILENAME,
        (
            "path",
            "line_number",
            "column",
            "match",
            "line_text",
        ),
        occurrence_rows,
    )

    _write_summary(
        report_dir / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_scanned=len(files),
        files_kept=files_kept,
        files_excluded=files_excluded,
        pluta_occurrences=total_occurrences,
    )

    return PlutaFilterResult(
        files_scanned=len(files),
        files_kept=files_kept,
        files_excluded=files_excluded,
        pluta_occurrences=total_occurrences,
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    output_root: Path,
    files_scanned: int,
    files_kept: int,
    files_excluded: int,
    pluta_occurrences: int,
) -> None:
    lines = [
        "Formal GRETIL pluta document filter",
        "===================================",
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        f"files_scanned: {files_scanned}",
        f"files_kept: {files_kept}",
        f"files_excluded: {files_excluded}",
        f"pluta_occurrences: {pluta_occurrences}",
        "",
        "policy:",
        "  detect Sanskrit vowel + digit 3 as pluta",
        "  do not delete pluta markers from Sanskrit text",
        "  exclude the containing document from this candidate corpus",
        "  preserve retained files byte-identically",
        "",
        "ordinary structural digits are not matched merely because",
        "they contain the digit 3.",
        "",
        "The input corpus was not modified.",
        "",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Exclude documents containing Sanskrit pluta "
            "markers from the Pass 1 canonical candidate"
        )
    )

    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )

    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
    )

    args = parser.parse_args(argv)

    result = filter_pluta_documents(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
    )

    print(
        f"scanned {result.files_scanned} document(s)"
    )

    print(
        f"excluded {result.files_excluded} "
        f"pluta-bearing document(s)"
    )

    print(
        f"retained {result.files_kept} document(s)"
    )

    print(
        f"found {result.pluta_occurrences} "
        f"pluta occurrence(s)"
    )

    print(
        f"candidate corpus: {args.output_root}"
    )

    print(
        f"reports: {args.report_dir}"
    )


if __name__ == "__main__":
    main()

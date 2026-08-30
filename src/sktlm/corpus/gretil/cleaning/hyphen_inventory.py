"""Dry-run inventory for hyphen conventions in the GRETIL canonical corpus.

This stage does NOT modify the corpus.

Purpose
-------
Identify files in which ASCII hyphen ``-`` functions systematically as an
explicit source segmentation separator, so that those files can later be added
to ``HYPHEN_BOUNDARY_FILES`` and normalized to ASCII spaces.

Input::

    data/intermediate/gretil/pass3a_separator_normalized_gretil_iast

Reports::

    reports/cleaning/generated/pass3b_hyphen_inventory/
        gretil_hyphen_inventory_summary.txt
        gretil_hyphen_inventory_files.csv
        gretil_hyphen_inventory_occurrences.csv
        gretil_hyphen_inventory_candidates.csv

Classification
--------------
SEPARATOR
    lexical-lexical
    lexical-avagraha
    protected-lexical / lexical-protected

NON_SEPARATOR
    digit-digit
    repeated hyphen
    inside protected span

REVIEW
    adjacent whitespace
    uppercase/editorial-looking context
    punctuation/symbol context
    line edge
    other unresolved context

Protected spans are opaque: their contents are not interpreted, but a hyphen
immediately outside a protected span can be classified using PROTECTED as one
semantic neighbour.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


IMPLEMENTATION = "hyphen-inventory-v1"

DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pass3a_separator_normalized_gretil_iast"
)
DEFAULT_REPORT_DIR = Path(
    "reports/cleaning/generated/pass3b_hyphen_inventory"
)

SUMMARY_FILENAME = "gretil_hyphen_inventory_summary.txt"
FILES_FILENAME = "gretil_hyphen_inventory_files.csv"
OCCURRENCES_FILENAME = "gretil_hyphen_inventory_occurrences.csv"
CANDIDATES_FILENAME = "gretil_hyphen_inventory_candidates.csv"

PROTECTED_SPAN_RE = re.compile(
    r"""
    \[[^\]\n]*\]
    |
    \([^)\n]*\)
    |
    \{[^}\n]*\}
    |
    <[^>\n]*>
    """,
    re.VERBOSE,
)

Decision = Literal[
    "SEPARATOR",
    "NON_SEPARATOR",
    "REVIEW",
]

UnitKind = Literal[
    "EDGE",
    "LEXICAL",
    "PROTECTED",
    "DIGIT",
    "SPACE",
    "APOSTROPHE",
    "HYPHEN",
    "DANDA",
    "OTHER",
]


@dataclass(frozen=True, slots=True)
class SemanticUnit:
    kind: UnitKind
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class Classification:
    decision: Decision
    reason: str


@dataclass(frozen=True, slots=True)
class Occurrence:
    path: str
    line_number: int
    column: int
    decision: Decision
    reason: str
    left_kind: UnitKind
    right_kind: UnitKind
    context: str
    line_text: str


@dataclass(frozen=True, slots=True)
class InventoryResult:
    files_scanned: int
    files_with_hyphen: int
    hyphen_occurrences: int
    separator_occurrences: int
    non_separator_occurrences: int
    review_occurrences: int
    candidate_files: int


def _protected_intervals(
    line: str,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (match.start(), match.end())
        for match in PROTECTED_SPAN_RE.finditer(line)
    )


def _containing_interval(
    index: int,
    intervals: tuple[tuple[int, int], ...],
) -> tuple[int, int] | None:
    for start, end in intervals:
        if start <= index < end:
            return start, end
    return None


def _interval_ending_at(
    index: int,
    intervals: tuple[tuple[int, int], ...],
) -> tuple[int, int] | None:
    for start, end in intervals:
        if end == index:
            return start, end
    return None


def _interval_starting_at(
    index: int,
    intervals: tuple[tuple[int, int], ...],
) -> tuple[int, int] | None:
    for start, end in intervals:
        if start == index:
            return start, end
    return None


def _is_lowercase_lexical(
    character: str,
) -> bool:
    return (
        character.isalpha()
        and character.lower() == character
    )


def _unit_from_character(
    line: str,
    index: int,
) -> SemanticUnit:
    character = line[index]

    if _is_lowercase_lexical(character):
        kind: UnitKind = "LEXICAL"
    elif character.isdigit():
        kind = "DIGIT"
    elif character.isspace():
        kind = "SPACE"
    elif character == "'":
        kind = "APOSTROPHE"
    elif character == "-":
        kind = "HYPHEN"
    elif character == "|":
        kind = "DANDA"
    else:
        kind = "OTHER"

    return SemanticUnit(
        kind=kind,
        start=index,
        end=index + 1,
        text=character,
    )


def _left_unit(
    line: str,
    hyphen_index: int,
    intervals: tuple[tuple[int, int], ...],
) -> SemanticUnit:
    if hyphen_index == 0:
        return SemanticUnit(
            "EDGE",
            0,
            0,
            "",
        )

    protected = _interval_ending_at(
        hyphen_index,
        intervals,
    )
    if protected is not None:
        start, end = protected
        return SemanticUnit(
            "PROTECTED",
            start,
            end,
            line[start:end],
        )

    return _unit_from_character(
        line,
        hyphen_index - 1,
    )


def _right_unit(
    line: str,
    hyphen_index: int,
    intervals: tuple[tuple[int, int], ...],
) -> SemanticUnit:
    next_index = hyphen_index + 1

    if next_index >= len(line):
        return SemanticUnit(
            "EDGE",
            len(line),
            len(line),
            "",
        )

    protected = _interval_starting_at(
        next_index,
        intervals,
    )
    if protected is not None:
        start, end = protected
        return SemanticUnit(
            "PROTECTED",
            start,
            end,
            line[start:end],
        )

    return _unit_from_character(
        line,
        next_index,
    )


def _avagraha_followed_by_lexical(
    line: str,
    right: SemanticUnit,
) -> bool:
    if right.kind != "APOSTROPHE":
        return False

    next_index = right.end

    return (
        next_index < len(line)
        and _is_lowercase_lexical(
            line[next_index]
        )
    )


def _context(
    line: str,
    index: int,
    radius: int = 35,
) -> str:
    start = max(
        0,
        index - radius,
    )
    end = min(
        len(line),
        index + radius + 1,
    )
    return line[start:end]


def classify_hyphen(
    line: str,
    index: int,
    *,
    protected: tuple[tuple[int, int], ...] | None = None,
) -> tuple[
    Classification,
    SemanticUnit,
    SemanticUnit,
]:
    """Classify one ASCII hyphen without modifying the line."""

    if not 0 <= index < len(line):
        raise IndexError(index)

    if line[index] != "-":
        raise ValueError(
            "index does not point at a hyphen"
        )

    if protected is None:
        protected = _protected_intervals(
            line
        )

    if _containing_interval(
        index,
        protected,
    ) is not None:
        unit = SemanticUnit(
            "PROTECTED",
            index,
            index + 1,
            "-",
        )
        return (
            Classification(
                "NON_SEPARATOR",
                "inside_protected_span",
            ),
            unit,
            unit,
        )

    left = _left_unit(
        line,
        index,
        protected,
    )
    right = _right_unit(
        line,
        index,
        protected,
    )

    if (
        left.kind == "DIGIT"
        or right.kind == "DIGIT"
    ):
        return (
            Classification(
                "NON_SEPARATOR",
                "adjacent_digit",
            ),
            left,
            right,
        )

    if (
        left.kind == "HYPHEN"
        or right.kind == "HYPHEN"
    ):
        return (
            Classification(
                "NON_SEPARATOR",
                "repeated_hyphen",
            ),
            left,
            right,
        )

    separator_pairs = {
        ("LEXICAL", "LEXICAL"),
        ("LEXICAL", "PROTECTED"),
        ("PROTECTED", "LEXICAL"),
        ("PROTECTED", "PROTECTED"),
    }

    if (
        left.kind,
        right.kind,
    ) in separator_pairs:
        return (
            Classification(
                "SEPARATOR",
                (
                    f"{left.kind.lower()}_to_"
                    f"{right.kind.lower()}"
                ),
            ),
            left,
            right,
        )

    if (
        left.kind in {
            "LEXICAL",
            "PROTECTED",
        }
        and _avagraha_followed_by_lexical(
            line,
            right,
        )
    ):
        return (
            Classification(
                "SEPARATOR",
                "to_avagraha_lexical",
            ),
            left,
            right,
        )

    if (
        left.kind == "SPACE"
        or right.kind == "SPACE"
    ):
        return (
            Classification(
                "REVIEW",
                "adjacent_whitespace",
            ),
            left,
            right,
        )

    if (
        left.kind == "EDGE"
        or right.kind == "EDGE"
    ):
        return (
            Classification(
                "REVIEW",
                "line_edge",
            ),
            left,
            right,
        )

    if (
        left.kind == "OTHER"
        or right.kind == "OTHER"
    ):
        return (
            Classification(
                "REVIEW",
                "other_symbol_context",
            ),
            left,
            right,
        )

    return (
        Classification(
            "REVIEW",
            (
                f"unclassified_"
                f"{left.kind.lower()}_"
                f"{right.kind.lower()}"
            ),
        ),
        left,
        right,
    )


def inventory_document(
    text: str,
    relative_path: str,
) -> tuple[
    tuple[Occurrence, ...],
    Counter[str],
]:
    normalized_path = relative_path.replace(
        "\\",
        "/",
    )

    occurrences: list[
        Occurrence
    ] = []

    reasons: Counter[str] = Counter()

    for line_number, line in enumerate(
        text.split("\n"),
        start=1,
    ):
        protected = _protected_intervals(
            line
        )

        for index, character in enumerate(
            line
        ):
            if character != "-":
                continue

            (
                classification,
                left,
                right,
            ) = classify_hyphen(
                line,
                index,
                protected=protected,
            )

            reasons[
                (
                    f"{classification.decision}:"
                    f"{classification.reason}"
                )
            ] += 1

            occurrences.append(
                Occurrence(
                    path=normalized_path,
                    line_number=line_number,
                    column=index + 1,
                    decision=(
                        classification.decision
                    ),
                    reason=(
                        classification.reason
                    ),
                    left_kind=left.kind,
                    right_kind=right.kind,
                    context=_context(
                        line,
                        index,
                    ),
                    line_text=line,
                )
            )

    return tuple(
        occurrences
    ), reasons


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
        writer.writerows(
            rows
        )


def _candidate_metrics(
    *,
    separator: int,
    non_separator: int,
    review: int,
) -> tuple[
    int,
    float,
    float,
]:
    """Return eligible_count, separator_share, review_share.

    ``separator_share`` is intentionally conservative: the denominator contains
    all hyphen occurrences, including obvious non-separators.
    """

    total = (
        separator
        + non_separator
        + review
    )

    if total == 0:
        return 0, 0.0, 0.0

    separator_share = (
        separator
        / total
    )
    review_share = (
        review
        / total
    )

    return (
        total,
        separator_share,
        review_share,
    )


def _is_candidate_file(
    *,
    total: int,
    separator: int,
    separator_share: float,
    review_share: float,
    min_occurrences: int,
    min_separator_share: float,
    max_review_share: float,
) -> bool:
    """Flag likely source-separator families for manual confirmation.

    This is only triage. A candidate flag never causes text modification.
    """

    return (
        total >= min_occurrences
        and separator > 0
        and separator_share
        >= min_separator_share
        and review_share
        <= max_review_share
    )


def build_inventory(
    *,
    input_root: Path,
    report_dir: Path,
    min_occurrences: int = 20,
    min_separator_share: float = 0.95,
    max_review_share: float = 0.05,
) -> InventoryResult:
    if not input_root.is_dir():
        raise FileNotFoundError(
            f"input corpus does not exist: "
            f"{input_root}"
        )

    files = tuple(
        sorted(
            path
            for path
            in input_root.rglob(
                "*.txt"
            )
            if path.is_file()
        )
    )

    if not files:
        raise RuntimeError(
            f"no .txt files found under: "
            f"{input_root}"
        )

    all_occurrences: list[
        Occurrence
    ] = []

    file_rows: list[
        dict[str, Any]
    ] = []

    candidate_rows: list[
        dict[str, Any]
    ] = []

    files_with_hyphen = 0

    for source_path in files:
        relative_path = (
            source_path.relative_to(
                input_root
            )
        )
        relative_string = (
            relative_path.as_posix()
        )

        text = source_path.read_text(
            encoding="utf-8",
        )

        (
            occurrences,
            _,
        ) = inventory_document(
            text,
            relative_string,
        )

        if not occurrences:
            continue

        files_with_hyphen += 1
        all_occurrences.extend(
            occurrences
        )

        decision_counts = Counter(
            occurrence.decision
            for occurrence
            in occurrences
        )

        reason_counts = Counter(
            (
                f"{occurrence.decision}:"
                f"{occurrence.reason}"
            )
            for occurrence
            in occurrences
        )

        separator = decision_counts[
            "SEPARATOR"
        ]
        non_separator = decision_counts[
            "NON_SEPARATOR"
        ]
        review = decision_counts[
            "REVIEW"
        ]

        (
            total,
            separator_share,
            review_share,
        ) = _candidate_metrics(
            separator=separator,
            non_separator=(
                non_separator
            ),
            review=review,
        )

        candidate = _is_candidate_file(
            total=total,
            separator=separator,
            separator_share=(
                separator_share
            ),
            review_share=(
                review_share
            ),
            min_occurrences=(
                min_occurrences
            ),
            min_separator_share=(
                min_separator_share
            ),
            max_review_share=(
                max_review_share
            ),
        )

        top_reasons = " ".join(
            f"{reason}={count}"
            for reason, count
            in reason_counts.most_common(
                8
            )
        )

        row = {
            "path": relative_string,
            "hyphens": total,
            "separator": separator,
            "non_separator": (
                non_separator
            ),
            "review": review,
            "separator_share": (
                f"{separator_share:.6f}"
            ),
            "review_share": (
                f"{review_share:.6f}"
            ),
            "candidate": int(
                candidate
            ),
            "top_reasons": (
                top_reasons
            ),
        }

        file_rows.append(
            row
        )

        if candidate:
            candidate_rows.append(
                row.copy()
            )

    file_rows.sort(
        key=lambda row: (
            -float(
                row[
                    "separator_share"
                ]
            ),
            -int(
                row["hyphens"]
            ),
            str(
                row["path"]
            ),
        )
    )

    candidate_rows.sort(
        key=lambda row: (
            -int(
                row["hyphens"]
            ),
            str(
                row["path"]
            ),
        )
    )

    occurrence_rows = [
        {
            "path": occurrence.path,
            "line_number": (
                occurrence.line_number
            ),
            "column": (
                occurrence.column
            ),
            "decision": (
                occurrence.decision
            ),
            "reason": (
                occurrence.reason
            ),
            "left_kind": (
                occurrence.left_kind
            ),
            "right_kind": (
                occurrence.right_kind
            ),
            "context": (
                occurrence.context
            ),
            "line_text": (
                occurrence.line_text
            ),
        }
        for occurrence
        in all_occurrences
    ]

    occurrence_rows.sort(
        key=lambda row: (
            str(
                row["path"]
            ),
            int(
                row["line_number"]
            ),
            int(
                row["column"]
            ),
        )
    )

    file_fields = (
        "path",
        "hyphens",
        "separator",
        "non_separator",
        "review",
        "separator_share",
        "review_share",
        "candidate",
        "top_reasons",
    )

    _write_csv(
        report_dir
        / FILES_FILENAME,
        file_fields,
        file_rows,
    )

    _write_csv(
        report_dir
        / CANDIDATES_FILENAME,
        file_fields,
        candidate_rows,
    )

    _write_csv(
        report_dir
        / OCCURRENCES_FILENAME,
        (
            "path",
            "line_number",
            "column",
            "decision",
            "reason",
            "left_kind",
            "right_kind",
            "context",
            "line_text",
        ),
        occurrence_rows,
    )

    decision_counts = Counter(
        occurrence.decision
        for occurrence
        in all_occurrences
    )

    _write_summary(
        report_dir
        / SUMMARY_FILENAME,
        input_root=input_root,
        files_scanned=len(
            files
        ),
        files_with_hyphen=(
            files_with_hyphen
        ),
        hyphen_occurrences=len(
            all_occurrences
        ),
        separator_occurrences=(
            decision_counts[
                "SEPARATOR"
            ]
        ),
        non_separator_occurrences=(
            decision_counts[
                "NON_SEPARATOR"
            ]
        ),
        review_occurrences=(
            decision_counts[
                "REVIEW"
            ]
        ),
        candidate_files=len(
            candidate_rows
        ),
        min_occurrences=(
            min_occurrences
        ),
        min_separator_share=(
            min_separator_share
        ),
        max_review_share=(
            max_review_share
        ),
    )

    return InventoryResult(
        files_scanned=len(
            files
        ),
        files_with_hyphen=(
            files_with_hyphen
        ),
        hyphen_occurrences=len(
            all_occurrences
        ),
        separator_occurrences=(
            decision_counts[
                "SEPARATOR"
            ]
        ),
        non_separator_occurrences=(
            decision_counts[
                "NON_SEPARATOR"
            ]
        ),
        review_occurrences=(
            decision_counts[
                "REVIEW"
            ]
        ),
        candidate_files=len(
            candidate_rows
        ),
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    files_scanned: int,
    files_with_hyphen: int,
    hyphen_occurrences: int,
    separator_occurrences: int,
    non_separator_occurrences: int,
    review_occurrences: int,
    candidate_files: int,
    min_occurrences: int,
    min_separator_share: float,
    max_review_share: float,
) -> None:
    lines = [
        "Formal GRETIL hyphen inventory",
        "==============================",
        (
            "implementation: "
            f"{IMPLEMENTATION}"
        ),
        f"input_root: {input_root}",
        (
            "files_scanned: "
            f"{files_scanned}"
        ),
        (
            "files_with_hyphen: "
            f"{files_with_hyphen}"
        ),
        (
            "hyphen_occurrences: "
            f"{hyphen_occurrences}"
        ),
        "",
        "classification:",
        (
            "  separator: "
            f"{separator_occurrences}"
        ),
        (
            "  non_separator: "
            f"{non_separator_occurrences}"
        ),
        (
            "  review: "
            f"{review_occurrences}"
        ),
        "",
        "candidate triage:",
        (
            "  candidate_files: "
            f"{candidate_files}"
        ),
        (
            "  min_occurrences: "
            f"{min_occurrences}"
        ),
        (
            "  min_separator_share: "
            f"{min_separator_share:.3f}"
        ),
        (
            "  max_review_share: "
            f"{max_review_share:.3f}"
        ),
        "",
        "important:",
        (
            "  candidate flags are diagnostic "
            "only"
        ),
        (
            "  this stage does not modify "
            "any corpus file"
        ),
        (
            "  source-family whitelist must "
            "still be reviewed manually"
        ),
        "",
    ]

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )


def main(
    argv: list[str] | None = None,
) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory ASCII hyphen "
            "conventions without modifying "
            "the corpus"
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
        "--min-occurrences",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--min-separator-share",
        type=float,
        default=0.95,
    )
    parser.add_argument(
        "--max-review-share",
        type=float,
        default=0.05,
    )

    args = parser.parse_args(
        argv
    )

    result = build_inventory(
        input_root=args.input_root,
        report_dir=args.report_dir,
        min_occurrences=(
            args.min_occurrences
        ),
        min_separator_share=(
            args.min_separator_share
        ),
        max_review_share=(
            args.max_review_share
        ),
    )

    print(
        f"implementation: "
        f"{IMPLEMENTATION}"
    )
    print(
        f"scanned "
        f"{result.files_scanned} "
        f"document(s)"
    )
    print(
        f"files with hyphen: "
        f"{result.files_with_hyphen}"
    )
    print(
        f"hyphen occurrences: "
        f"{result.hyphen_occurrences}"
    )
    print(
        f"SEPARATOR: "
        f"{result.separator_occurrences}"
    )
    print(
        f"NON_SEPARATOR: "
        f"{result.non_separator_occurrences}"
    )
    print(
        f"REVIEW: "
        f"{result.review_occurrences}"
    )
    print(
        f"candidate files: "
        f"{result.candidate_files}"
    )


if __name__ == "__main__":
    main()

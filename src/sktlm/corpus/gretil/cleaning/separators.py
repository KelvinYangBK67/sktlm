"""Pass 3A v2: normalize explicit source segmentation separators.

Version signature
-----------------
PASS3A_IMPLEMENTATION = "opaque-protected-v2"

The important change from v1 is that protected spans are treated as opaque
semantic units during separator classification. Their *contents* are not
examined or modified, but a separator immediately outside a protected span can
still be normalized.

Examples::

    anitam.(?).bhavati
        -> anitam (?) bhavati

    śraddhād.(.eva.asya.).satya
        -> śraddhād (.eva.asya.) satya

The dots *inside* ``(.eva.asya.)`` remain untouched.

This stage standardizes source-encoded segmentation marks to ASCII spaces. It
does not infer whether a boundary is a word boundary, compound boundary, or
morpheme boundary.

Current execution policy
------------------------
DOT is enabled only for a file whitelist already verified to use dots
systematically as source separators.

HYPHEN uses the same engine, but no real file is enabled yet.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


PASS3A_IMPLEMENTATION = "opaque-protected-v2"

DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pass2_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pass3a_separator_normalized_gretil_iast"
)
DEFAULT_REPORT_DIR = Path(
    "reports/cleaning/generated/pass3a_separators"
)

SUMMARY_FILENAME = "gretil_pass3a_separator_summary.txt"
FILE_AUDIT_FILENAME = "gretil_pass3a_separator_file_audit.csv"
AUTO_FILENAME = "gretil_pass3a_separator_auto.csv"
REVIEW_FILENAME = "gretil_pass3a_separator_review.csv"

DOT_BOUNDARY_FILES = frozenset(
    {
        "1_veda/2_bra/kausibru.txt",
        "1_veda/5_vedang/1_srauta/asvss_u.txt",
        "1_veda/5_vedang/1_srauta/sankhssu.txt",
        "1_veda/5_vedang/2_grhya/sankhgsu.txt",
        "1_veda/5_vedang/2_grhya/asvgs_u.txt",
    }
)

HYPHEN_BOUNDARY_FILES: frozenset[str] = frozenset()

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

Decision = Literal["AUTO", "REVIEW", "IGNORE"]
UnitKind = Literal[
    "EDGE",
    "LEXICAL",
    "PROTECTED",
    "DANDA",
    "DIGIT",
    "SPACE",
    "APOSTROPHE",
    "SEPARATOR",
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
    replacement: str | None = None


@dataclass(frozen=True, slots=True)
class Occurrence:
    path: str
    line_number: int
    column: int
    separator: str
    decision: Decision
    reason: str
    replacement: str
    context: str
    line_before: str
    line_after: str


@dataclass(frozen=True, slots=True)
class DocumentResult:
    text: str
    auto: tuple[Occurrence, ...]
    review: tuple[Occurrence, ...]
    ignored_counts: Counter[str]


@dataclass(frozen=True, slots=True)
class CorpusResult:
    files_processed: int
    target_files: int
    files_changed: int
    auto_dot: int
    auto_hyphen: int
    review_dot: int
    review_hyphen: int


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


def _is_lowercase_lexical(character: str) -> bool:
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
    elif character == "|":
        kind = "DANDA"
    elif character == "'":
        kind = "APOSTROPHE"
    elif character in ".-":
        kind = "SEPARATOR"
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
    separator_index: int,
    intervals: tuple[tuple[int, int], ...],
) -> SemanticUnit:
    """Return the semantic unit immediately left of the separator.

    A protected span ending immediately before the separator is returned as
    one opaque PROTECTED unit instead of exposing its closing bracket.
    """

    if separator_index == 0:
        return SemanticUnit(
            "EDGE",
            0,
            0,
            "",
        )

    protected = _interval_ending_at(
        separator_index,
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
        separator_index - 1,
    )


def _right_unit(
    line: str,
    separator_index: int,
    intervals: tuple[tuple[int, int], ...],
) -> SemanticUnit:
    """Return the semantic unit immediately right of the separator.

    A protected span beginning immediately after the separator is returned as
    one opaque PROTECTED unit instead of exposing its opening bracket.
    """

    next_index = separator_index + 1

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
    unit: SemanticUnit,
) -> bool:
    if unit.kind != "APOSTROPHE":
        return False

    next_index = unit.end
    return (
        next_index < len(line)
        and _is_lowercase_lexical(
            line[next_index]
        )
    )


def _context(
    line: str,
    index: int,
    radius: int = 32,
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


def classify_separator(
    line: str,
    index: int,
    *,
    separator: str,
    enabled: bool,
    protected: tuple[tuple[int, int], ...] | None = None,
) -> Classification:
    """Classify one source separator.

    Protected spans are opaque semantic units. The classifier may normalize a
    separator *outside* them but never a separator *inside* them.
    """

    if separator not in {".", "-"}:
        raise ValueError(
            f"unsupported separator: {separator!r}"
        )

    if not 0 <= index < len(line):
        raise IndexError(index)

    if line[index] != separator:
        raise ValueError(
            "index does not point at requested separator"
        )

    if not enabled:
        return Classification(
            "IGNORE",
            "separator_not_enabled_for_file",
        )

    if protected is None:
        protected = _protected_intervals(
            line
        )

    if _containing_interval(
        index,
        protected,
    ) is not None:
        return Classification(
            "IGNORE",
            "inside_protected_span",
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

    # Numeric material must win over line-edge normalization:
    #     6.28.
    # The final dot sees DIGIT + EDGE and remains untouched.
    if (
        left.kind == "DIGIT"
        or right.kind == "DIGIT"
    ):
        return Classification(
            "IGNORE",
            "adjacent_digit",
        )

    if (
        left.kind == "SEPARATOR"
        or right.kind == "SEPARATOR"
    ):
        return Classification(
            "IGNORE",
            "repeated_or_adjacent_separator",
        )

    # In verified dot-boundary families, a stray leading/trailing dot is just
    # the source separator at a line break. Remove it rather than inserting a
    # leading/trailing space.
    if separator == ".":
        if (
            left.kind == "EDGE"
            and right.kind in {
                "LEXICAL",
                "PROTECTED",
                "DANDA",
            }
        ):
            return Classification(
                "AUTO",
                "leading_edge_separator",
                "",
            )

        if (
            right.kind == "EDGE"
            and left.kind in {
                "LEXICAL",
                "PROTECTED",
                "DANDA",
            }
        ):
            return Classification(
                "AUTO",
                "trailing_edge_separator",
                "",
            )

    # Ordinary source segmentation.
    auto_pairs = {
        ("LEXICAL", "LEXICAL"),
        ("LEXICAL", "PROTECTED"),
        ("PROTECTED", "LEXICAL"),
        ("PROTECTED", "PROTECTED"),
    }

    if separator == ".":
        auto_pairs |= {
            ("LEXICAL", "DANDA"),
            ("DANDA", "LEXICAL"),
            ("PROTECTED", "DANDA"),
            ("DANDA", "PROTECTED"),
        }

    if (
        left.kind,
        right.kind,
    ) in auto_pairs:
        return Classification(
            "AUTO",
            (
                f"{left.kind.lower()}_to_"
                f"{right.kind.lower()}"
            ),
            " ",
        )

    # Source separator before avagraha-bearing material:
    #     anyo-'nyaḥ -> anyo 'nyaḥ
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
        return Classification(
            "AUTO",
            "to_avagraha_lexical",
            " ",
        )

    if (
        left.kind == "SPACE"
        or right.kind == "SPACE"
    ):
        return Classification(
            "REVIEW",
            "adjacent_whitespace",
        )

    if (
        left.kind == "OTHER"
        or right.kind == "OTHER"
    ):
        return Classification(
            "REVIEW",
            "other_symbol_context",
        )

    return Classification(
        "REVIEW",
        (
            f"unclassified_"
            f"{left.kind.lower()}_"
            f"{right.kind.lower()}"
        ),
    )


def normalize_line(
    line: str,
    *,
    path: str,
    line_number: int,
    dot_enabled: bool,
    hyphen_enabled: bool,
) -> tuple[
    str,
    list[Occurrence],
    list[Occurrence],
    Counter[str],
]:
    protected = _protected_intervals(
        line
    )

    decisions: list[
        tuple[
            int,
            str,
            Classification,
        ]
    ] = []

    for index, character in enumerate(
        line
    ):
        if character == ".":
            classification = (
                classify_separator(
                    line,
                    index,
                    separator=".",
                    enabled=dot_enabled,
                    protected=protected,
                )
            )
        elif character == "-":
            classification = (
                classify_separator(
                    line,
                    index,
                    separator="-",
                    enabled=hyphen_enabled,
                    protected=protected,
                )
            )
        else:
            continue

        if (
            classification.reason
            == "separator_not_enabled_for_file"
        ):
            continue

        decisions.append(
            (
                index,
                character,
                classification,
            )
        )

    replacements = {
        index: classification.replacement
        for (
            index,
            _,
            classification,
        ) in decisions
        if (
            classification.decision
            == "AUTO"
            and classification.replacement
            is not None
        )
    }

    if replacements:
        pieces: list[str] = []
        cursor = 0

        for index in sorted(
            replacements
        ):
            pieces.append(
                line[cursor:index]
            )
            pieces.append(
                replacements[index]
                or ""
            )
            cursor = index + 1

        pieces.append(
            line[cursor:]
        )

        normalized_line = "".join(
            pieces
        )
    else:
        normalized_line = line

    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    ignored_counts: Counter[str] = Counter()

    for (
        index,
        separator,
        classification,
    ) in decisions:
        occurrence = Occurrence(
            path=path,
            line_number=line_number,
            column=index + 1,
            separator=separator,
            decision=classification.decision,
            reason=classification.reason,
            replacement=(
                classification.replacement
                or ""
            ),
            context=_context(
                line,
                index,
            ),
            line_before=line,
            line_after=(
                normalized_line
                if classification.decision
                == "AUTO"
                else line
            ),
        )

        if classification.decision == "AUTO":
            auto.append(
                occurrence
            )
        elif classification.decision == "REVIEW":
            review.append(
                occurrence
            )
        else:
            ignored_counts[
                (
                    f"{separator}:"
                    f"{classification.reason}"
                )
            ] += 1

    return (
        normalized_line,
        auto,
        review,
        ignored_counts,
    )


def normalize_document(
    text: str,
    relative_path: str,
) -> DocumentResult:
    normalized_path = (
        relative_path.replace(
            "\\",
            "/",
        )
    )

    dot_enabled = (
        normalized_path
        in DOT_BOUNDARY_FILES
    )
    hyphen_enabled = (
        normalized_path
        in HYPHEN_BOUNDARY_FILES
    )

    if (
        not dot_enabled
        and not hyphen_enabled
    ):
        return DocumentResult(
            text=text,
            auto=(),
            review=(),
            ignored_counts=Counter(),
        )

    output_lines: list[str] = []
    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    ignored_counts: Counter[str] = (
        Counter()
    )

    for line_number, line in enumerate(
        text.split("\n"),
        start=1,
    ):
        (
            normalized_line,
            line_auto,
            line_review,
            line_ignored,
        ) = normalize_line(
            line,
            path=normalized_path,
            line_number=line_number,
            dot_enabled=dot_enabled,
            hyphen_enabled=hyphen_enabled,
        )

        output_lines.append(
            normalized_line
        )
        auto.extend(
            line_auto
        )
        review.extend(
            line_review
        )
        ignored_counts.update(
            line_ignored
        )

    return DocumentResult(
        text="\n".join(
            output_lines
        ),
        auto=tuple(
            auto
        ),
        review=tuple(
            review
        ),
        ignored_counts=(
            ignored_counts
        ),
    )


def _validate_roots(
    input_root: Path,
    output_root: Path,
) -> None:
    source = input_root.resolve()
    destination = output_root.resolve()

    if source == destination:
        raise ValueError(
            "Pass 3A output root must not "
            "equal input root"
        )

    try:
        destination.relative_to(
            source
        )
    except ValueError:
        pass
    else:
        raise ValueError(
            "Pass 3A output root must not "
            "be inside input root"
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
        writer.writerows(
            rows
        )


def _occurrence_row(
    occurrence: Occurrence,
) -> dict[str, Any]:
    return {
        "path": occurrence.path,
        "line_number": (
            occurrence.line_number
        ),
        "column": (
            occurrence.column
        ),
        "separator": (
            occurrence.separator
        ),
        "decision": (
            occurrence.decision
        ),
        "reason": (
            occurrence.reason
        ),
        "replacement": (
            occurrence.replacement
        ),
        "context": (
            occurrence.context
        ),
        "line_before": (
            occurrence.line_before
        ),
        "line_after": (
            occurrence.line_after
        ),
    }


def build_pass3a_candidate(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
) -> CorpusResult:
    if not input_root.is_dir():
        raise FileNotFoundError(
            (
                "Pass 3A input root does "
                f"not exist: {input_root}"
            )
        )

    _validate_roots(
        input_root,
        output_root,
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
            (
                "no .txt files found "
                f"under: {input_root}"
            )
        )

    if output_root.exists():
        shutil.rmtree(
            output_root
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    files_changed = 0
    target_files = 0
    total_input_chars = 0
    total_output_chars = 0

    auto_occurrences: list[
        Occurrence
    ] = []
    review_occurrences: list[
        Occurrence
    ] = []
    file_rows: list[
        dict[str, Any]
    ] = []

    for source_path in files:
        relative_path = (
            source_path.relative_to(
                input_root
            )
        )
        relative_string = (
            relative_path.as_posix()
        )

        raw_bytes = (
            source_path.read_bytes()
        )
        original_text = (
            raw_bytes.decode(
                "utf-8",
                errors="strict",
            )
        )

        total_input_chars += len(
            original_text
        )

        is_target = (
            relative_string
            in DOT_BOUNDARY_FILES
            or relative_string
            in HYPHEN_BOUNDARY_FILES
        )

        if is_target:
            target_files += 1

        result = normalize_document(
            original_text,
            relative_string,
        )

        destination = (
            output_root
            / relative_path
        )
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        changed = bool(
            result.auto
        )

        if changed:
            destination.write_bytes(
                result.text.encode(
                    "utf-8"
                )
            )
            files_changed += 1
            output_text = result.text
        else:
            destination.write_bytes(
                raw_bytes
            )
            output_text = (
                original_text
            )

        total_output_chars += len(
            output_text
        )

        auto_occurrences.extend(
            result.auto
        )
        review_occurrences.extend(
            result.review
        )

        if is_target:
            auto_dot = sum(
                occurrence.separator
                == "."
                for occurrence
                in result.auto
            )
            auto_hyphen = sum(
                occurrence.separator
                == "-"
                for occurrence
                in result.auto
            )
            review_dot = sum(
                occurrence.separator
                == "."
                for occurrence
                in result.review
            )
            review_hyphen = sum(
                occurrence.separator
                == "-"
                for occurrence
                in result.review
            )

            ignored_dot = sum(
                count
                for key, count
                in result.ignored_counts.items()
                if key.startswith(".:")
            )
            ignored_hyphen = sum(
                count
                for key, count
                in result.ignored_counts.items()
                if key.startswith("-:")
            )

            file_rows.append(
                {
                    "path": (
                        relative_string
                    ),
                    "dot_enabled": int(
                        relative_string
                        in DOT_BOUNDARY_FILES
                    ),
                    "hyphen_enabled": int(
                        relative_string
                        in HYPHEN_BOUNDARY_FILES
                    ),
                    "changed": int(
                        changed
                    ),
                    "input_chars": len(
                        original_text
                    ),
                    "output_chars": len(
                        output_text
                    ),
                    "char_delta": (
                        len(output_text)
                        - len(original_text)
                    ),
                    "auto_dot": auto_dot,
                    "auto_hyphen": (
                        auto_hyphen
                    ),
                    "review_dot": (
                        review_dot
                    ),
                    "review_hyphen": (
                        review_hyphen
                    ),
                    "ignored_dot": (
                        ignored_dot
                    ),
                    "ignored_hyphen": (
                        ignored_hyphen
                    ),
                }
            )

    file_rows.sort(
        key=lambda row: (
            -int(
                row["auto_dot"]
            )
            - int(
                row["auto_hyphen"]
            ),
            str(
                row["path"]
            ),
        )
    )

    auto_rows = [
        _occurrence_row(
            occurrence
        )
        for occurrence
        in auto_occurrences
    ]
    review_rows = [
        _occurrence_row(
            occurrence
        )
        for occurrence
        in review_occurrences
    ]

    auto_rows.sort(
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
    review_rows.sort(
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

    _write_csv(
        report_dir
        / FILE_AUDIT_FILENAME,
        (
            "path",
            "dot_enabled",
            "hyphen_enabled",
            "changed",
            "input_chars",
            "output_chars",
            "char_delta",
            "auto_dot",
            "auto_hyphen",
            "review_dot",
            "review_hyphen",
            "ignored_dot",
            "ignored_hyphen",
        ),
        file_rows,
    )

    occurrence_fields = (
        "path",
        "line_number",
        "column",
        "separator",
        "decision",
        "reason",
        "replacement",
        "context",
        "line_before",
        "line_after",
    )

    _write_csv(
        report_dir
        / AUTO_FILENAME,
        occurrence_fields,
        auto_rows,
    )

    _write_csv(
        report_dir
        / REVIEW_FILENAME,
        occurrence_fields,
        review_rows,
    )

    auto_dot = sum(
        occurrence.separator == "."
        for occurrence
        in auto_occurrences
    )
    auto_hyphen = sum(
        occurrence.separator == "-"
        for occurrence
        in auto_occurrences
    )
    review_dot = sum(
        occurrence.separator == "."
        for occurrence
        in review_occurrences
    )
    review_hyphen = sum(
        occurrence.separator == "-"
        for occurrence
        in review_occurrences
    )

    _write_summary(
        report_dir
        / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_processed=len(
            files
        ),
        target_files=target_files,
        files_changed=files_changed,
        input_chars=(
            total_input_chars
        ),
        output_chars=(
            total_output_chars
        ),
        auto_dot=auto_dot,
        auto_hyphen=auto_hyphen,
        review_dot=review_dot,
        review_hyphen=(
            review_hyphen
        ),
    )

    return CorpusResult(
        files_processed=len(
            files
        ),
        target_files=(
            target_files
        ),
        files_changed=(
            files_changed
        ),
        auto_dot=(
            auto_dot
        ),
        auto_hyphen=(
            auto_hyphen
        ),
        review_dot=(
            review_dot
        ),
        review_hyphen=(
            review_hyphen
        ),
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    output_root: Path,
    files_processed: int,
    target_files: int,
    files_changed: int,
    input_chars: int,
    output_chars: int,
    auto_dot: int,
    auto_hyphen: int,
    review_dot: int,
    review_hyphen: int,
) -> None:
    lines = [
        (
            "Formal GRETIL Pass 3A "
            "separator normalization"
        ),
        "=============================================",
        (
            "implementation: "
            f"{PASS3A_IMPLEMENTATION}"
        ),
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        (
            "files_processed: "
            f"{files_processed}"
        ),
        (
            "target_files: "
            f"{target_files}"
        ),
        (
            "files_changed: "
            f"{files_changed}"
        ),
        (
            "input_chars: "
            f"{input_chars}"
        ),
        (
            "output_chars: "
            f"{output_chars}"
        ),
        (
            "char_delta: "
            f"{output_chars - input_chars}"
        ),
        "",
        "AUTO:",
        (
            "  dot_to_space_or_edge_remove: "
            f"{auto_dot}"
        ),
        (
            "  hyphen_to_space: "
            f"{auto_hyphen}"
        ),
        "",
        "REVIEW:",
        f"  dot: {review_dot}",
        (
            "  hyphen: "
            f"{review_hyphen}"
        ),
        "",
        "enabled dot files:",
        *[
            f"  {name}"
            for name
            in sorted(
                DOT_BOUNDARY_FILES
            )
        ],
        "",
        "enabled hyphen files:",
        *(
            [
                f"  {name}"
                for name
                in sorted(
                    HYPHEN_BOUNDARY_FILES
                )
            ]
            or ["  (none)"]
        ),
        "",
        "policy:",
        (
            "  protected spans are "
            "opaque semantic units"
        ),
        (
            "  separators outside protected "
            "spans may be normalized"
        ),
        (
            "  separator characters inside "
            "protected spans are untouched"
        ),
        (
            "  normalize explicit source "
            "segmentation to ASCII space"
        ),
        (
            "  remove verified leading/"
            "trailing dot separators"
        ),
        (
            "  numeric contexts are "
            "never edge-normalized"
        ),
        (
            "  do not infer or repair "
            "linguistic segmentation"
        ),
        "",
        (
            "The Pass 3A input corpus "
            "was not modified."
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
            "Normalize verified source "
            "segmentation separators "
            "(opaque-protected v2)"
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

    args = parser.parse_args(
        argv
    )

    result = build_pass3a_candidate(
        input_root=(
            args.input_root
        ),
        output_root=(
            args.output_root
        ),
        report_dir=(
            args.report_dir
        ),
    )

    print(
        f"implementation: "
        f"{PASS3A_IMPLEMENTATION}"
    )
    print(
        f"processed "
        f"{result.files_processed} "
        f"document(s)"
    )
    print(
        f"target files: "
        f"{result.target_files}"
    )
    print(
        f"changed "
        f"{result.files_changed} "
        f"document(s)"
    )
    print(
        f"AUTO dot: "
        f"{result.auto_dot}"
    )
    print(
        f"AUTO hyphen: "
        f"{result.auto_hyphen}"
    )
    print(
        f"REVIEW dot: "
        f"{result.review_dot}"
    )
    print(
        f"REVIEW hyphen: "
        f"{result.review_hyphen}"
    )


if __name__ == "__main__":
    main()

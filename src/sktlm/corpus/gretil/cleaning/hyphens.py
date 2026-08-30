"""Pass 3B v3: final generic hyphen normalization.

This is a complete rebuild from Pass 3A, not a patch on Pass 3B v2.

It keeps all Pass 3B v2 rules and adds only two final conservative
refinements:

1. TRAILING_HYPHEN_AT_LINE_END_REMOVED
   In whitelisted files other than the two apparatus-heavy exclusions,
   a REVIEW hyphen after lowercase lexical material at physical line end
   is removed:

       indriyārtha-
       -> indriyārtha

   The newline itself remains the boundary. Leading line-edge hyphens are
   deliberately NOT normalized.

2. HYPHEN_BEFORE_APOSTROPHE_SEQUENCE_REMOVED
   In any whitelisted file, a REVIEW form such as:

       yatnā-''dṛta
       -> yatnā''dṛta

   loses only the hyphen when one or more apostrophes are followed by
   lowercase lexical material.

All other REVIEW and NON_SEPARATOR cases remain untouched.

Input::

    data/intermediate/gretil/pass3a_separator_normalized_gretil_iast

Output::

    data/intermediate/gretil/pass3b_v3_hyphen_normalized_gretil_iast

Reports::

    reports/cleaning/generated/pass3b_hyphen_normalization_v3/
        gretil_pass3b_v3_hyphen_summary.txt
        gretil_pass3b_v3_hyphen_file_audit.csv
        gretil_pass3b_v3_hyphen_auto.csv
        gretil_pass3b_v3_hyphen_review.csv
        gretil_pass3b_v3_hyphen_nonseparator.csv
"""

from __future__ import annotations

import argparse
import csv
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.corpus.gretil.cleaning.hyphen_inventory import (
    PROTECTED_SPAN_RE,
    classify_hyphen,
)


IMPLEMENTATION = "hyphen-executor-v3"

DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pass3a_separator_normalized_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pass3b_v3_hyphen_normalized_gretil_iast"
)
DEFAULT_REPORT_DIR = Path(
    "reports/cleaning/generated/pass3b_hyphen_normalization_v3"
)

SUMMARY_FILENAME = "gretil_pass3b_v3_hyphen_summary.txt"
FILE_AUDIT_FILENAME = "gretil_pass3b_v3_hyphen_file_audit.csv"
AUTO_FILENAME = "gretil_pass3b_v3_hyphen_auto.csv"
REVIEW_FILENAME = "gretil_pass3b_v3_hyphen_review.csv"
NONSEPARATOR_FILENAME = "gretil_pass3b_v3_hyphen_nonseparator.csv"


HYPHEN_BOUNDARY_FILES = frozenset(
    {
        # Śatapatha Brāhmaṇa family
        "1_veda/2_bra/satapath/sb_01_u.txt",
        "1_veda/2_bra/satapath/sb_02_u.txt",
        "1_veda/2_bra/satapath/sb_03_u.txt",
        "1_veda/2_bra/satapath/sb_04_u.txt",
        "1_veda/2_bra/satapath/sb_05_u.txt",
        "1_veda/2_bra/satapath/sb_06_u.txt",
        "1_veda/2_bra/satapath/sb_07_u.txt",
        "1_veda/2_bra/satapath/sb_08_u.txt",
        "1_veda/2_bra/satapath/sb_09_u.txt",
        "1_veda/2_bra/satapath/sb_10_u.txt",
        "1_veda/2_bra/satapath/sb_11_u.txt",
        "1_veda/2_bra/satapath/sb_13_u.txt",
        "1_veda/2_bra/satapath/sb_14_u.txt",

        # Bhāgavata Purāṇa family
        "3_purana/bhagp/bhp_03u.txt",
        "3_purana/bhagp/bhp_04u.txt",
        "3_purana/bhagp/bhp_05u.txt",
        "3_purana/bhagp/bhp_09u.txt",
        "3_purana/bhagp/bhp_10u.txt",
        "3_purana/bhagp/bhp_11u.txt",
        "3_purana/bhagp/bhp_12u.txt",

        # Individually verified files
        "4_rellit/vaisn/vaimp__u.txt",
        "4_rellit/vaisn/astavgpu.txt",
        "4_rellit/saiva/kubjt_pu.txt",
        "4_rellit/saiva/pasupspu.txt",
        "4_rellit/buddh/mhvastuu.txt",
        "4_rellit/buddh/vinv08_u.txt",
        "4_rellit/buddh/vinv11_u.txt",
        "5_poetry/1_chandas/jvrtmspu.txt",
        "5_poetry/2_kavya/bhattiku.txt",
        "5_poetry/5_subhas/bharst_u.txt",
        "6_sastra/3_phil/yoga/hathyopu.txt",
        "6_sastra/7_ayur/vagaah_u.txt",
    }
)


# Apparatus-heavy files excluded from the two more permissive physical-layout
# refinements. They remain eligible for general lexical separator cleanup and
# the apostrophe-specific rules.
LAYOUT_REFINEMENT_EXCLUSIONS = frozenset(
    {
        "4_rellit/vaisn/vaimp__u.txt",
        "6_sastra/7_ayur/vagaah_u.txt",
    }
)

LAYOUT_REFINEMENT_FILES = frozenset(
    HYPHEN_BOUNDARY_FILES
    - LAYOUT_REFINEMENT_EXCLUSIONS
)


@dataclass(frozen=True, slots=True)
class Replacement:
    index: int
    replacement: str
    rule: str
    original_decision: str
    original_reason: str


@dataclass(frozen=True, slots=True)
class Occurrence:
    path: str
    line_number: int
    column: int
    decision: str
    reason: str
    rule: str
    replacement: str
    context: str
    line_before: str
    line_after: str


@dataclass(frozen=True, slots=True)
class DocumentResult:
    text: str
    auto: tuple[Occurrence, ...]
    review: tuple[Occurrence, ...]
    non_separator: tuple[Occurrence, ...]


@dataclass(frozen=True, slots=True)
class CorpusResult:
    files_processed: int
    whitelist_files: int
    present_whitelist_files: int
    missing_whitelist_files: int
    files_changed: int
    general_separator_replacements: int
    redundant_space_replacements: int
    apostrophe_replacements: int
    trailing_edge_replacements: int
    apostrophe_sequence_replacements: int
    review_occurrences: int
    non_separator_occurrences: int


def _protected_intervals(
    line: str,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (match.start(), match.end())
        for match in PROTECTED_SPAN_RE.finditer(line)
    )


def _inside_protected(
    index: int,
    intervals: tuple[tuple[int, int], ...],
) -> bool:
    return any(
        start <= index < end
        for start, end in intervals
    )


def _is_lowercase_lexical(
    character: str,
) -> bool:
    return (
        character.isalpha()
        and character.lower() == character
    )


def _previous_character(
    line: str,
    index: int,
) -> str | None:
    if index <= 0:
        return None
    return line[index - 1]


def _next_nonspace(
    line: str,
    index: int,
) -> tuple[int, str] | None:
    i = index + 1

    if (
        i >= len(line)
        or not line[i].isspace()
    ):
        return None

    while (
        i < len(line)
        and line[i].isspace()
    ):
        i += 1

    if i >= len(line):
        return None

    return i, line[i]


def _matches_redundant_hyphen_before_space(
    line: str,
    index: int,
    *,
    path: str,
    protected: tuple[tuple[int, int], ...],
) -> bool:
    """Recognize ``lexical- whitespace lexical``."""

    if path not in LAYOUT_REFINEMENT_FILES:
        return False

    if _inside_protected(
        index,
        protected,
    ):
        return False

    left = _previous_character(
        line,
        index,
    )

    if (
        left is None
        or not _is_lowercase_lexical(
            left
        )
    ):
        return False

    next_item = _next_nonspace(
        line,
        index,
    )

    if next_item is None:
        return False

    next_index, next_character = (
        next_item
    )

    if not _is_lowercase_lexical(
        next_character
    ):
        return False

    if _inside_protected(
        next_index,
        protected,
    ):
        return False

    return True


def _matches_apostrophe_hyphen_lexical(
    line: str,
    index: int,
    *,
    protected: tuple[tuple[int, int], ...],
) -> bool:
    """Recognize ``'-x`` and remove only the hyphen."""

    if _inside_protected(
        index,
        protected,
    ):
        return False

    if (
        index <= 0
        or line[index - 1] != "'"
    ):
        return False

    next_index = index + 1

    return (
        next_index < len(line)
        and _is_lowercase_lexical(
            line[next_index]
        )
        and not _inside_protected(
            next_index,
            protected,
        )
    )


def _matches_trailing_hyphen_at_line_end(
    line: str,
    index: int,
    *,
    path: str,
    protected: tuple[tuple[int, int], ...],
) -> bool:
    """Recognize ``lexical-`` where the hyphen is the physical line end."""

    if path not in LAYOUT_REFINEMENT_FILES:
        return False

    if _inside_protected(
        index,
        protected,
    ):
        return False

    if index != len(line) - 1:
        return False

    left = _previous_character(
        line,
        index,
    )

    return (
        left is not None
        and _is_lowercase_lexical(
            left
        )
    )


def _matches_hyphen_before_apostrophe_sequence(
    line: str,
    index: int,
    *,
    protected: tuple[tuple[int, int], ...],
) -> bool:
    """Recognize ``lexical-''x`` (one or more apostrophes before lexical x)."""

    if _inside_protected(
        index,
        protected,
    ):
        return False

    left = _previous_character(
        line,
        index,
    )

    if (
        left is None
        or not _is_lowercase_lexical(
            left
        )
    ):
        return False

    i = index + 1
    apostrophes = 0

    while (
        i < len(line)
        and line[i] == "'"
    ):
        apostrophes += 1
        i += 1

    if apostrophes == 0:
        return False

    return (
        i < len(line)
        and _is_lowercase_lexical(
            line[i]
        )
        and not _inside_protected(
            i,
            protected,
        )
    )


def _context(
    line: str,
    index: int,
    radius: int = 42,
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


def _classify_replacement(
    line: str,
    index: int,
    *,
    path: str,
    protected: tuple[tuple[int, int], ...],
) -> tuple[
    Replacement | None,
    str,
    str,
]:
    classification, _, _ = (
        classify_hyphen(
            line,
            index,
            protected=protected,
        )
    )

    if (
        classification.decision
        == "SEPARATOR"
    ):
        return (
            Replacement(
                index=index,
                replacement=" ",
                rule=(
                    "general_separator_to_space"
                ),
                original_decision=(
                    classification.decision
                ),
                original_reason=(
                    classification.reason
                ),
            ),
            classification.decision,
            classification.reason,
        )

    # Explicit NON_SEPARATOR remains immutable.
    if (
        classification.decision
        != "REVIEW"
    ):
        return (
            None,
            classification.decision,
            classification.reason,
        )

    if _matches_apostrophe_hyphen_lexical(
        line,
        index,
        protected=protected,
    ):
        return (
            Replacement(
                index=index,
                replacement="",
                rule=(
                    "apostrophe_hyphen_removed"
                ),
                original_decision=(
                    classification.decision
                ),
                original_reason=(
                    classification.reason
                ),
            ),
            classification.decision,
            classification.reason,
        )

    if _matches_hyphen_before_apostrophe_sequence(
        line,
        index,
        protected=protected,
    ):
        return (
            Replacement(
                index=index,
                replacement="",
                rule=(
                    "hyphen_before_apostrophe_sequence_removed"
                ),
                original_decision=(
                    classification.decision
                ),
                original_reason=(
                    classification.reason
                ),
            ),
            classification.decision,
            classification.reason,
        )

    if _matches_redundant_hyphen_before_space(
        line,
        index,
        path=path,
        protected=protected,
    ):
        return (
            Replacement(
                index=index,
                replacement="",
                rule=(
                    "redundant_hyphen_before_space_removed"
                ),
                original_decision=(
                    classification.decision
                ),
                original_reason=(
                    classification.reason
                ),
            ),
            classification.decision,
            classification.reason,
        )

    if _matches_trailing_hyphen_at_line_end(
        line,
        index,
        path=path,
        protected=protected,
    ):
        return (
            Replacement(
                index=index,
                replacement="",
                rule=(
                    "trailing_hyphen_at_line_end_removed"
                ),
                original_decision=(
                    classification.decision
                ),
                original_reason=(
                    classification.reason
                ),
            ),
            classification.decision,
            classification.reason,
        )

    return (
        None,
        classification.decision,
        classification.reason,
    )


def _apply_replacements(
    line: str,
    replacements: list[Replacement],
) -> str:
    if not replacements:
        return line

    by_index = {
        item.index: item.replacement
        for item in replacements
    }

    pieces: list[str] = []

    for index, character in enumerate(
        line
    ):
        if index in by_index:
            pieces.append(
                by_index[index]
            )
        else:
            pieces.append(
                character
            )

    return "".join(
        pieces
    )


def normalize_line(
    line: str,
    *,
    path: str,
    line_number: int,
) -> tuple[
    str,
    list[Occurrence],
    list[Occurrence],
    list[Occurrence],
]:
    protected = _protected_intervals(
        line
    )

    replacement_by_index: dict[
        int,
        Replacement,
    ] = {}

    residual: list[
        tuple[int, str, str]
    ] = []

    for index, character in enumerate(
        line
    ):
        if character != "-":
            continue

        (
            replacement,
            decision,
            reason,
        ) = _classify_replacement(
            line,
            index,
            path=path,
            protected=protected,
        )

        if replacement is not None:
            replacement_by_index[
                index
            ] = replacement
        else:
            residual.append(
                (
                    index,
                    decision,
                    reason,
                )
            )

    normalized_line = (
        _apply_replacements(
            line,
            list(
                replacement_by_index.values()
            ),
        )
    )

    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    non_separator: list[
        Occurrence
    ] = []

    for index in sorted(
        replacement_by_index
    ):
        replacement = (
            replacement_by_index[index]
        )

        auto.append(
            Occurrence(
                path=path,
                line_number=line_number,
                column=index + 1,
                decision="AUTO",
                reason=(
                    replacement.original_reason
                ),
                rule=(
                    replacement.rule
                ),
                replacement=(
                    replacement.replacement
                ),
                context=_context(
                    line,
                    index,
                ),
                line_before=line,
                line_after=(
                    normalized_line
                ),
            )
        )

    for (
        index,
        decision,
        reason,
    ) in residual:
        occurrence = Occurrence(
            path=path,
            line_number=line_number,
            column=index + 1,
            decision=decision,
            reason=reason,
            rule="",
            replacement="",
            context=_context(
                line,
                index,
            ),
            line_before=line,
            line_after=line,
        )

        if decision == "REVIEW":
            review.append(
                occurrence
            )
        else:
            non_separator.append(
                occurrence
            )

    return (
        normalized_line,
        auto,
        review,
        non_separator,
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

    if (
        normalized_path
        not in HYPHEN_BOUNDARY_FILES
    ):
        return DocumentResult(
            text=text,
            auto=(),
            review=(),
            non_separator=(),
        )

    output_lines: list[str] = []
    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    non_separator: list[
        Occurrence
    ] = []

    for line_number, line in enumerate(
        text.split("\n"),
        start=1,
    ):
        (
            normalized_line,
            line_auto,
            line_review,
            line_non_separator,
        ) = normalize_line(
            line,
            path=normalized_path,
            line_number=line_number,
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
        non_separator.extend(
            line_non_separator
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
        non_separator=tuple(
            non_separator
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
            "Pass 3B v3 output root must not equal input root"
        )

    try:
        destination.relative_to(
            source
        )
    except ValueError:
        pass
    else:
        raise ValueError(
            "Pass 3B v3 output root must not be inside input root"
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
        "decision": (
            occurrence.decision
        ),
        "reason": (
            occurrence.reason
        ),
        "rule": occurrence.rule,
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


def build_pass3b_v3_candidate(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
    require_all_targets: bool = False,
) -> CorpusResult:
    if not input_root.is_dir():
        raise FileNotFoundError(
            f"Pass 3B v3 input root does not exist: {input_root}"
        )

    _validate_roots(
        input_root,
        output_root,
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

    present_paths = {
        path.relative_to(
            input_root
        ).as_posix()
        for path in files
    }

    missing_targets = sorted(
        HYPHEN_BOUNDARY_FILES
        - present_paths
    )

    if (
        require_all_targets
        and missing_targets
    ):
        formatted = "\n".join(
            f"  {path}"
            for path in missing_targets
        )
        raise RuntimeError(
            "hyphen whitelist contains paths "
            "missing from the input corpus:\n"
            f"{formatted}"
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
    all_auto: list[Occurrence] = []
    all_review: list[Occurrence] = []
    all_non_separator: list[
        Occurrence
    ] = []
    file_rows: list[
        dict[str, Any]
    ] = []

    total_input_chars = 0
    total_output_chars = 0

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
            in HYPHEN_BOUNDARY_FILES
        )

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
            output_text = (
                result.text
            )
            files_changed += 1
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

        all_auto.extend(
            result.auto
        )
        all_review.extend(
            result.review
        )
        all_non_separator.extend(
            result.non_separator
        )

        if is_target:
            rule_counts = Counter(
                occurrence.rule
                for occurrence
                in result.auto
            )

            reason_counts = Counter(
                occurrence.reason
                for occurrence in (
                    *result.auto,
                    *result.review,
                    *result.non_separator,
                )
            )

            file_rows.append(
                {
                    "path": (
                        relative_string
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
                    "general_separator": (
                        rule_counts[
                            "general_separator_to_space"
                        ]
                    ),
                    "redundant_space": (
                        rule_counts[
                            "redundant_hyphen_before_space_removed"
                        ]
                    ),
                    "apostrophe": (
                        rule_counts[
                            "apostrophe_hyphen_removed"
                        ]
                    ),
                    "trailing_edge": (
                        rule_counts[
                            "trailing_hyphen_at_line_end_removed"
                        ]
                    ),
                    "apostrophe_sequence": (
                        rule_counts[
                            "hyphen_before_apostrophe_sequence_removed"
                        ]
                    ),
                    "review": len(
                        result.review
                    ),
                    "non_separator": len(
                        result.non_separator
                    ),
                    "total_hyphens": (
                        len(result.auto)
                        + len(result.review)
                        + len(
                            result.non_separator
                        )
                    ),
                    "top_reasons": " ".join(
                        f"{reason}={count}"
                        for reason, count
                        in reason_counts.most_common(
                            8
                        )
                    ),
                }
            )

    file_rows.sort(
        key=lambda row: (
            -(
                int(row["general_separator"])
                + int(row["redundant_space"])
                + int(row["apostrophe"])
                + int(row["trailing_edge"])
                + int(row["apostrophe_sequence"])
            ),
            str(row["path"]),
        )
    )

    occurrence_fields = (
        "path",
        "line_number",
        "column",
        "decision",
        "reason",
        "rule",
        "replacement",
        "context",
        "line_before",
        "line_after",
    )

    auto_rows = [
        _occurrence_row(
            occurrence
        )
        for occurrence in all_auto
    ]
    review_rows = [
        _occurrence_row(
            occurrence
        )
        for occurrence
        in all_review
    ]
    nonseparator_rows = [
        _occurrence_row(
            occurrence
        )
        for occurrence
        in all_non_separator
    ]

    for rows in (
        auto_rows,
        review_rows,
        nonseparator_rows,
    ):
        rows.sort(
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
            "changed",
            "input_chars",
            "output_chars",
            "char_delta",
            "general_separator",
            "redundant_space",
            "apostrophe",
            "trailing_edge",
            "apostrophe_sequence",
            "review",
            "non_separator",
            "total_hyphens",
            "top_reasons",
        ),
        file_rows,
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
    _write_csv(
        report_dir
        / NONSEPARATOR_FILENAME,
        occurrence_fields,
        nonseparator_rows,
    )

    rule_counts = Counter(
        occurrence.rule
        for occurrence
        in all_auto
    )

    _write_summary(
        report_dir
        / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_processed=len(
            files
        ),
        present_whitelist_files=len(
            HYPHEN_BOUNDARY_FILES
            & present_paths
        ),
        missing_targets=(
            missing_targets
        ),
        files_changed=(
            files_changed
        ),
        input_chars=(
            total_input_chars
        ),
        output_chars=(
            total_output_chars
        ),
        rule_counts=(
            rule_counts
        ),
        review_occurrences=len(
            all_review
        ),
        non_separator_occurrences=len(
            all_non_separator
        ),
    )

    return CorpusResult(
        files_processed=len(
            files
        ),
        whitelist_files=len(
            HYPHEN_BOUNDARY_FILES
        ),
        present_whitelist_files=len(
            HYPHEN_BOUNDARY_FILES
            & present_paths
        ),
        missing_whitelist_files=len(
            missing_targets
        ),
        files_changed=(
            files_changed
        ),
        general_separator_replacements=(
            rule_counts[
                "general_separator_to_space"
            ]
        ),
        redundant_space_replacements=(
            rule_counts[
                "redundant_hyphen_before_space_removed"
            ]
        ),
        apostrophe_replacements=(
            rule_counts[
                "apostrophe_hyphen_removed"
            ]
        ),
        trailing_edge_replacements=(
            rule_counts[
                "trailing_hyphen_at_line_end_removed"
            ]
        ),
        apostrophe_sequence_replacements=(
            rule_counts[
                "hyphen_before_apostrophe_sequence_removed"
            ]
        ),
        review_occurrences=len(
            all_review
        ),
        non_separator_occurrences=len(
            all_non_separator
        ),
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    output_root: Path,
    files_processed: int,
    present_whitelist_files: int,
    missing_targets: list[str],
    files_changed: int,
    input_chars: int,
    output_chars: int,
    rule_counts: Counter[str],
    review_occurrences: int,
    non_separator_occurrences: int,
) -> None:
    total_auto = sum(
        rule_counts.values()
    )

    lines = [
        "Formal GRETIL Pass 3B v3 hyphen normalization",
        "=============================================",
        (
            "implementation: "
            f"{IMPLEMENTATION}"
        ),
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        (
            "files_processed: "
            f"{files_processed}"
        ),
        (
            "whitelist_files: "
            f"{len(HYPHEN_BOUNDARY_FILES)}"
        ),
        (
            "present_whitelist_files: "
            f"{present_whitelist_files}"
        ),
        (
            "missing_whitelist_files: "
            f"{len(missing_targets)}"
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
            "  general_separator_to_space: "
            f"{rule_counts['general_separator_to_space']}"
        ),
        (
            "  redundant_hyphen_before_space_removed: "
            f"{rule_counts['redundant_hyphen_before_space_removed']}"
        ),
        (
            "  apostrophe_hyphen_removed: "
            f"{rule_counts['apostrophe_hyphen_removed']}"
        ),
        (
            "  trailing_hyphen_at_line_end_removed: "
            f"{rule_counts['trailing_hyphen_at_line_end_removed']}"
        ),
        (
            "  hyphen_before_apostrophe_sequence_removed: "
            f"{rule_counts['hyphen_before_apostrophe_sequence_removed']}"
        ),
        (
            "  total_auto: "
            f"{total_auto}"
        ),
        "",
        "untouched:",
        (
            "  review: "
            f"{review_occurrences}"
        ),
        (
            "  non_separator: "
            f"{non_separator_occurrences}"
        ),
        "",
        "layout-refinement exclusions:",
        *[
            f"  {item}"
            for item in sorted(
                LAYOUT_REFINEMENT_EXCLUSIONS
            )
        ],
        "",
        "policy:",
        (
            "  rebuild completely from Pass 3A"
        ),
        (
            "  generic hyphen cleanup ends after this pass"
        ),
        (
            "  classifier SEPARATOR -> ASCII space"
        ),
        (
            "  redundant lexical-<space>lexical drops only hyphen"
        ),
        (
            "  apostrophe-adjacent residual forms drop only hyphen"
        ),
        (
            "  trailing lexical hyphen at physical line end drops only hyphen"
        ),
        (
            "  leading line-edge hyphens remain untouched"
        ),
        (
            "  vaimp and vagaah remain excluded from layout refinements"
        ),
        (
            "  remaining REVIEW/NON_SEPARATOR cases require source-specific handling"
        ),
        "",
        "missing whitelist paths:",
        *(
            [
                f"  {item}"
                for item in missing_targets
            ]
            or ["  (none)"]
        ),
        "",
        (
            "The Pass 3B v3 input corpus "
            "was not modified."
        ),
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


def main(
    argv: list[str] | None = None,
) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Final generic hyphen normalization "
            "before source-specific cleanup"
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
    parser.add_argument(
        "--require-all-targets",
        action="store_true",
    )

    args = parser.parse_args(
        argv
    )

    result = build_pass3b_v3_candidate(
        input_root=(
            args.input_root
        ),
        output_root=(
            args.output_root
        ),
        report_dir=(
            args.report_dir
        ),
        require_all_targets=(
            args.require_all_targets
        ),
    )

    print(
        f"implementation: "
        f"{IMPLEMENTATION}"
    )
    print(
        f"processed "
        f"{result.files_processed} "
        f"document(s)"
    )
    print(
        f"whitelist files: "
        f"{result.whitelist_files}"
    )
    print(
        f"present whitelist files: "
        f"{result.present_whitelist_files}"
    )
    print(
        f"missing whitelist files: "
        f"{result.missing_whitelist_files}"
    )
    print(
        f"changed "
        f"{result.files_changed} "
        f"document(s)"
    )
    print(
        "general separator -> space: "
        f"{result.general_separator_replacements}"
    )
    print(
        "redundant '- ' removed: "
        f"{result.redundant_space_replacements}"
    )
    print(
        "apostrophe-hyphen removed: "
        f"{result.apostrophe_replacements}"
    )
    print(
        "trailing line-edge hyphen removed: "
        f"{result.trailing_edge_replacements}"
    )
    print(
        "hyphen before apostrophe sequence removed: "
        f"{result.apostrophe_sequence_replacements}"
    )
    print(
        f"REVIEW untouched: "
        f"{result.review_occurrences}"
    )
    print(
        f"NON_SEPARATOR untouched: "
        f"{result.non_separator_occurrences}"
    )


if __name__ == "__main__":
    main()

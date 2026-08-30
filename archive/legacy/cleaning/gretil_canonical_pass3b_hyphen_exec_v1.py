"""Pass 3B v1: execute verified hyphen-separator normalization.

This stage consumes the Pass 3A candidate and normalizes only hyphens that:

1. occur in an explicitly whitelisted source file; and
2. are classified as SEPARATOR by the same dry-run classifier used in the
   hyphen inventory.

A SEPARATOR hyphen is replaced by one ASCII space. No linguistic subtype is
assigned: word, compound, and other source-encoded segmentation boundaries are
all standardized to the same canonical separator.

NON_SEPARATOR and REVIEW hyphens are never modified.

Input::

    data/canonical_candidate/pass3a_separator_normalized_gretil_iast

Output::

    data/canonical_candidate/pass3b_hyphen_normalized_gretil_iast

Reports::

    data/_reports/pass3b_hyphen_normalization/
        gretil_pass3b_hyphen_summary.txt
        gretil_pass3b_hyphen_file_audit.csv
        gretil_pass3b_hyphen_auto.csv
        gretil_pass3b_hyphen_review.csv
        gretil_pass3b_hyphen_nonseparator.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.data.gretil_canonical_hyphen_inventory_v1 import (
    PROTECTED_SPAN_RE,
    classify_hyphen,
)


IMPLEMENTATION = "hyphen-executor-v1"

DEFAULT_INPUT_ROOT = Path(
    "data/canonical_candidate/pass3a_separator_normalized_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/canonical_candidate/pass3b_hyphen_normalized_gretil_iast"
)
DEFAULT_REPORT_DIR = Path(
    "data/_reports/pass3b_hyphen_normalization"
)

SUMMARY_FILENAME = "gretil_pass3b_hyphen_summary.txt"
FILE_AUDIT_FILENAME = "gretil_pass3b_hyphen_file_audit.csv"
AUTO_FILENAME = "gretil_pass3b_hyphen_auto.csv"
REVIEW_FILENAME = "gretil_pass3b_hyphen_review.csv"
NONSEPARATOR_FILENAME = "gretil_pass3b_hyphen_nonseparator.csv"


HYPHEN_BOUNDARY_FILES = frozenset(
    {
        # Śatapatha Brāhmaṇa source family
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

        # Bhāgavata Purāṇa source family
        "3_purana/bhagp/bhp_03u.txt",
        "3_purana/bhagp/bhp_04u.txt",
        "3_purana/bhagp/bhp_05u.txt",
        "3_purana/bhagp/bhp_09u.txt",
        "3_purana/bhagp/bhp_10u.txt",
        "3_purana/bhagp/bhp_11u.txt",
        "3_purana/bhagp/bhp_12u.txt",

        # Individually high-confidence files
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


@dataclass(frozen=True, slots=True)
class Occurrence:
    path: str
    line_number: int
    column: int
    decision: str
    reason: str
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
    auto_replacements: int
    review_occurrences: int
    non_separator_occurrences: int


def _protected_intervals(
    line: str,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (match.start(), match.end())
        for match in PROTECTED_SPAN_RE.finditer(line)
    )


def _context(
    line: str,
    index: int,
    radius: int = 38,
) -> str:
    start = max(0, index - radius)
    end = min(len(line), index + radius + 1)
    return line[start:end]


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
    """Normalize SEPARATOR hyphens on one whitelisted line."""

    protected = _protected_intervals(line)

    decisions: list[
        tuple[int, str, str]
    ] = []

    for index, character in enumerate(line):
        if character != "-":
            continue

        classification, _, _ = classify_hyphen(
            line,
            index,
            protected=protected,
        )

        decisions.append(
            (
                index,
                classification.decision,
                classification.reason,
            )
        )

    auto_positions = {
        index
        for index, decision, _
        in decisions
        if decision == "SEPARATOR"
    }

    if auto_positions:
        characters = list(line)

        for index in auto_positions:
            characters[index] = " "

        normalized_line = "".join(characters)
    else:
        normalized_line = line

    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    non_separator: list[Occurrence] = []

    for index, decision, reason in decisions:
        occurrence = Occurrence(
            path=path,
            line_number=line_number,
            column=index + 1,
            decision=decision,
            reason=reason,
            context=_context(line, index),
            line_before=line,
            line_after=(
                normalized_line
                if decision == "SEPARATOR"
                else line
            ),
        )

        if decision == "SEPARATOR":
            auto.append(occurrence)
        elif decision == "REVIEW":
            review.append(occurrence)
        else:
            non_separator.append(occurrence)

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
    """Normalize one document if and only if it is whitelisted."""

    normalized_path = relative_path.replace(
        "\\",
        "/",
    )

    if normalized_path not in HYPHEN_BOUNDARY_FILES:
        return DocumentResult(
            text=text,
            auto=(),
            review=(),
            non_separator=(),
        )

    output_lines: list[str] = []
    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    non_separator: list[Occurrence] = []

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
        text="\n".join(output_lines),
        auto=tuple(auto),
        review=tuple(review),
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
            "Pass 3B output root must not equal input root"
        )

    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError(
            "Pass 3B output root must not be inside input root"
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


def _occurrence_row(
    occurrence: Occurrence,
) -> dict[str, Any]:
    return {
        "path": occurrence.path,
        "line_number": occurrence.line_number,
        "column": occurrence.column,
        "decision": occurrence.decision,
        "reason": occurrence.reason,
        "context": occurrence.context,
        "line_before": occurrence.line_before,
        "line_after": occurrence.line_after,
    }


def build_pass3b_candidate(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
    require_all_targets: bool = False,
) -> CorpusResult:
    """Build the hyphen-normalized candidate corpus."""

    if not input_root.is_dir():
        raise FileNotFoundError(
            f"Pass 3B input root does not exist: {input_root}"
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
        shutil.rmtree(output_root)

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    files_changed = 0
    all_auto: list[Occurrence] = []
    all_review: list[Occurrence] = []
    all_non_separator: list[Occurrence] = []
    file_rows: list[dict[str, Any]] = []

    total_input_chars = 0
    total_output_chars = 0

    for source_path in files:
        relative_path = source_path.relative_to(
            input_root
        )
        relative_string = relative_path.as_posix()

        raw_bytes = source_path.read_bytes()
        original_text = raw_bytes.decode(
            "utf-8",
            errors="strict",
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
            output_text = result.text
            files_changed += 1
        else:
            # Non-targets and target files without SEPARATOR hits remain
            # byte-identical.
            destination.write_bytes(
                raw_bytes
            )
            output_text = original_text

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
                    "path": relative_string,
                    "changed": int(changed),
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
                    "auto": len(
                        result.auto
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
            -int(row["auto"]),
            str(row["path"]),
        )
    )

    occurrence_fields = (
        "path",
        "line_number",
        "column",
        "decision",
        "reason",
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
        for occurrence in all_review
    ]
    non_separator_rows = [
        _occurrence_row(
            occurrence
        )
        for occurrence
        in all_non_separator
    ]

    for rows in (
        auto_rows,
        review_rows,
        non_separator_rows,
    ):
        rows.sort(
            key=lambda row: (
                str(row["path"]),
                int(row["line_number"]),
                int(row["column"]),
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
            "auto",
            "review",
            "non_separator",
            "total_hyphens",
            "top_reasons",
        ),
        file_rows,
    )

    _write_csv(
        report_dir / AUTO_FILENAME,
        occurrence_fields,
        auto_rows,
    )

    _write_csv(
        report_dir / REVIEW_FILENAME,
        occurrence_fields,
        review_rows,
    )

    _write_csv(
        report_dir
        / NONSEPARATOR_FILENAME,
        occurrence_fields,
        non_separator_rows,
    )

    _write_summary(
        report_dir
        / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_processed=len(files),
        present_whitelist_files=(
            len(
                HYPHEN_BOUNDARY_FILES
                & present_paths
            )
        ),
        missing_targets=(
            missing_targets
        ),
        files_changed=files_changed,
        input_chars=total_input_chars,
        output_chars=total_output_chars,
        auto_replacements=len(
            all_auto
        ),
        review_occurrences=len(
            all_review
        ),
        non_separator_occurrences=len(
            all_non_separator
        ),
    )

    return CorpusResult(
        files_processed=len(files),
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
        files_changed=files_changed,
        auto_replacements=len(
            all_auto
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
    auto_replacements: int,
    review_occurrences: int,
    non_separator_occurrences: int,
) -> None:
    lines = [
        "Formal GRETIL Pass 3B hyphen normalization",
        "==========================================",
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
        "classification within whitelisted files:",
        (
            "  separator_to_space: "
            f"{auto_replacements}"
        ),
        (
            "  review_untouched: "
            f"{review_occurrences}"
        ),
        (
            "  non_separator_untouched: "
            f"{non_separator_occurrences}"
        ),
        "",
        "policy:",
        (
            "  only explicitly whitelisted "
            "source files are eligible"
        ),
        (
            "  only classifier SEPARATOR "
            "hyphens are replaced"
        ),
        (
            "  SEPARATOR hyphen -> ASCII space"
        ),
        (
            "  REVIEW and NON_SEPARATOR "
            "hyphens are preserved"
        ),
        (
            "  no distinction is made between "
            "word and compound boundary subtype"
        ),
        (
            "  non-whitelisted files remain "
            "byte-identical"
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
        "whitelist:",
        *[
            f"  {item}"
            for item in sorted(
                HYPHEN_BOUNDARY_FILES
            )
        ],
        "",
        (
            "The Pass 3B input corpus "
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
            "Normalize verified source-separator "
            "hyphens to ASCII spaces"
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
        help=(
            "fail if any whitelisted file is "
            "missing from the input corpus"
        ),
    )

    args = parser.parse_args(argv)

    result = build_pass3b_candidate(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
        require_all_targets=(
            args.require_all_targets
        ),
    )

    print(
        f"implementation: {IMPLEMENTATION}"
    )
    print(
        f"processed {result.files_processed} document(s)"
    )
    print(
        f"whitelist files: {result.whitelist_files}"
    )
    print(
        "present whitelist files: "
        f"{result.present_whitelist_files}"
    )
    print(
        "missing whitelist files: "
        f"{result.missing_whitelist_files}"
    )
    print(
        f"changed {result.files_changed} document(s)"
    )
    print(
        f"SEPARATOR -> space: "
        f"{result.auto_replacements}"
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

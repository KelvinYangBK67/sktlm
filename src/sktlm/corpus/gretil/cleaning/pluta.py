"""Conservative Vedic pluta normalization for the GRETIL canonical corpus.

Policy
------

General high-confidence pluta spellings are normalized by removing only the
pluta duration marker ``3`` while preserving the written vowel:

    ā3  -> ā
    ī3  -> ī
    ū3  -> ū
    ṝ3  -> ṝ
    ḹ3  -> ḹ
    e3  -> e
    o3  -> o
    ai3 -> ai
    au3 -> au

Short-vowel-plus-3 spellings are NOT normalized generically:

    a3
    i3
    u3
    ṛ3
    ḷ3

They remain review-only unless an occurrence has been independently verified
and encoded as an explicit source-specific exception.

Currently verified exceptions:

    1_veda/2_bra/satapath/sb_10_u.txt
        vratāni3 -> vratāni

    1_veda/4_upa/chup___u.txt
        hu3m -> hūm

The Chāndogya exception is lexical: ``hu3m`` is normalized to the later
orthographic form ``hūm`` rather than mechanically to ``hum``.

Further safeguards:

- only files under ``1_veda/`` are examined;
- simple bracketed/parenthetical editorial spans are protected;
- obvious locator-like contexts are ignored;
- ordinary structural numbers are untouched;
- the input corpus is never modified.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.corpus.gretil.build import (
    ACCENT_MARKS,
    ACCENTED_VOWELS,
)


DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pass1_gretil_iast"
)

DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pass1_pluta_normalized_gretil_iast"
)

DEFAULT_REPORT_DIR = Path(
    "reports/cleaning/generated/pluta_normalization"
)


SUMMARY_FILENAME = "gretil_pluta_normalization_summary.txt"
NORMALIZED_FILES_FILENAME = "gretil_pluta_normalized_files.csv"
NORMALIZED_OCCURRENCES_FILENAME = (
    "gretil_pluta_normalized_occurrences.csv"
)
REVIEW_FILES_FILENAME = "gretil_pluta_review_files.csv"
REVIEW_OCCURRENCES_FILENAME = (
    "gretil_pluta_review_occurrences.csv"
)


VEDIC_PREFIX = "1_veda/"


# ---------------------------------------------------------------------------
# General orthographic policy
# ---------------------------------------------------------------------------

AUTO_BASES = {
    "ā",
    "ī",
    "ū",
    "ṝ",
    "ḹ",
    "e",
    "o",
    "ai",
    "au",
}

REVIEW_BASES = {
    "a",
    "i",
    "u",
    "ṛ",
    "ḷ",
}

LOWERCASE_ACCENTED_VOWELS = {
    character
    for character in ACCENTED_VOWELS
    if character.islower()
}

CANDIDATE_BASES = (
    AUTO_BASES
    | REVIEW_BASES
    | LOWERCASE_ACCENTED_VOWELS
)

CANDIDATE_BASE_PATTERN = "|".join(
    sorted(
        (
            re.escape(value)
            for value in CANDIDATE_BASES
        ),
        key=len,
        reverse=True,
    )
)

PLUTA_CANDIDATE_RE = re.compile(
    rf"(?P<base>{CANDIDATE_BASE_PATTERN})"
    rf"(?P<marks>[\u0300-\u036f]*)"
    rf"3"
)


# ---------------------------------------------------------------------------
# Explicit, independently verified source-specific exceptions
# ---------------------------------------------------------------------------

SOURCE_EXCEPTIONS: dict[
    str,
    tuple[
        tuple[
            re.Pattern[str],
            str,
            str,
        ],
        ...,
    ],
] = {
    "1_veda/2_bra/satapath/sb_10_u.txt": (
        (
            re.compile(r"vratāni3"),
            "vratāni",
            "verified_sb10_vratani_pluta",
        ),
    ),
    "1_veda/4_upa/chup___u.txt": (
        (
            re.compile(r"hu3m"),
            "hūm",
            "verified_chup_hum_stobha",
        ),
    ),
}


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


@dataclass(frozen=True, slots=True)
class CandidateAnalysis:
    lexical_base: str
    classification: str
    replacement: str | None


@dataclass(frozen=True, slots=True)
class Replacement:
    start: int
    end: int
    before: str
    after: str
    lexical_base: str
    rule: str


@dataclass(frozen=True, slots=True)
class PlutaOccurrence:
    path: str
    line_number: int
    column: int
    before: str
    lexical_base: str
    after: str
    rule: str
    line_before: str
    line_after: str


@dataclass(frozen=True, slots=True)
class DocumentResult:
    text: str
    normalized: tuple[PlutaOccurrence, ...]
    review: tuple[PlutaOccurrence, ...]


@dataclass(frozen=True, slots=True)
class CorpusResult:
    files_scanned: int
    vedic_files_scanned: int
    files_changed: int
    normalized_occurrences: int
    review_files: int
    review_occurrences: int


def _separate_lexical_base_and_accents(
    value: str,
) -> tuple[str, str]:
    decomposed = unicodedata.normalize(
        "NFD",
        value,
    )

    lexical_parts: list[str] = []
    accent_parts: list[str] = []

    for character in decomposed:
        if character in ACCENT_MARKS:
            accent_parts.append(
                character
            )
        else:
            lexical_parts.append(
                character
            )

    lexical_base = unicodedata.normalize(
        "NFC",
        "".join(
            lexical_parts
        ),
    )

    return (
        lexical_base,
        "".join(
            accent_parts
        ),
    )


def _analyse_candidate(
    base: str,
    marks: str,
) -> CandidateAnalysis | None:
    combined = unicodedata.normalize(
        "NFC",
        base + marks,
    )

    lexical_base, accents = (
        _separate_lexical_base_and_accents(
            combined
        )
    )

    if lexical_base in AUTO_BASES:
        replacement = unicodedata.normalize(
            "NFC",
            lexical_base + accents,
        )

        return CandidateAnalysis(
            lexical_base=lexical_base,
            classification="AUTO",
            replacement=replacement,
        )

    if lexical_base in REVIEW_BASES:
        return CandidateAnalysis(
            lexical_base=lexical_base,
            classification="REVIEW",
            replacement=None,
        )

    return None


def _protected_intervals(
    line: str,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (
            match.start(),
            match.end(),
        )
        for match in PROTECTED_SPAN_RE.finditer(
            line
        )
    )


def _overlaps(
    start: int,
    end: int,
    intervals: tuple[tuple[int, int], ...]
    | list[tuple[int, int]],
) -> bool:
    return any(
        start < interval_end
        and end > interval_start
        for interval_start, interval_end
        in intervals
    )


def _looks_like_locator(
    line: str,
    start: int,
    end: int,
) -> bool:
    """Reject candidates embedded in obvious structural locator contexts."""

    if start > 0:
        previous = line[start - 1]

        if previous.isdigit():
            return True

        if previous in "._":
            return True

        if (
            previous.isalpha()
            and previous.upper() == previous
            and previous.lower() != previous
        ):
            return True

    if end < len(line):
        following = line[end]

        if following.isdigit():
            return True

        if following in "._":
            return True

        if (
            following.isalpha()
            and following.upper() == following
            and following.lower() != following
        ):
            return True

    return False


def _source_exception_replacements(
    line: str,
    relative_path: str,
    protected: tuple[tuple[int, int], ...],
) -> list[Replacement]:
    replacements: list[Replacement] = []

    rules = SOURCE_EXCEPTIONS.get(
        relative_path,
        (),
    )

    for pattern, replacement, rule_name in rules:
        for match in pattern.finditer(
            line
        ):
            if _overlaps(
                match.start(),
                match.end(),
                protected,
            ):
                continue

            replacements.append(
                Replacement(
                    start=match.start(),
                    end=match.end(),
                    before=match.group(0),
                    after=replacement,
                    lexical_base="",
                    rule=rule_name,
                )
            )

    replacements.sort(
        key=lambda item: (
            item.start,
            item.end,
        )
    )

    return replacements


def _apply_replacements(
    line: str,
    replacements: list[Replacement],
) -> str:
    if not replacements:
        return line

    pieces: list[str] = []
    cursor = 0

    for replacement in sorted(
        replacements,
        key=lambda item: item.start,
    ):
        pieces.append(
            line[
                cursor:replacement.start
            ]
        )

        pieces.append(
            replacement.after
        )

        cursor = replacement.end

    pieces.append(
        line[cursor:]
    )

    return "".join(
        pieces
    )


def normalize_vedic_pluta(
    text: str,
    relative_path: str,
) -> DocumentResult:
    normalized_path = relative_path.replace(
        "\\",
        "/",
    )

    if not normalized_path.startswith(
        VEDIC_PREFIX
    ):
        return DocumentResult(
            text=text,
            normalized=(),
            review=(),
        )

    output_lines: list[str] = []

    normalized_occurrences: list[
        PlutaOccurrence
    ] = []

    review_occurrences: list[
        PlutaOccurrence
    ] = []

    for line_number, line in enumerate(
        text.split("\n"),
        start=1,
    ):
        protected = _protected_intervals(
            line
        )

        # ---------------------------------------------------------------
        # First reserve explicitly verified source-specific exceptions.
        # ---------------------------------------------------------------

        exception_replacements = (
            _source_exception_replacements(
                line,
                normalized_path,
                protected,
            )
        )

        exception_intervals = [
            (
                replacement.start,
                replacement.end,
            )
            for replacement
            in exception_replacements
        ]

        general_replacements: list[
            Replacement
        ] = []

        review_matches: list[
            tuple[
                re.Match[str],
                CandidateAnalysis,
            ]
        ] = []

        # ---------------------------------------------------------------
        # Then classify remaining generic vowel+3 candidates.
        # ---------------------------------------------------------------

        for match in PLUTA_CANDIDATE_RE.finditer(
            line
        ):
            if _overlaps(
                match.start(),
                match.end(),
                protected,
            ):
                continue

            if _overlaps(
                match.start(),
                match.end(),
                exception_intervals,
            ):
                continue

            if _looks_like_locator(
                line,
                match.start(),
                match.end(),
            ):
                continue

            analysis = _analyse_candidate(
                match.group("base"),
                match.group("marks"),
            )

            if analysis is None:
                continue

            if analysis.classification == "AUTO":
                assert analysis.replacement is not None

                general_replacements.append(
                    Replacement(
                        start=match.start(),
                        end=match.end(),
                        before=match.group(0),
                        after=analysis.replacement,
                        lexical_base=(
                            analysis.lexical_base
                        ),
                        rule="general_pluta",
                    )
                )

            elif analysis.classification == "REVIEW":
                review_matches.append(
                    (
                        match,
                        analysis,
                    )
                )

        all_replacements = (
            exception_replacements
            + general_replacements
        )

        all_replacements.sort(
            key=lambda item: item.start
        )

        # Defensive check: replacement rules must never overlap.
        previous_end = -1

        for replacement in all_replacements:
            if replacement.start < previous_end:
                raise RuntimeError(
                    "overlapping pluta replacement rules "
                    f"in {normalized_path}: "
                    f"{line_number}"
                )

            previous_end = replacement.end

        normalized_line = _apply_replacements(
            line,
            all_replacements,
        )

        output_lines.append(
            normalized_line
        )

        for replacement in all_replacements:
            normalized_occurrences.append(
                PlutaOccurrence(
                    path=normalized_path,
                    line_number=line_number,
                    column=(
                        replacement.start + 1
                    ),
                    before=(
                        replacement.before
                    ),
                    lexical_base=(
                        replacement.lexical_base
                    ),
                    after=(
                        replacement.after
                    ),
                    rule=(
                        replacement.rule
                    ),
                    line_before=line,
                    line_after=(
                        normalized_line
                    ),
                )
            )

        for match, analysis in review_matches:
            review_occurrences.append(
                PlutaOccurrence(
                    path=normalized_path,
                    line_number=line_number,
                    column=(
                        match.start() + 1
                    ),
                    before=match.group(0),
                    lexical_base=(
                        analysis.lexical_base
                    ),
                    after="",
                    rule="review_short_vowel_plus_3",
                    line_before=line,
                    line_after=line,
                )
            )

    normalized_text = "\n".join(
        output_lines
    )

    normalized_text = unicodedata.normalize(
        "NFC",
        normalized_text,
    )

    return DocumentResult(
        text=normalized_text,
        normalized=tuple(
            normalized_occurrences
        ),
        review=tuple(
            review_occurrences
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
            "output root must not equal input root"
        )

    try:
        destination.relative_to(
            source
        )
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
        writer.writerows(
            rows
        )


def normalize_corpus(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
) -> CorpusResult:
    if not input_root.is_dir():
        raise FileNotFoundError(
            f"input corpus does not exist: "
            f"{input_root}"
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
            f"no .txt files found under: "
            f"{input_root}"
        )

    if output_root.exists():
        shutil.rmtree(
            output_root
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    vedic_files_scanned = 0
    files_changed = 0

    all_normalized: list[
        PlutaOccurrence
    ] = []

    all_review: list[
        PlutaOccurrence
    ] = []

    normalized_file_rows: list[
        dict[str, Any]
    ] = []

    review_file_rows: list[
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

        original_text = raw_bytes.decode(
            "utf-8",
            errors="strict",
        )

        if relative_string.startswith(
            VEDIC_PREFIX
        ):
            vedic_files_scanned += 1

        result = normalize_vedic_pluta(
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

        if result.normalized:
            destination.write_bytes(
                result.text.encode(
                    "utf-8"
                )
            )

            files_changed += 1

        else:
            destination.write_bytes(
                raw_bytes
            )

        if result.normalized:
            all_normalized.extend(
                result.normalized
            )

            form_counts: Counter[
                tuple[
                    str,
                    str,
                    str,
                ]
            ] = Counter(
                (
                    occurrence.before,
                    occurrence.after,
                    occurrence.rule,
                )
                for occurrence
                in result.normalized
            )

            forms = " ".join(
                (
                    f"{before}->{after}"
                    f"[{rule}]:{count}"
                )
                for (
                    before,
                    after,
                    rule,
                ), count
                in sorted(
                    form_counts.items()
                )
            )

            normalized_file_rows.append(
                {
                    "path": relative_string,
                    "replacements": len(
                        result.normalized
                    ),
                    "forms": forms,
                }
            )

        if result.review:
            all_review.extend(
                result.review
            )

            review_counts: Counter[
                str
            ] = Counter(
                occurrence.before
                for occurrence
                in result.review
            )

            forms = " ".join(
                f"{form}:{count}"
                for form, count
                in sorted(
                    review_counts.items()
                )
            )

            review_file_rows.append(
                {
                    "path": relative_string,
                    "review_occurrences": len(
                        result.review
                    ),
                    "forms": forms,
                }
            )

    normalized_file_rows.sort(
        key=lambda row: (
            -int(
                row["replacements"]
            ),
            str(
                row["path"]
            ),
        )
    )

    review_file_rows.sort(
        key=lambda row: (
            -int(
                row[
                    "review_occurrences"
                ]
            ),
            str(
                row["path"]
            ),
        )
    )

    normalized_occurrence_rows = [
        {
            "path": occurrence.path,
            "line_number": (
                occurrence.line_number
            ),
            "column": (
                occurrence.column
            ),
            "before": (
                occurrence.before
            ),
            "lexical_base": (
                occurrence.lexical_base
            ),
            "after": (
                occurrence.after
            ),
            "rule": (
                occurrence.rule
            ),
            "line_before": (
                occurrence.line_before
            ),
            "line_after": (
                occurrence.line_after
            ),
        }
        for occurrence
        in all_normalized
    ]

    review_occurrence_rows = [
        {
            "path": occurrence.path,
            "line_number": (
                occurrence.line_number
            ),
            "column": (
                occurrence.column
            ),
            "form": (
                occurrence.before
            ),
            "lexical_base": (
                occurrence.lexical_base
            ),
            "line_text": (
                occurrence.line_before
            ),
        }
        for occurrence
        in all_review
    ]

    normalized_occurrence_rows.sort(
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

    review_occurrence_rows.sort(
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
        / NORMALIZED_FILES_FILENAME,
        (
            "path",
            "replacements",
            "forms",
        ),
        normalized_file_rows,
    )

    _write_csv(
        report_dir
        / NORMALIZED_OCCURRENCES_FILENAME,
        (
            "path",
            "line_number",
            "column",
            "before",
            "lexical_base",
            "after",
            "rule",
            "line_before",
            "line_after",
        ),
        normalized_occurrence_rows,
    )

    _write_csv(
        report_dir
        / REVIEW_FILES_FILENAME,
        (
            "path",
            "review_occurrences",
            "forms",
        ),
        review_file_rows,
    )

    _write_csv(
        report_dir
        / REVIEW_OCCURRENCES_FILENAME,
        (
            "path",
            "line_number",
            "column",
            "form",
            "lexical_base",
            "line_text",
        ),
        review_occurrence_rows,
    )

    _write_summary(
        report_dir
        / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_scanned=len(files),
        vedic_files_scanned=(
            vedic_files_scanned
        ),
        files_changed=files_changed,
        normalized_occurrences=(
            len(
                all_normalized
            )
        ),
        review_files=len(
            review_file_rows
        ),
        review_occurrences=len(
            all_review
        ),
    )

    return CorpusResult(
        files_scanned=len(
            files
        ),
        vedic_files_scanned=(
            vedic_files_scanned
        ),
        files_changed=(
            files_changed
        ),
        normalized_occurrences=len(
            all_normalized
        ),
        review_files=len(
            review_file_rows
        ),
        review_occurrences=len(
            all_review
        ),
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    output_root: Path,
    files_scanned: int,
    vedic_files_scanned: int,
    files_changed: int,
    normalized_occurrences: int,
    review_files: int,
    review_occurrences: int,
) -> None:
    lines = [
        "Formal GRETIL pluta normalization",
        "=================================",
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        f"files_scanned: {files_scanned}",
        (
            "vedic_files_scanned: "
            f"{vedic_files_scanned}"
        ),
        f"files_changed: {files_changed}",
        (
            "auto_normalized_occurrences: "
            f"{normalized_occurrences}"
        ),
        f"review_files: {review_files}",
        (
            "review_occurrences: "
            f"{review_occurrences}"
        ),
        "",
        "general AUTO policy:",
        "  ā3 -> ā",
        "  ī3 -> ī",
        "  ū3 -> ū",
        "  ṝ3 -> ṝ",
        "  ḹ3 -> ḹ",
        "  e3 -> e",
        "  o3 -> o",
        "  ai3 -> ai",
        "  au3 -> au",
        "",
        "verified source-specific exceptions:",
        (
            "  sb_10_u.txt: "
            "vratāni3 -> vratāni"
        ),
        (
            "  chup___u.txt: "
            "hu3m -> hūm"
        ),
        "",
        "remaining REVIEW-only classes:",
        "  a3",
        "  i3",
        "  u3",
        "  ṛ3",
        "  ḷ3",
        "",
        "safeguards:",
        "  operate only under 1_veda/",
        (
            "  protect simple [], (), {}, "
            "<> spans"
        ),
        (
            "  ignore obvious locator-like "
            "contexts"
        ),
        (
            "  preserve ordinary structural "
            "numbers"
        ),
        (
            "  preserve untouched files "
            "byte-identically"
        ),
        "",
        (
            "The input corpus was not "
            "modified."
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
            "Normalize verified Vedic "
            "pluta forms conservatively"
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

    result = normalize_corpus(
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
        f"scanned "
        f"{result.files_scanned} "
        f"document(s)"
    )

    print(
        f"scanned "
        f"{result.vedic_files_scanned} "
        f"Vedic document(s)"
    )

    print(
        f"changed "
        f"{result.files_changed} "
        f"document(s)"
    )

    print(
        f"normalized "
        f"{result.normalized_occurrences} "
        f"pluta occurrence(s)"
    )

    print(
        f"REVIEW: "
        f"{result.review_occurrences} "
        f"occurrence(s) in "
        f"{result.review_files} "
        f"document(s)"
    )


if __name__ == "__main__":
    main()

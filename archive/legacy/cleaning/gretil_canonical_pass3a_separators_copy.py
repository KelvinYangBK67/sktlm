"""Pass 3A: normalize explicit source segmentation separators.

This stage standardizes source-encoded segmentation marks to ASCII spaces.
It does *not* infer linguistic segmentation and does not attempt to distinguish
word boundaries from compound-member boundaries.

Current execution policy
------------------------

DOT is enabled only for an explicit whitelist of source files whose electronic
edition systematically uses periods as segmentation separators.

HYPHEN is implemented by the same classifier, but no file is enabled for
automatic hyphen normalization yet. Add a file to ``HYPHEN_BOUNDARY_FILES``
only after its hyphen convention has been checked.

Classification
--------------

AUTO
    Known separator-family file + unambiguous separator context.
    The separator is replaced by one ASCII space.

REVIEW
    Separator-like occurrence in an enabled file that is not covered by an
    AUTO or IGNORE rule. It is reported but not modified.

IGNORE
    Protected editorial spans, numeric/locator contexts, repeated punctuation,
    and other contexts that are not treated as segmentation.

Input::

    data/canonical_candidate/pass2_gretil_iast

Output::

    data/canonical_candidate/pass3a_separator_normalized_gretil_iast
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
from typing import Any, Literal


DEFAULT_INPUT_ROOT = Path(
    "data/canonical_candidate/pass2_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/canonical_candidate/pass3a_separator_normalized_gretil_iast"
)
DEFAULT_REPORT_DIR = Path(
    "data/_reports/pass3a_separators"
)

SUMMARY_FILENAME = "gretil_pass3a_separator_summary.txt"
FILE_AUDIT_FILENAME = "gretil_pass3a_separator_file_audit.csv"
AUTO_FILENAME = "gretil_pass3a_separator_auto.csv"
REVIEW_FILENAME = "gretil_pass3a_separator_review.csv"


# These files have already been identified as using dot systematically as a
# source segmentation convention. This is a provenance decision, not a
# language-model guess.
DOT_BOUNDARY_FILES = frozenset(
    {
        "1_veda/2_bra/kausibru.txt",
        "1_veda/5_vedang/1_srauta/asvss_u.txt",
        "1_veda/5_vedang/1_srauta/sankhssu.txt",
        "1_veda/5_vedang/2_grhya/sankhgsu.txt",
        "1_veda/5_vedang/2_grhya/asvgs_u.txt",
    }
)

# Intentionally empty in the first execution. The same engine is ready for
# hyphen-family normalization once file-level conventions are verified.
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

HORIZONTAL_SPACE_RE = re.compile(r"[ \t]+")

Decision = Literal["AUTO", "REVIEW", "IGNORE"]


@dataclass(frozen=True, slots=True)
class Classification:
    decision: Decision
    reason: str


@dataclass(frozen=True, slots=True)
class Occurrence:
    path: str
    line_number: int
    column: int
    separator: str
    decision: Decision
    reason: str
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


def _inside_intervals(
    index: int,
    intervals: tuple[tuple[int, int], ...],
) -> bool:
    return any(
        start <= index < end
        for start, end in intervals
    )


def _is_combining(character: str) -> bool:
    return unicodedata.category(character).startswith("M")


def _is_lowercase_letter(character: str) -> bool:
    """True for lowercase alphabetic characters usable in Sanskrit text.

    The file-level provenance whitelist carries most of the safety burden.
    Uppercase source sigla / English headings are deliberately excluded.
    """

    return (
        character.isalpha()
        and character.lower() == character
    )


def _left_anchor(
    line: str,
    index: int,
) -> tuple[int, str] | None:
    """Find the lexical/punctuation anchor immediately left of a separator.

    Combining marks are skipped because they belong to the preceding letter.
    Whitespace is *not* skipped.
    """

    i = index - 1
    while i >= 0 and _is_combining(line[i]):
        i -= 1

    if i < 0:
        return None

    return i, line[i]


def _right_anchor(
    line: str,
    index: int,
) -> tuple[int, str] | None:
    """Find the anchor immediately right of a separator.

    Combining marks are skipped only after a base character; a combining mark
    cannot sensibly begin a new token by itself, so such a context is REVIEW.
    """

    i = index + 1
    if i >= len(line):
        return None

    return i, line[i]


def _right_after_apostrophe(
    line: str,
    right_index: int,
) -> str | None:
    if (
        right_index < len(line)
        and line[right_index] == "'"
        and right_index + 1 < len(line)
    ):
        return line[right_index + 1]

    return None


def _context(
    line: str,
    index: int,
    radius: int = 28,
) -> str:
    start = max(0, index - radius)
    end = min(len(line), index + radius + 1)
    return line[start:end]


def classify_separator(
    line: str,
    index: int,
    *,
    separator: str,
    enabled: bool,
    protected: tuple[tuple[int, int], ...] | None = None,
) -> Classification:
    """Classify one ``.`` or ``-`` occurrence.

    This function intentionally answers a source-format question only:
    "is this occurrence an explicit segmentation separator in a file whose
    convention is known?"  It does not ask whether the boundary is a word,
    compound, morpheme, or any other linguistic boundary.
    """

    if separator not in {".", "-"}:
        raise ValueError(
            f"unsupported separator: {separator!r}"
        )

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
        protected = _protected_intervals(line)

    if _inside_intervals(index, protected):
        return Classification(
            "IGNORE",
            "inside_protected_span",
        )

    left = _left_anchor(line, index)
    right = _right_anchor(line, index)

    if left is None or right is None:
        return Classification(
            "REVIEW",
            "line_edge",
        )

    left_index, left_char = left
    right_index, right_char = right

    # Numeric locators, ranges, decimal-like material.
    if left_char.isdigit() or right_char.isdigit():
        return Classification(
            "IGNORE",
            "adjacent_digit",
        )

    # Repeated punctuation is not interpreted as segmentation.
    if left_char == separator or right_char == separator:
        return Classification(
            "IGNORE",
            "repeated_separator",
        )

    # Explicit source separator between lexical material.
    if (
        _is_lowercase_letter(left_char)
        and _is_lowercase_letter(right_char)
    ):
        return Classification(
            "AUTO",
            "lexical_to_lexical",
        )

    # Source separators can occur before an avagraha-bearing form:
    #   anyo-'nyaḥ -> anyo 'nyaḥ
    apostrophe_target = _right_after_apostrophe(
        line,
        right_index,
    )
    if (
        _is_lowercase_letter(left_char)
        and right_char == "'"
        and apostrophe_target is not None
        and _is_lowercase_letter(apostrophe_target)
    ):
        return Classification(
            "AUTO",
            "lexical_to_avagraha",
        )

    # Dot-heavy Vedic editions also use ".|" and "|." around danda.
    # These are safe only for dot, not hyphen.
    if separator == ".":
        if (
            _is_lowercase_letter(left_char)
            and right_char == "|"
        ):
            return Classification(
                "AUTO",
                "lexical_to_danda",
            )

        if (
            left_char == "|"
            and _is_lowercase_letter(right_char)
        ):
            return Classification(
                "AUTO",
                "danda_to_lexical",
            )

    # Existing whitespace next to the separator usually means punctuation or
    # an editorial convention rather than a tightly encoded segmentation mark.
    if left_char.isspace() or right_char.isspace():
        return Classification(
            "REVIEW",
            "adjacent_whitespace",
        )

    # Uppercase and miscellaneous symbols are kept for explicit review.
    if (
        (left_char.isalpha() and not _is_lowercase_letter(left_char))
        or (right_char.isalpha() and not _is_lowercase_letter(right_char))
    ):
        return Classification(
            "REVIEW",
            "uppercase_or_nonlowercase_context",
        )

    return Classification(
        "REVIEW",
        "unclassified_context",
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
    protected = _protected_intervals(line)

    classifications: list[
        tuple[int, str, Classification]
    ] = []

    for index, character in enumerate(line):
        if character == ".":
            classification = classify_separator(
                line,
                index,
                separator=".",
                enabled=dot_enabled,
                protected=protected,
            )
        elif character == "-":
            classification = classify_separator(
                line,
                index,
                separator="-",
                enabled=hyphen_enabled,
                protected=protected,
            )
        else:
            continue

        if classification.reason == "separator_not_enabled_for_file":
            continue

        classifications.append(
            (
                index,
                character,
                classification,
            )
        )

    auto_positions = {
        index
        for index, _, classification
        in classifications
        if classification.decision == "AUTO"
    }

    if auto_positions:
        chars = list(line)
        for index in auto_positions:
            chars[index] = " "

        normalized_line = "".join(chars)
        normalized_line = HORIZONTAL_SPACE_RE.sub(
            " ",
            normalized_line,
        ).strip()
    else:
        normalized_line = line

    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    ignored_counts: Counter[str] = Counter()

    for index, separator, classification in classifications:
        occurrence = Occurrence(
            path=path,
            line_number=line_number,
            column=index + 1,
            separator=separator,
            decision=classification.decision,
            reason=classification.reason,
            context=_context(line, index),
            line_before=line,
            line_after=(
                normalized_line
                if classification.decision == "AUTO"
                else line
            ),
        )

        if classification.decision == "AUTO":
            auto.append(occurrence)
        elif classification.decision == "REVIEW":
            review.append(occurrence)
        else:
            ignored_counts[
                f"{separator}:{classification.reason}"
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
    normalized_path = relative_path.replace(
        "\\",
        "/",
    )

    dot_enabled = (
        normalized_path in DOT_BOUNDARY_FILES
    )
    hyphen_enabled = (
        normalized_path in HYPHEN_BOUNDARY_FILES
    )

    if not dot_enabled and not hyphen_enabled:
        return DocumentResult(
            text=text,
            auto=(),
            review=(),
            ignored_counts=Counter(),
        )

    output_lines: list[str] = []
    auto: list[Occurrence] = []
    review: list[Occurrence] = []
    ignored_counts: Counter[str] = Counter()

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

        output_lines.append(normalized_line)
        auto.extend(line_auto)
        review.extend(line_review)
        ignored_counts.update(line_ignored)

    return DocumentResult(
        text="\n".join(output_lines),
        auto=tuple(auto),
        review=tuple(review),
        ignored_counts=ignored_counts,
    )


def _validate_roots(
    input_root: Path,
    output_root: Path,
) -> None:
    source = input_root.resolve()
    destination = output_root.resolve()

    if source == destination:
        raise ValueError(
            "Pass 3A output root must not equal input root"
        )

    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError(
            "Pass 3A output root must not be inside input root"
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
        "separator": occurrence.separator,
        "decision": occurrence.decision,
        "reason": occurrence.reason,
        "context": occurrence.context,
        "line_before": occurrence.line_before,
        "line_after": occurrence.line_after,
    }


def build_pass3a_candidate(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
) -> CorpusResult:
    if not input_root.is_dir():
        raise FileNotFoundError(
            f"Pass 3A input root does not exist: {input_root}"
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

    files_changed = 0
    target_files = 0

    auto_occurrences: list[Occurrence] = []
    review_occurrences: list[Occurrence] = []
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

        total_input_chars += len(original_text)

        is_target = (
            relative_string in DOT_BOUNDARY_FILES
            or relative_string in HYPHEN_BOUNDARY_FILES
        )

        if is_target:
            target_files += 1

        result = normalize_document(
            original_text,
            relative_string,
        )

        destination = output_root / relative_path
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        changed = bool(result.auto)

        if changed:
            destination.write_bytes(
                result.text.encode("utf-8")
            )
            files_changed += 1
            output_text = result.text
        else:
            # Files with only REVIEW/IGNORE decisions remain byte-identical.
            destination.write_bytes(raw_bytes)
            output_text = original_text

        total_output_chars += len(output_text)

        auto_occurrences.extend(result.auto)
        review_occurrences.extend(result.review)

        if is_target:
            auto_dot = sum(
                occurrence.separator == "."
                for occurrence in result.auto
            )
            auto_hyphen = sum(
                occurrence.separator == "-"
                for occurrence in result.auto
            )
            review_dot = sum(
                occurrence.separator == "."
                for occurrence in result.review
            )
            review_hyphen = sum(
                occurrence.separator == "-"
                for occurrence in result.review
            )

            ignored_dot = sum(
                count
                for key, count in result.ignored_counts.items()
                if key.startswith(".:")
            )
            ignored_hyphen = sum(
                count
                for key, count in result.ignored_counts.items()
                if key.startswith("-:")
            )

            file_rows.append(
                {
                    "path": relative_string,
                    "dot_enabled": int(
                        relative_string in DOT_BOUNDARY_FILES
                    ),
                    "hyphen_enabled": int(
                        relative_string in HYPHEN_BOUNDARY_FILES
                    ),
                    "changed": int(changed),
                    "input_chars": len(original_text),
                    "output_chars": len(output_text),
                    "char_delta": (
                        len(output_text)
                        - len(original_text)
                    ),
                    "auto_dot": auto_dot,
                    "auto_hyphen": auto_hyphen,
                    "review_dot": review_dot,
                    "review_hyphen": review_hyphen,
                    "ignored_dot": ignored_dot,
                    "ignored_hyphen": ignored_hyphen,
                }
            )

    file_rows.sort(
        key=lambda row: (
            -int(row["auto_dot"])
            - int(row["auto_hyphen"]),
            str(row["path"]),
        )
    )

    auto_rows = [
        _occurrence_row(occurrence)
        for occurrence in auto_occurrences
    ]
    review_rows = [
        _occurrence_row(occurrence)
        for occurrence in review_occurrences
    ]

    auto_rows.sort(
        key=lambda row: (
            str(row["path"]),
            int(row["line_number"]),
            int(row["column"]),
        )
    )
    review_rows.sort(
        key=lambda row: (
            str(row["path"]),
            int(row["line_number"]),
            int(row["column"]),
        )
    )

    _write_csv(
        report_dir / FILE_AUDIT_FILENAME,
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
        "context",
        "line_before",
        "line_after",
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

    auto_dot = sum(
        occurrence.separator == "."
        for occurrence in auto_occurrences
    )
    auto_hyphen = sum(
        occurrence.separator == "-"
        for occurrence in auto_occurrences
    )
    review_dot = sum(
        occurrence.separator == "."
        for occurrence in review_occurrences
    )
    review_hyphen = sum(
        occurrence.separator == "-"
        for occurrence in review_occurrences
    )

    _write_summary(
        report_dir / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_processed=len(files),
        target_files=target_files,
        files_changed=files_changed,
        input_chars=total_input_chars,
        output_chars=total_output_chars,
        auto_dot=auto_dot,
        auto_hyphen=auto_hyphen,
        review_dot=review_dot,
        review_hyphen=review_hyphen,
    )

    return CorpusResult(
        files_processed=len(files),
        target_files=target_files,
        files_changed=files_changed,
        auto_dot=auto_dot,
        auto_hyphen=auto_hyphen,
        review_dot=review_dot,
        review_hyphen=review_hyphen,
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
        "Formal GRETIL Pass 3A separator normalization",
        "=============================================",
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        f"files_processed: {files_processed}",
        f"target_files: {target_files}",
        f"files_changed: {files_changed}",
        f"input_chars: {input_chars}",
        f"output_chars: {output_chars}",
        f"char_delta: {output_chars - input_chars}",
        "",
        "AUTO:",
        f"  dot_to_space: {auto_dot}",
        f"  hyphen_to_space: {auto_hyphen}",
        "",
        "REVIEW:",
        f"  dot: {review_dot}",
        f"  hyphen: {review_hyphen}",
        "",
        "enabled dot files:",
        *[
            f"  {path}"
            for path in sorted(DOT_BOUNDARY_FILES)
        ],
        "",
        "enabled hyphen files:",
        *(
            [
                f"  {path}"
                for path in sorted(HYPHEN_BOUNDARY_FILES)
            ]
            or ["  (none)"]
        ),
        "",
        "policy:",
        (
            "  normalize explicit source segmentation marks "
            "to ASCII space"
        ),
        (
            "  do not distinguish word/compound/morpheme "
            "boundary subtypes"
        ),
        (
            "  do not infer missing boundaries or repair "
            "Sanskrit spelling"
        ),
        (
            "  protected/editorial and numeric contexts "
            "are not modified"
        ),
        (
            "  files without an enabled separator convention "
            "are byte-identical"
        ),
        "",
        "The Pass 3A input corpus was not modified.",
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
            "Normalize verified source segmentation "
            "separators to ASCII spaces"
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

    result = build_pass3a_candidate(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
    )

    print(
        f"processed {result.files_processed} document(s)"
    )
    print(
        f"target files: {result.target_files}"
    )
    print(
        f"changed {result.files_changed} document(s)"
    )
    print(
        f"AUTO dot -> space: {result.auto_dot}"
    )
    print(
        f"AUTO hyphen -> space: {result.auto_hyphen}"
    )
    print(
        f"REVIEW dot: {result.review_dot}"
    )
    print(
        f"REVIEW hyphen: {result.review_hyphen}"
    )


if __name__ == "__main__":
    main()

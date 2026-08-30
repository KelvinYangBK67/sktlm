"""Pass 1 conservative cleanup for the formal GRETIL canonical IAST corpus.

This pass applies only mechanically high-confidence transformations established
by corpus-wide anomaly auditing.

It NEVER modifies ``data/canonical/gretil_iast``. By default it writes a
parallel candidate corpus under::

    data/intermediate/gretil/pass1_gretil_iast

The purpose of this pass is to remove obvious encoding/infrastructure residue
and explicit scholarly markup before more ambiguous phenomena such as hyphens,
periods, commas, uppercase text, and mixed-language material are analysed.

Pass 1 intentionally does NOT attempt to solve:

- general hyphen interpretation;
- general period interpretation;
- commas or ordinary punctuation;
- uppercase text;
- q/w/f/x/z residue;
- arbitrary parentheses/braces/brackets;
- mixed-language passages;
- file-specific corrupt transliteration.
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


DEFAULT_INPUT_ROOT = Path("data/canonical/gretil_iast")
DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pass1_gretil_iast"
)
DEFAULT_REPORT_DIR = Path("reports/cleaning/generated/pass1")

AUDIT_FILENAME = "gretil_canonical_pass1_cleaning_audit.csv"
SUMMARY_FILENAME = "gretil_canonical_pass1_summary.txt"


# ---------------------------------------------------------------------------
# Conservative Sanskrit character set used ONLY for short [...] supplements.
# This is not the full canonical-corpus validation contract.
# ---------------------------------------------------------------------------

SANSKRIT_SUPPLEMENT_LETTERS = set(
    "aāiīuūṛṝḷḹeo"
    "kgṅhcjñyśṭḍṇrṣtdnlspbmv"
    "ṃḥ"
)


# ---------------------------------------------------------------------------
# Explicit source/editorial markup
# ---------------------------------------------------------------------------

# GRETIL Harivaṃśa metadata:
#
# [h: HV (CE) Appendix ..., transliterated by ... :h]
# [k: K2.4 Ñ2.3 V B ... ins. ... :k]
#
# These are explicit machine/editorial records, not Sanskrit text.
HV_METADATA_RE = re.compile(
    r"\[(?P<tag>[hk]):.*?:(?P=tag)\]",
    re.IGNORECASE,
)


# Process only non-nested square-bracket spans.
SQUARE_RE = re.compile(
    r"\[([^\[\]\n]*)\]"
)


# Process only non-nested round-parenthesis spans.
ROUND_RE = re.compile(
    r"\(([^()\n]*)\)"
)


# Process only non-nested angle-bracket spans.
ANGLE_RE = re.compile(
    r"<([^<>\n]*)>"
)


# Clearly editorial square-bracket notes.
#
# Deliberately conservative: this does NOT mean every [...] span is apparatus.
SQUARE_EDITORIAL_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?:
        ed(?:\.|:|\s)
        |
        corr(?:\.|:|\s)
        |
        cf(?:\.|:|\s)
        |
        note\b
        |
        see\b
        |
        variant\b
        |
        emend(?:ed|ation)?\b
        |
        interpolation\b
        |
        Matsumura\b
        |
        Speyer\b
        |
        Patyal\b
        |
        Caland\b
        |
        Dutt\b
        |
        Bloomfield\b
        |
        Mylius\b
        |
        sūtra-division\b
        |
        pratīka\s+of\b
        |
        sakala\s+(?:at|also)\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Known citation sigla seen in the formal corpus.
#
# A citation match also requires locator-like material; a bare Sanskrit-looking
# abbreviation is not deleted merely because it resembles one of these strings.
CITATION_SIGLUM_RE = re.compile(
    r"""
    ^\s*
    (?:
        ṚV
        |
        RV
        |
        ṚVKh
        |
        ŚS
        |
        PS
        |
        VS
        |
        VSM
        |
        SV
        |
        TS
        |
        TB
        |
        TAA
        |
        VaitS
        |
        KauśS
        |
        ĀpŚS
        |
        ApŚS
        |
        BaudhŚS
        |
        ŚBM
        |
        GBr
        |
        BhP
        |
        SBV
        |
        GBM
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Examples:
#
# <1.2.13>
# <7.3.4>
# <18.4.28>
ANGLE_NUMERIC_LOCATOR_RE = re.compile(
    r"""
    ^\s*
    \d+
    (?:
        [.,:]
        \d+[A-Za-z]*
    )*
    [A-Za-z]?
    \s*$
    """,
    re.VERBOSE,
)


# High-confidence parenthetical source/page/editorial locators.
ROUND_EDITORIAL_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?:
        Matsumura\b
        |
        SBV\b
        |
        GBM\b
        |
        Speyer\b
        |
        Caland\b
        |
        Dutt\b
        |
        Patyal\b
        |
        Bloomfield\b
        |
        Mylius\b
        |
        ed(?:\.|:|\s)
        |
        cf(?:\.|:|\s)
        |
        corr(?:\.|:|\s)
        |
        VAR\b
        |
        variant\b
        |
        text\s+confused\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Examples:
#
# (79r = GBM 741)
# (A 386a)
# (a2)
# (276v1 = GBM 6.865)
ROUND_FOLIO_LOCATOR_RE = re.compile(
    r"""
    ^\s*
    (?:
        [A-Za-z]{0,4}\s*
    )?
    \d+
    [rvab]?
    \d*
    (?:
        \s*=\s*
        [A-Za-z]{1,8}
        \s*
        \d+(?:[.,]\d+)*
        [rvab]?
    )?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Explicit bibliographic wording that may not occur at the beginning.
ROUND_EDITORIAL_SUBSTRING_RE = re.compile(
    r"""
    (?:
        not\s+found\s+in
        |
        BI\s+ed\.
        |
        GGA\s+\d+
        |
        Kl\.\s*Schr\.
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


HORIZONTAL_SPACE_RE = re.compile(r"[ \t]+")


@dataclass(frozen=True, slots=True)
class Pass1Result:
    """Result of cleaning one canonical document."""

    text: str
    counts: Counter[str]


@dataclass(frozen=True, slots=True)
class CorpusPass1Result:
    """Summary of a complete Pass 1 candidate build."""

    files_processed: int
    total_counts: Counter[str]
    audit_rows: tuple[dict[str, Any], ...]


RULE_FIELDS = (
    "crlf_normalized",
    "cr_normalized",
    "tab_to_space",
    "control_or_format_removed",
    "underscore_to_space",
    "hv_metadata_removed",
    "square_editorial_removed",
    "square_citation_removed",
    "square_supplement_unwrapped",
    "angle_numeric_locator_removed",
    "angle_unwrapped",
    "round_editorial_removed",
    "whitespace_normalized",
)


def _is_simple_sanskrit_supplement(content: str) -> bool:
    """Return True for a very short Sanskrit supplementation such as [ḥ]."""

    value = content.strip()

    if not value:
        return False

    # Keep this intentionally short. Long bracketed Sanskrit may have a
    # different editorial function and belongs to later review.
    if len(value) > 4:
        return False

    for character in value:
        if character in SANSKRIT_SUPPLEMENT_LETTERS:
            continue

        category = unicodedata.category(character)

        # Permit combining marks on otherwise Sanskrit letters.
        if category.startswith("M"):
            continue

        return False

    return True


def _is_square_citation(content: str) -> bool:
    """Return True for a high-confidence bibliographic/scriptural locator."""

    value = content.strip()

    if not value:
        return False

    if not CITATION_SIGLUM_RE.match(value):
        return False

    # Require locator-like evidence. This prevents a bare siglum from being
    # removed merely because it happens to match the known abbreviation list.
    return (
        any(character.isdigit() for character in value)
        or "(?)" in value
        or "cf." in value.casefold()
        or "sakala" in value.casefold()
    )


def _is_round_editorial(content: str) -> bool:
    """Return True for a high-confidence parenthetical locator/editor note."""

    value = content.strip()

    if not value:
        return False

    if ROUND_EDITORIAL_PREFIX_RE.search(value):
        return True

    if ROUND_FOLIO_LOCATOR_RE.fullmatch(value):
        return True

    if ROUND_EDITORIAL_SUBSTRING_RE.search(value):
        return True

    return False


def _remove_control_and_format(
    text: str,
    counts: Counter[str],
) -> str:
    """Normalize newlines/tabs and remove remaining Cc/Cf characters."""

    crlf_count = text.count("\r\n")

    if crlf_count:
        counts["crlf_normalized"] += crlf_count
        text = text.replace("\r\n", "\n")

    cr_count = text.count("\r")

    if cr_count:
        counts["cr_normalized"] += cr_count
        text = text.replace("\r", "\n")

    tab_count = text.count("\t")

    if tab_count:
        counts["tab_to_space"] += tab_count
        text = text.replace("\t", " ")

    output: list[str] = []

    for character in text:
        if character == "\n":
            output.append(character)
            continue

        category = unicodedata.category(character)

        if category in {"Cc", "Cf"}:
            counts["control_or_format_removed"] += 1
            continue

        output.append(character)

    return "".join(output)


def _remove_hv_metadata(
    text: str,
    counts: Counter[str],
) -> str:
    """Delete explicit [h:...:h] and [k:...:k] Harivaṃśa metadata."""

    text, replacement_count = HV_METADATA_RE.subn(
        " ",
        text,
    )

    counts["hv_metadata_removed"] += replacement_count

    return text


def _process_square_brackets(
    text: str,
    counts: Counter[str],
) -> str:
    """Apply only high-confidence square-bracket transformations."""

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        stripped = content.strip()

        if _is_simple_sanskrit_supplement(stripped):
            counts["square_supplement_unwrapped"] += 1
            return stripped

        if SQUARE_EDITORIAL_PREFIX_RE.search(stripped):
            counts["square_editorial_removed"] += 1
            return " "

        if _is_square_citation(stripped):
            counts["square_citation_removed"] += 1
            return " "

        # Unknown [...] stays untouched for later rounds.
        return match.group(0)

    return SQUARE_RE.sub(
        replace,
        text,
    )


def _process_angle_brackets(
    text: str,
    counts: Counter[str],
) -> str:
    """Delete numeric locators; otherwise unwrap <...> while preserving text."""

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        stripped = content.strip()

        if ANGLE_NUMERIC_LOCATOR_RE.fullmatch(stripped):
            counts["angle_numeric_locator_removed"] += 1
            return " "

        # Corpus sampling shows angle brackets extensively mark quoted Sanskrit
        # mantras. The brackets are markup; the Sanskrit contents are not.
        counts["angle_unwrapped"] += 1
        return stripped

    return ANGLE_RE.sub(
        replace,
        text,
    )


def _process_round_brackets(
    text: str,
    counts: Counter[str],
) -> str:
    """Remove only recognized parenthetical source/editorial locators."""

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)

        if _is_round_editorial(content):
            counts["round_editorial_removed"] += 1
            return " "

        # General (...) is deliberately preserved for Pass 2.
        return match.group(0)

    return ROUND_RE.sub(
        replace,
        text,
    )


def _normalize_whitespace(
    text: str,
    counts: Counter[str],
) -> str:
    """Normalize horizontal spaces and blank-line runs without joining lines."""

    output_lines: list[str] = []
    previous_blank = True

    for raw_line in text.split("\n"):
        line, replacement_count = HORIZONTAL_SPACE_RE.subn(
            " ",
            raw_line,
        )

        counts["whitespace_normalized"] += replacement_count

        stripped = line.strip()

        if stripped != line:
            counts["whitespace_normalized"] += 1

        line = stripped

        if not line:
            if output_lines and not previous_blank:
                output_lines.append("")

            previous_blank = True
            continue

        output_lines.append(line)
        previous_blank = False

    while output_lines and not output_lines[-1]:
        output_lines.pop()

    if not output_lines:
        return ""

    return "\n".join(output_lines) + "\n"


def apply_pass1(text: str) -> Pass1Result:
    """Apply the conservative Pass 1 transformations to one document."""

    counts: Counter[str] = Counter()

    text = _remove_control_and_format(
        text,
        counts,
    )

    underscore_count = text.count("_")

    if underscore_count:
        counts["underscore_to_space"] += underscore_count
        text = text.replace("_", " ")

    # HV records must be removed before generic [...] handling.
    text = _remove_hv_metadata(
        text,
        counts,
    )

    # Process citations/apparatus inside <...> first, so:
    #
    # <agnim īḷe ... [ṚV 1.1.1]>
    #
    # becomes:
    #
    # <agnim īḷe ... >
    #
    # before the outer angle markup is unwrapped.
    text = _process_square_brackets(
        text,
        counts,
    )

    text = _process_angle_brackets(
        text,
        counts,
    )

    text = _process_round_brackets(
        text,
        counts,
    )

    text = _normalize_whitespace(
        text,
        counts,
    )

    return Pass1Result(
        text=text,
        counts=counts,
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


def _validate_roots(
    input_root: Path,
    output_root: Path,
) -> None:
    """Prevent accidental in-place or nested writes."""

    source = input_root.resolve()
    destination = output_root.resolve()

    if source == destination:
        raise ValueError(
            "Pass 1 output root must not equal the canonical input root"
        )

    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError(
            "Pass 1 output root must not be inside the canonical input root"
        )


def build_pass1_candidate(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
) -> CorpusPass1Result:
    """Build a complete read-only-derived Pass 1 candidate corpus."""

    if not input_root.is_dir():
        raise FileNotFoundError(
            f"canonical input root does not exist: {input_root}"
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
            f"no canonical .txt files found under: {input_root}"
        )

    # Candidate output is a generated artifact. Rebuild it from scratch so no
    # stale files can survive from an earlier run.
    if output_root.exists():
        shutil.rmtree(output_root)

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_counts: Counter[str] = Counter()
    audit_rows: list[dict[str, Any]] = []

    for source_path in files:
        relative_path = source_path.relative_to(
            input_root
        )

        raw_bytes = source_path.read_bytes()
        original_text = raw_bytes.decode(
            "utf-8",
            errors="strict",
        )

        result = apply_pass1(
            original_text,
        )

        destination = output_root / relative_path

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_bytes(
            result.text.encode("utf-8")
        )

        total_counts.update(
            result.counts
        )

        row: dict[str, Any] = {
            "path": relative_path.as_posix(),
            "input_chars": len(original_text),
            "output_chars": len(result.text),
            "char_delta": (
                len(result.text)
                - len(original_text)
            ),
        }

        for rule in RULE_FIELDS:
            row[rule] = result.counts.get(
                rule,
                0,
            )

        row["total_rule_hits"] = sum(
            result.counts.get(rule, 0)
            for rule in RULE_FIELDS
        )

        audit_rows.append(row)

    _write_csv(
        report_dir / AUDIT_FILENAME,
        (
            "path",
            "input_chars",
            "output_chars",
            "char_delta",
            *RULE_FIELDS,
            "total_rule_hits",
        ),
        audit_rows,
    )

    _write_summary(
        report_dir / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_processed=len(files),
        total_counts=total_counts,
        input_chars=sum(
            int(row["input_chars"])
            for row in audit_rows
        ),
        output_chars=sum(
            int(row["output_chars"])
            for row in audit_rows
        ),
    )

    return CorpusPass1Result(
        files_processed=len(files),
        total_counts=total_counts,
        audit_rows=tuple(audit_rows),
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    output_root: Path,
    files_processed: int,
    total_counts: Counter[str],
    input_chars: int,
    output_chars: int,
) -> None:
    lines = [
        "Formal GRETIL canonical Pass 1",
        "================================",
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        f"files_processed: {files_processed}",
        f"input_chars: {input_chars}",
        f"output_chars: {output_chars}",
        f"char_delta: {output_chars - input_chars}",
        "",
        "rule_hits:",
    ]

    for rule in RULE_FIELDS:
        lines.append(
            f"  {rule}: {total_counts.get(rule, 0)}"
        )

    lines.extend(
        [
            "",
            "intentionally_untouched:",
            "  general hyphens",
            "  general periods",
            "  commas",
            "  uppercase text",
            "  q/w/f/x/z and other non-IAST Latin residue",
            "  unclassified square brackets",
            "  unclassified round brackets",
            "  curly braces",
            "  mixed-language passages",
            "  file-specific transliteration corruption",
            "",
            "The formal canonical input corpus was not modified.",
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


def main(argv: list[str] | None = None) -> None:
    """Build the Pass 1 candidate corpus."""

    parser = argparse.ArgumentParser(
        description=(
            "Build a conservative Pass 1 candidate from "
            "the formal GRETIL canonical corpus"
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

    result = build_pass1_candidate(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
    )

    print(
        f"built Pass 1 candidate for "
        f"{result.files_processed} document(s)"
    )

    print(
        f"candidate corpus: {args.output_root}"
    )

    print(
        f"Pass 1 reports: {args.report_dir}"
    )


if __name__ == "__main__":
    main()

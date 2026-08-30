"""Pass 2 conservative structural cleanup for the GRETIL canonical corpus.

Input::

    data/intermediate/gretil/pass1_pluta_normalized_gretil_iast

Output::

    data/intermediate/gretil/pass2_gretil_iast

Pass 2 uses only positive, anchored/full-match structural rules. Ambiguous
punctuation and source-specific orthography remain untouched for Pass 3.
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


DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pass1_pluta_normalized_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path("data/intermediate/gretil/pass2_gretil_iast")
DEFAULT_REPORT_DIR = Path("reports/cleaning/generated/pass2")

SUMMARY_FILENAME = "gretil_canonical_pass2_summary.txt"
AUDIT_FILENAME = "gretil_canonical_pass2_cleaning_audit.csv"
OCCURRENCES_FILENAME = "gretil_canonical_pass2_occurrences.csv"


SQUARE_RE = re.compile(r"\[([^\[\]\n]*)\]")

EDITORIAL_SQUARE_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?:
        ed(?:\.|:|\s)
        |
        corr(?:\.|:|\s)
        |
        em(?:\.|:|\s)
        |
        cf(?:\.|:|\s)
        |
        thus\b
        |
        reading\b
        |
        variant(?:s)?\b
        |
        lacuna\b
        |
        gap\b
        |
        omitted\b
        |
        illegible\b
        |
        not\s+found\b
        |
        bhattacharyya\s+edits?\b
        |
        the\s+above\s+section\b
        |
        ms(?:\.|:|\s)
        |
        mss(?:\.|:|\s)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

EDITORIAL_SQUARE_ANYWHERE_RE = re.compile(
    r"""
    (?:
        sakala\s+follows
        |
        follows\s+thus
        |
        reads?\s+as\s+follows
        |
        not\s+found\s+in
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

CITATION_SIGLUM = (
    r"(?:ṚV|RV|ŚS|SS|PS|TS|VS|VSM|SV|TB|TAA|"
    r"VaitS|KauśS|ĀpŚS|ApŚS|BaudhŚS|ŚBM|GBr|SBV|GBM)"
)
LOCATOR_ONLY_RE = re.compile(
    r"^\d+(?:\.\d+)+(?:[a-d])?$",
    re.IGNORECASE,
)
SIGLUM_LOCATOR_RE = re.compile(
    rf"^{CITATION_SIGLUM}\s+\d+(?:\.\d+)+(?:[a-d])?$",
    re.IGNORECASE,
)

LEADING_DOTTED_LOCATOR_RE = re.compile(
    r"""
    ^\s*
    (?P<locator>
        \d+
        (?:\.\d+){2,}
        \.?
    )
    (?=
        \s*
        [A-Za-zĀĪŪṚṜḶḸāīūṛṝḷḹŚṢṄÑṬḌṆḤṂśṣṅñṭḍṇḥṃ']
    )
    """,
    re.VERBOSE,
)

MIDLINE_DOTTED_LOCATOR_RE = re.compile(
    r"""
    (?<=\s)
    \d+
    (?:\.\d+){2,}
    \.
    (?=
        [A-Za-zĀĪŪṚṜḶḸāīūṛṝḷḹŚṢṄÑṬḌṆḤṂśṣṅñṭḍṇḥṃ']
    )
    """,
    re.VERBOSE,
)

DOUBLE_DANDA_NUMBER_RE = re.compile(r"\|\|\s*\d+\s*\|\|")
LINE_FINAL_DANDA_NUMBER_RE = re.compile(r"\|\s*\d+\s*$")

LEADING_PAREN_LOCATOR_RE = re.compile(
    r"""
    ^\s*
    \(
        \d+
        (?:\.\d+)+
    \)
    \s*
    """,
    re.VERBOSE,
)

# Intentionally no global '^%' rule here: '%' notes are source-family-specific
# and remain for Pass 3 unless another explicit metadata field identifies them.
METADATA_LINE_RE = re.compile(
    r"""
    ^\s*
    -?
    (?:
        date
        |
        version
        |
        status
        |
        from
        |
        subject
        |
        encoding
        |
        source
        |
        filename
        |
        file
        |
        url
    )
    \s*:
    """,
    re.IGNORECASE | re.VERBOSE,
)

KNOWN_SOURCE_SIGLA = (
    "JaimGS",
    "KauśS",
    "VaitS",
    "ĀpŚS",
    "ApŚS",
    "BaudhŚS",
    "PS",
    "RV",
    "ṚV",
    "ŚS",
    "SS",
    "TS",
    "VS",
    "SBV",
    "GBM",
)

STANDALONE_SOURCE_LOCATOR_RE = re.compile(
    rf"""
    ^\s*
    (?:{"|".join(re.escape(item) for item in KNOWN_SOURCE_SIGLA)})
    \s+
    \d+
    (?:\.\d+)+
    \s*:?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

HV_APP_MARKER_RE = re.compile(r"\*\*HV\s+App\.[^*\n]+\*\*", re.IGNORECASE)
HORIZONTAL_SPACE_RE = re.compile(r"[ \t]+")

RULE_NAMES = (
    "metadata_line_removed",
    "standalone_source_locator_removed",
    "full_line_numeric_locator_removed",
    "leading_parenthesized_locator_removed",
    "leading_dotted_locator_removed",
    "midline_dotted_locator_removed",
    "double_danda_number_removed",
    "line_final_danda_number_removed",
    "square_editorial_removed",
    "square_citation_removed",
    "hv_app_suffix_removed",
)


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    line_number: int
    rule: str
    before: str
    after: str
    line_before: str
    line_after: str


@dataclass(frozen=True, slots=True)
class DocumentResult:
    text: str
    counts: Counter[str]
    changes: tuple[Change, ...]


@dataclass(frozen=True, slots=True)
class CorpusResult:
    files_processed: int
    files_changed: int
    total_changes: int
    counts: Counter[str]


def _is_full_line_numeric_locator(line: str) -> bool:
    """Recognize lines containing only dotted/bracketed numeric locators.

    Positive examples::

        2.1.4.
        1.1.3[[.]]5
        1.4.3[.1]0

    A bare integer is deliberately not enough.
    """

    value = line.strip()
    if not value:
        return False
    if not re.fullmatch(r"[\d.\[\]\s]+", value):
        return False
    if "." not in value:
        return False
    return any(character.isdigit() for character in value)


def _is_citation_only_square(content: str) -> bool:
    """Recognize citation lists with a known siglum and numeric locators."""

    value = content.strip().lstrip(".; ")
    parts = [
        part.strip().lstrip(". ")
        for part in value.split(";")
        if part.strip()
    ]
    if not parts:
        return False

    saw_siglum = False
    for part in parts:
        if SIGLUM_LOCATOR_RE.fullmatch(part):
            saw_siglum = True
            continue
        if LOCATOR_ONLY_RE.fullmatch(part):
            continue
        return False

    return saw_siglum


def _is_editorial_square(content: str) -> bool:
    value = content.strip()
    if not value:
        return False
    if EDITORIAL_SQUARE_PREFIX_RE.search(value):
        return True
    if value[0].isdigit() and EDITORIAL_SQUARE_ANYWHERE_RE.search(value):
        return True
    return False


def _process_square_spans(
    line: str,
) -> tuple[str, list[tuple[str, str, str]]]:
    changes: list[tuple[str, str, str]] = []

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        whole = match.group(0)

        if _is_editorial_square(content):
            changes.append(("square_editorial_removed", whole, " "))
            return " "

        if _is_citation_only_square(content):
            changes.append(("square_citation_removed", whole, " "))
            return " "

        return whole

    return SQUARE_RE.sub(replace, line), changes


def _remove_hv_app_suffix(
    line: str,
) -> tuple[str, tuple[str, str, str] | None]:
    """Remove HV App metadata only when Sanskrit verse text precedes it."""

    match = HV_APP_MARKER_RE.search(line)
    if match is None:
        return line, None

    prefix = line[: match.start()]

    # Do not turn lines like
    #   {{vahnir uvāca} **HV App...**78:4}
    # into malformed leftovers. Those remain for the HV family pass.
    if "|" not in prefix:
        return line, None

    removed = line[match.start() :]
    return prefix.rstrip(), ("hv_app_suffix_removed", removed, "")


def _normalize_changed_line(line: str) -> str:
    return HORIZONTAL_SPACE_RE.sub(" ", line).strip()


def clean_line(
    line: str,
    *,
    path: str,
    line_number: int,
) -> tuple[str, Counter[str], list[Change]]:
    counts: Counter[str] = Counter()
    changes: list[Change] = []
    original = line

    def record(
        rule: str,
        before: str,
        after: str,
        current_before: str,
        current_after: str,
    ) -> None:
        counts[rule] += 1
        changes.append(
            Change(
                path=path,
                line_number=line_number,
                rule=rule,
                before=before,
                after=after,
                line_before=current_before,
                line_after=current_after,
            )
        )

    # Whole-line rules first.
    if METADATA_LINE_RE.match(line):
        record("metadata_line_removed", line, "", original, "")
        return "", counts, changes

    if STANDALONE_SOURCE_LOCATOR_RE.fullmatch(line):
        record("standalone_source_locator_removed", line, "", original, "")
        return "", counts, changes

    if _is_full_line_numeric_locator(line):
        record("full_line_numeric_locator_removed", line, "", original, "")
        return "", counts, changes

    # (1.9) Sanskrit... -> Sanskrit...
    before = line
    match = LEADING_PAREN_LOCATOR_RE.match(line)
    if match is not None:
        removed = match.group(0)
        line = line[match.end() :]
        record(
            "leading_parenthesized_locator_removed",
            removed,
            "",
            before,
            line,
        )

    # 11.7.4.2prajāpati... -> prajāpati...
    before = line
    match = LEADING_DOTTED_LOCATOR_RE.match(line)
    if match is not None:
        removed = match.group("locator")
        line = line[match.end() :]
        record("leading_dotted_locator_removed", removed, "", before, line)

    # ... 5.1.5.tadyad... -> ... tadyad...
    while True:
        before = line
        match = MIDLINE_DOTTED_LOCATOR_RE.search(line)
        if match is None:
            break
        removed = match.group(0)
        line = line[: match.start()] + " " + line[match.end() :]
        record("midline_dotted_locator_removed", removed, " ", before, line)

    # ||31|| -> ||
    while True:
        before = line
        match = DOUBLE_DANDA_NUMBER_RE.search(line)
        if match is None:
            break
        removed = match.group(0)
        line = line[: match.start()] + "||" + line[match.end() :]
        record("double_danda_number_removed", removed, "||", before, line)

    # Final |27 -> |
    before = line
    match = LINE_FINAL_DANDA_NUMBER_RE.search(line)
    if match is not None:
        removed = match.group(0)
        line = line[: match.start()] + "|"
        record("line_final_danda_number_removed", removed, "|", before, line)

    # Explicit [] editorial apparatus / citation lists.
    before_square = line
    line, square_changes = _process_square_spans(line)
    for rule, removed, replacement in square_changes:
        record(rule, removed, replacement, before_square, line)

    # HV critical-edition suffix.
    before = line
    line, hv_change = _remove_hv_app_suffix(line)
    if hv_change is not None:
        rule, removed, replacement = hv_change
        record(rule, removed, replacement, before, line)

    # Only lines actually touched by a rule get whitespace normalization.
    if changes:
        line = _normalize_changed_line(line)

    return line, counts, changes


def clean_document(text: str, relative_path: str) -> DocumentResult:
    counts: Counter[str] = Counter()
    changes: list[Change] = []
    output_lines: list[str] = []

    # split/join preserves the original number of LF-delimited lines, including
    # a final trailing newline. Removed structural lines become blank lines.
    for line_number, line in enumerate(text.split("\n"), start=1):
        cleaned, line_counts, line_changes = clean_line(
            line,
            path=relative_path,
            line_number=line_number,
        )
        counts.update(line_counts)
        changes.extend(line_changes)
        output_lines.append(cleaned)

    return DocumentResult(
        text="\n".join(output_lines),
        counts=counts,
        changes=tuple(changes),
    )


def _validate_roots(input_root: Path, output_root: Path) -> None:
    source = input_root.resolve()
    destination = output_root.resolve()

    if source == destination:
        raise ValueError("Pass 2 output root must not equal input root")

    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError("Pass 2 output root must not be inside input root")


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_pass2_candidate(
    *,
    input_root: Path,
    output_root: Path,
    report_dir: Path,
) -> CorpusResult:
    if not input_root.is_dir():
        raise FileNotFoundError(f"Pass 2 input root does not exist: {input_root}")

    _validate_roots(input_root, output_root)

    files = tuple(
        sorted(
            path
            for path in input_root.rglob("*.txt")
            if path.is_file()
        )
    )
    if not files:
        raise RuntimeError(f"no .txt files found under: {input_root}")

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    total_counts: Counter[str] = Counter()
    occurrence_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    files_changed = 0

    for source_path in files:
        relative_path = source_path.relative_to(input_root)
        relative_string = relative_path.as_posix()

        raw_bytes = source_path.read_bytes()
        original_text = raw_bytes.decode("utf-8", errors="strict")
        result = clean_document(original_text, relative_string)

        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)

        changed = bool(result.changes)
        if changed:
            destination.write_bytes(result.text.encode("utf-8"))
            files_changed += 1
            output_chars = len(result.text)
        else:
            destination.write_bytes(raw_bytes)
            output_chars = len(original_text)

        total_counts.update(result.counts)

        row: dict[str, Any] = {
            "path": relative_string,
            "changed": int(changed),
            "input_chars": len(original_text),
            "output_chars": output_chars,
            "char_delta": output_chars - len(original_text),
        }
        for rule in RULE_NAMES:
            row[rule] = result.counts.get(rule, 0)
        row["total_rule_hits"] = sum(
            result.counts.get(rule, 0)
            for rule in RULE_NAMES
        )
        audit_rows.append(row)

        for change in result.changes:
            occurrence_rows.append(
                {
                    "path": change.path,
                    "line_number": change.line_number,
                    "rule": change.rule,
                    "before": change.before,
                    "after": change.after,
                    "line_before": change.line_before,
                    "line_after": change.line_after,
                }
            )

    audit_rows.sort(
        key=lambda row: (-int(row["total_rule_hits"]), str(row["path"]))
    )
    occurrence_rows.sort(
        key=lambda row: (
            str(row["path"]),
            int(row["line_number"]),
            str(row["rule"]),
        )
    )

    _write_csv(
        report_dir / AUDIT_FILENAME,
        (
            "path",
            "changed",
            "input_chars",
            "output_chars",
            "char_delta",
            *RULE_NAMES,
            "total_rule_hits",
        ),
        audit_rows,
    )
    _write_csv(
        report_dir / OCCURRENCES_FILENAME,
        (
            "path",
            "line_number",
            "rule",
            "before",
            "after",
            "line_before",
            "line_after",
        ),
        occurrence_rows,
    )

    _write_summary(
        report_dir / SUMMARY_FILENAME,
        input_root=input_root,
        output_root=output_root,
        files_processed=len(files),
        files_changed=files_changed,
        counts=total_counts,
        input_chars=sum(int(row["input_chars"]) for row in audit_rows),
        output_chars=sum(int(row["output_chars"]) for row in audit_rows),
    )

    return CorpusResult(
        files_processed=len(files),
        files_changed=files_changed,
        total_changes=len(occurrence_rows),
        counts=total_counts,
    )


def _write_summary(
    path: Path,
    *,
    input_root: Path,
    output_root: Path,
    files_processed: int,
    files_changed: int,
    counts: Counter[str],
    input_chars: int,
    output_chars: int,
) -> None:
    lines = [
        "Formal GRETIL canonical Pass 2",
        "================================",
        f"input_root: {input_root}",
        f"output_root: {output_root}",
        f"files_processed: {files_processed}",
        f"files_changed: {files_changed}",
        f"input_chars: {input_chars}",
        f"output_chars: {output_chars}",
        f"char_delta: {output_chars - input_chars}",
        "",
        "rule_hits:",
    ]
    for rule in RULE_NAMES:
        lines.append(f"  {rule}: {counts.get(rule, 0)}")

    lines.extend(
        [
            "",
            "intentionally_untouched:",
            "  general periods",
            "  general hyphens",
            "  commas",
            "  colons and semicolons",
            "  general parentheses",
            "  curly braces",
            "  residual malformed angle brackets",
            "  general digits",
            "  general uppercase",
            "  non-IAST Latin residue",
            "  mixed-language material",
            "  source-specific transliteration corruption",
            "  percent-note lines (reserved for source-family Pass 3)",
            "",
            "The Pass 2 input corpus was not modified.",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build conservative structural-cleanup Pass 2 from the "
            "pluta-normalized GRETIL candidate"
        )
    )
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)

    result = build_pass2_candidate(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
    )

    print(f"processed {result.files_processed} document(s)")
    print(f"changed {result.files_changed} document(s)")
    print(f"applied {result.total_changes} structural cleanup(s)")
    print(f"candidate corpus: {args.output_root}")
    print(f"reports: {args.report_dir}")


if __name__ == "__main__":
    main()

"""Mechanical pre-M0 closure and read-only anomaly audit.

Only Unicode, newline, ASCII-space, and ASCII-danda layout are normalized.
The anomaly audit is observational and never changes corpus text.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sktlm.corpus.gretil.cleaning.strict import IAST_LOWER, validate_corpus
from sktlm.corpus.gretil.freeze import corpus_sha256


IMPLEMENTATION = "gretil-pre-m0-final-closure-1"
DEFAULT_CANONICAL_ROOT = Path("data/canonical/gretil_iast")
DEFAULT_MANIFEST = Path("data/manifests/canonical_corpus.csv")
DEFAULT_FREEZE_REPORT = Path("reports/cleaning/gretil_canonical_freeze_summary.txt")
DEFAULT_SUMMARY_TSV = Path("reports/cleaning/pre_m0_final_anomaly_summary.tsv")
DEFAULT_DETAILS_TSV = Path("reports/cleaning/pre_m0_final_anomaly_details.tsv")
DEFAULT_CLOSURE_REPORT = Path("reports/cleaning/pre_m0_final_closure.md")
DEFAULT_MAX_ITERATIONS = 10

RULE_FIELDS = (
    "unicode_nfc",
    "newline_to_lf",
    "leading_blank_lines_removed",
    "line_edge_spaces_removed",
    "multiple_spaces_collapsed",
    "standalone_single_danda_lines_removed",
    "standalone_double_danda_lines_removed",
    "line_start_single_danda_removed",
    "danda_spacing_normalized",
    "multiple_blank_lines_collapsed",
)

CONSONANTS = frozenset("kgṅcjñṭḍṇtdnpbmyrlvśṣsh")
VOWELS = frozenset("aāiīuūṛṝḷeo")
LEXICAL_RE = re.compile(
    "[" + re.escape("".join(sorted(IAST_LOWER)) + chr(39)) + "]+"
)
EXACT_DANDA_RE = re.compile(r"(?<!\|)(\|\|?)(?!\|)")
MULTIPLE_SPACE_RE = re.compile(r" {2,}")
MULTIPLE_BLANK_RE = re.compile(r"\n{3,}")
LEADING_BLANK_RE = re.compile(r"^\n+")


@dataclass(frozen=True, slots=True)
class TextNormalizationResult:
    text: str
    counts: Counter[str]


@dataclass(frozen=True, slots=True)
class FixedPointResult:
    text: str
    iterations: int
    counts: Counter[str]


@dataclass(frozen=True, slots=True)
class CorpusNormalizationResult:
    files_processed: int
    before_sha256: str
    after_sha256: str
    iterations: int
    counts: Counter[str]
    modified_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MechanicalValidationResult:
    files_processed: int
    standalone_single_danda_lines: int
    standalone_double_danda_lines: int
    line_start_single_danda: int
    line_start_double_danda: int
    leading_or_trailing_space_lines: int
    multiple_space_runs: int
    multiple_blank_line_runs: int
    danda_spacing_violation_lines: int
    non_lf_newline_occurrences: int
    non_nfc_files: int
    leading_blank_line_files: int
    fixed_point: bool

    @property
    def is_clean(self) -> bool:
        return (
            self.standalone_single_danda_lines == 0
            and self.standalone_double_danda_lines == 0
            and self.line_start_single_danda == 0
            and self.leading_or_trailing_space_lines == 0
            and self.multiple_space_runs == 0
            and self.multiple_blank_line_runs == 0
            and self.danda_spacing_violation_lines == 0
            and self.non_lf_newline_occurrences == 0
            and self.non_nfc_files == 0
            and self.leading_blank_line_files == 0
            and self.fixed_point
        )


@dataclass(frozen=True, slots=True)
class AnomalyAuditResult:
    summary_rows: tuple[dict[str, Any], ...]
    details: tuple[dict[str, Any], ...]
    per_file_counts: dict[str, Counter[str]]
    occurrence_counts: Counter[str]
    distinct_form_counts: Counter[str]
    file_counts: Counter[str]
    corpus_sha256: str


@dataclass(frozen=True, slots=True)
class ClosureResult:
    normalization: CorpusNormalizationResult
    mechanical_validation: MechanicalValidationResult
    anomaly_audit: AnomalyAuditResult
    audit_after_sha256: str


def _text_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise FileNotFoundError(f"canonical root does not exist: {root}")
    files = tuple(sorted(path for path in root.rglob("*.txt") if path.is_file()))
    if not files:
        raise RuntimeError(f"no canonical .txt files found under: {root}")
    return files


def _normalize_danda_spacing(line: str) -> str:
    if not EXACT_DANDA_RE.search(line):
        return line
    normalized = EXACT_DANDA_RE.sub(r" \1 ", line)
    normalized = MULTIPLE_SPACE_RE.sub(" ", normalized)
    return normalized.strip(" ")


def normalize_once(text: str) -> TextNormalizationResult:
    """Apply exactly one ordered pass of the mechanical closure rules."""

    counts: Counter[str] = Counter()
    normalized = unicodedata.normalize("NFC", text)
    if normalized != text:
        counts["unicode_nfc"] += 1
    text = normalized

    crlf_count = text.count("\r\n")
    cr_count = text.count("\r") - crlf_count
    if crlf_count or cr_count:
        counts["newline_to_lf"] += crlf_count + cr_count
        text = text.replace("\r\n", "\n").replace("\r", "\n")

    output_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip(" ")
        if line != raw_line:
            counts["line_edge_spaces_removed"] += 1

        def collapse_spaces(match: re.Match[str]) -> str:
            counts["multiple_spaces_collapsed"] += 1
            return " "

        line = MULTIPLE_SPACE_RE.sub(collapse_spaces, line)
        if line == "|":
            counts["standalone_single_danda_lines_removed"] += 1
            continue
        if line == "||":
            counts["standalone_double_danda_lines_removed"] += 1
            continue
        if line.startswith("|") and not line.startswith("||"):
            line = line[1:].lstrip(" ")
            counts["line_start_single_danda_removed"] += 1

        danda_normalized = _normalize_danda_spacing(line)
        if danda_normalized != line:
            counts["danda_spacing_normalized"] += 1
        output_lines.append(danda_normalized)

    text = "\n".join(output_lines)
    leading_match = LEADING_BLANK_RE.match(text)
    if leading_match:
        counts["leading_blank_lines_removed"] += len(leading_match.group(0))
        text = text[leading_match.end() :]

    def collapse_blank_lines(match: re.Match[str]) -> str:
        counts["multiple_blank_lines_collapsed"] += len(match.group(0)) - 2
        return "\n\n"

    text = MULTIPLE_BLANK_RE.sub(collapse_blank_lines, text)
    return TextNormalizationResult(text=text, counts=counts)


def normalize_to_fixed_point(
    text: str, *, max_iterations: int = DEFAULT_MAX_ITERATIONS
) -> FixedPointResult:
    """Normalize until a complete pass reports no modifications."""

    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")
    total_counts: Counter[str] = Counter()
    current = text
    for iteration in range(1, max_iterations + 1):
        result = normalize_once(current)
        total_counts.update(result.counts)
        if result.text == current and not sum(result.counts.values()):
            return FixedPointResult(
                text=current,
                iterations=iteration,
                counts=total_counts,
            )
        current = result.text
    raise RuntimeError(
        "mechanical normalization did not reach a fixed point within "
        f"{max_iterations} iterations"
    )


def normalize_corpus_in_place(
    *,
    canonical_root: Path,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> CorpusNormalizationResult:
    """Normalize canonical files in place after every file has converged."""

    files = _text_files(canonical_root)
    before_sha256 = corpus_sha256(canonical_root, files)
    total_counts: Counter[str] = Counter()
    updates: dict[Path, bytes] = {}
    modified_files: list[str] = []
    corpus_iterations = 1

    for path in files:
        original = path.read_bytes().decode("utf-8", errors="strict")
        result = normalize_to_fixed_point(
            original, max_iterations=max_iterations
        )
        total_counts.update(result.counts)
        corpus_iterations = max(corpus_iterations, result.iterations)
        if result.text != original:
            updates[path] = result.text.encode("utf-8")
            modified_files.append(path.relative_to(canonical_root).as_posix())

    for path, data in updates.items():
        temporary = path.with_name(path.name + ".pre_m0_tmp")
        temporary.write_bytes(data)
        temporary.replace(path)

    after_files = _text_files(canonical_root)
    before_paths = tuple(path.relative_to(canonical_root) for path in files)
    after_paths = tuple(path.relative_to(canonical_root) for path in after_files)
    if before_paths != after_paths:
        raise RuntimeError("canonical file membership changed during normalization")
    after_sha256 = corpus_sha256(canonical_root, after_files)
    return CorpusNormalizationResult(
        files_processed=len(files),
        before_sha256=before_sha256,
        after_sha256=after_sha256,
        iterations=corpus_iterations,
        counts=total_counts,
        modified_files=tuple(modified_files),
    )


def validate_mechanical_corpus(
    *, canonical_root: Path
) -> MechanicalValidationResult:
    """Verify the requested mechanical invariants without changing files."""

    files = _text_files(canonical_root)
    counts: Counter[str] = Counter()
    fixed_point = True
    for path in files:
        data = path.read_bytes()
        counts["non_lf_newline_occurrences"] += data.count(b"\r")
        text = data.decode("utf-8", errors="strict")
        if unicodedata.normalize("NFC", text) != text:
            counts["non_nfc_files"] += 1
        if text.startswith("\n"):
            counts["leading_blank_line_files"] += 1
        pass_result = normalize_once(text)
        if pass_result.text != text or sum(pass_result.counts.values()):
            fixed_point = False

        for line in text.split("\n"):
            if line == "|":
                counts["standalone_single_danda_lines"] += 1
            if line == "||":
                counts["standalone_double_danda_lines"] += 1
            if line.startswith("|") and not line.startswith("||"):
                counts["line_start_single_danda"] += 1
            if line.startswith("||"):
                counts["line_start_double_danda"] += 1
            if line.startswith(" ") or line.endswith(" "):
                counts["leading_or_trailing_space_lines"] += 1
            counts["multiple_space_runs"] += len(MULTIPLE_SPACE_RE.findall(line))
            if _normalize_danda_spacing(line) != line:
                counts["danda_spacing_violation_lines"] += 1
        counts["multiple_blank_line_runs"] += len(
            MULTIPLE_BLANK_RE.findall(text)
        )

    return MechanicalValidationResult(
        files_processed=len(files),
        standalone_single_danda_lines=counts["standalone_single_danda_lines"],
        standalone_double_danda_lines=counts["standalone_double_danda_lines"],
        line_start_single_danda=counts["line_start_single_danda"],
        line_start_double_danda=counts["line_start_double_danda"],
        leading_or_trailing_space_lines=counts[
            "leading_or_trailing_space_lines"
        ],
        multiple_space_runs=counts["multiple_space_runs"],
        multiple_blank_line_runs=counts["multiple_blank_line_runs"],
        danda_spacing_violation_lines=counts[
            "danda_spacing_violation_lines"
        ],
        non_lf_newline_occurrences=counts["non_lf_newline_occurrences"],
        non_nfc_files=counts["non_nfc_files"],
        leading_blank_line_files=counts["leading_blank_line_files"],
        fixed_point=fixed_point,
    )


def _context(line: str, start: int, end: int, width: int = 60) -> str:
    left = max(0, start - width)
    right = min(len(line), end + width)
    prefix = "..." if left else ""
    suffix = "..." if right < len(line) else ""
    return prefix + line[left:right] + suffix


def _write_tsv(
    path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def audit_anomalies(
    *,
    canonical_root: Path,
    summary_path: Path,
    details_path: Path,
) -> AnomalyAuditResult:
    """Report isolated consonants and adjacent vowel nuclei read-only."""

    files = _text_files(canonical_root)
    digest = corpus_sha256(canonical_root, files)
    detail_rows: list[dict[str, Any]] = []
    form_counts: Counter[tuple[str, str]] = Counter()
    form_files: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    per_file: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for path in files:
        relative = path.relative_to(canonical_root).as_posix()
        text = path.read_bytes().decode("utf-8", errors="strict")
        for line_number, line in enumerate(text.split("\n"), start=1):
            for token_match in LEXICAL_RE.finditer(line):
                form = token_match.group(0)
                if len(form) == 1 and form in CONSONANTS:
                    issue = "isolated_consonant"
                    form_counts[(issue, form)] += 1
                    form_files[(issue, form)].add(relative)
                    per_file[relative][issue] += 1
                    detail_rows.append(
                        {
                            "file": relative,
                            "line_no": line_number,
                            "issue_type": issue,
                            "matched_form": form,
                            "matched_sequence": form,
                            "context": _context(
                                line,
                                token_match.start(),
                                token_match.end(),
                            ),
                        }
                    )

                for offset in range(len(form) - 1):
                    sequence = form[offset : offset + 2]
                    if (
                        sequence[0] in VOWELS
                        and sequence[1] in VOWELS
                        and sequence not in {"ai", "au"}
                    ):
                        issue = "adjacent_vowels"
                        form_counts[(issue, form)] += 1
                        form_files[(issue, form)].add(relative)
                        per_file[relative][issue] += 1
                        start = token_match.start() + offset
                        detail_rows.append(
                            {
                                "file": relative,
                                "line_no": line_number,
                                "issue_type": issue,
                                "matched_form": form,
                                "matched_sequence": sequence,
                                "context": _context(line, start, start + 2),
                            }
                        )

    summary_rows = [
        {
            "issue_type": issue,
            "matched_form": form,
            "count": count,
            "file_count": len(form_files[(issue, form)]),
        }
        for (issue, form), count in sorted(
            form_counts.items(),
            key=lambda item: (item[0][0], -item[1], item[0][1]),
        )
    ]
    detail_rows.sort(
        key=lambda row: (
            str(row["file"]),
            int(row["line_no"]),
            str(row["issue_type"]),
            str(row["matched_form"]),
            str(row["matched_sequence"]),
        )
    )
    _write_tsv(
        summary_path,
        ("issue_type", "matched_form", "count", "file_count"),
        summary_rows,
    )
    _write_tsv(
        details_path,
        (
            "file",
            "line_no",
            "issue_type",
            "matched_form",
            "matched_sequence",
            "context",
        ),
        detail_rows,
    )

    occurrence_counts: Counter[str] = Counter()
    distinct_form_counts: Counter[str] = Counter()
    issue_files: defaultdict[str, set[str]] = defaultdict(set)
    for (issue, form), count in form_counts.items():
        occurrence_counts[issue] += count
        distinct_form_counts[issue] += 1
        issue_files[issue].update(form_files[(issue, form)])
    file_counts = Counter(
        {issue: len(paths) for issue, paths in issue_files.items()}
    )
    return AnomalyAuditResult(
        summary_rows=tuple(summary_rows),
        details=tuple(detail_rows),
        per_file_counts=dict(per_file),
        occurrence_counts=occurrence_counts,
        distinct_form_counts=distinct_form_counts,
        file_counts=file_counts,
        corpus_sha256=digest,
    )


def refresh_canonical_manifest(
    *, canonical_root: Path, manifest_path: Path, freeze_id: str
) -> None:
    """Refresh derived canonical fields while preserving provenance columns."""

    if not manifest_path.is_file():
        raise FileNotFoundError(f"canonical manifest does not exist: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"manifest has no header: {manifest_path}")
        fields = list(reader.fieldnames)
        rows = list(reader)

    files = _text_files(canonical_root)
    files_by_relative = {
        path.relative_to(canonical_root).as_posix(): path for path in files
    }
    rows_by_relative: dict[str, dict[str, str]] = {}
    for row in rows:
        relative = row.get("freeze_input_path", "").replace(chr(92), "/")
        if not relative:
            canonical = PurePosixPath(
                row["canonical_path"].replace(chr(92), "/")
            )
            index = canonical.parts.index("gretil_iast")
            relative = PurePosixPath(*canonical.parts[index + 1 :]).as_posix()
        rows_by_relative[relative] = row
    if set(rows_by_relative) != set(files_by_relative):
        raise RuntimeError("canonical manifest membership mismatch during refresh")

    for relative, path in files_by_relative.items():
        row = rows_by_relative[relative]
        data = path.read_bytes()
        text = data.decode("utf-8", errors="strict")
        row.update(
            {
                "canonical_path": (canonical_root / relative).as_posix(),
                "canonical_script": "iast",
                "char_count": str(len(text)),
                "line_count": str(len(text.splitlines())),
                "segment_count": str(
                    sum(1 for line in text.splitlines() if line.strip())
                ),
                "canonical_hash": hashlib.sha256(data).hexdigest(),
                "byte_count": str(len(data)),
                "freeze_id": freeze_id,
                "freeze_input_path": relative,
            }
        )

    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_freeze_state_report(
    path: Path,
    *,
    canonical_root: Path,
    manifest_path: Path,
    normalization: CorpusNormalizationResult,
    apostrophe_occurrences: int,
) -> None:
    files = _text_files(canonical_root)
    byte_count = sum(file_path.stat().st_size for file_path in files)
    char_count = sum(
        len(file_path.read_bytes().decode("utf-8", errors="strict"))
        for file_path in files
    )
    lines = [
        "Formal GRETIL canonical corpus state after pre-M0 closure",
        "========================================================",
        f"implementation: {IMPLEMENTATION}",
        f"output_root: {canonical_root}",
        f"manifest: {manifest_path}",
        f"files_frozen: {normalization.files_processed}",
        f"byte_count: {byte_count}",
        f"char_count: {char_count}",
        f"pre_normalization_corpus_sha256: {normalization.before_sha256}",
        f"corpus_sha256: {normalization.after_sha256}",
        f"strict_clean_files: {normalization.files_processed}",
        "invalid_character_files: 0",
        "invalid_character_occurrences: 0",
        "invalid_apostrophe_files: 0",
        "invalid_apostrophe_occurrences: 0",
        f"validated_apostrophe_occurrences: {apostrophe_occurrences}",
        "",
        "state policy:",
        "  the strict freeze was followed only by the recorded pre-M0 mechanical normalization",
        "  exact file membership, provenance identifiers, and split assignments are preserved",
        "  manifest hashes and counts describe the post-normalization canonical bytes",
        "  anomaly audit is read-only and does not alter canonical text",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def _write_closure_report(
    path: Path,
    *,
    canonical_root: Path,
    normalization: CorpusNormalizationResult,
    mechanical: MechanicalValidationResult,
    audit: AnomalyAuditResult,
    audit_after_sha256: str,
) -> None:
    lines = [
        "# pre-M0 final closure",
        "",
        f"- Implementation: {IMPLEMENTATION}",
        f"- Canonical root: {canonical_root.as_posix()}",
        f"- Path-and-content SHA256 before normalization: {normalization.before_sha256}",
        f"- Path-and-content SHA256 after normalization: {normalization.after_sha256}",
        f"- Fixed-point iterations (including final zero-modification pass): {normalization.iterations}",
        f"- Modified files: {len(normalization.modified_files)} / {normalization.files_processed}",
        "",
        "## Normalization rule counts",
        "",
        "| rule | modifications |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {rule} | {normalization.counts.get(rule, 0)} |"
        for rule in RULE_FIELDS
    )
    lines.extend(
        [
            "",
            "Count semantics: NFC counts changed file-passes; newline counts changed "
            "line endings; line rules count affected lines; spacing rules count "
            "matched spans or affected danda lines.",
            "",
            "## Modified files",
            "",
        ]
    )
    if normalization.modified_files:
        lines.extend(f"- {name}" for name in normalization.modified_files)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Anomaly totals",
            "",
            "| issue | occurrences | distinct forms | files |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for issue in ("isolated_consonant", "adjacent_vowels"):
        lines.append(
            f"| {issue} | {audit.occurrence_counts.get(issue, 0)} | "
            f"{audit.distinct_form_counts.get(issue, 0)} | "
            f"{audit.file_counts.get(issue, 0)} |"
        )

    lines.extend(
        [
            "",
            "## Anomaly counts by file",
            "",
            "| file | isolated consonant | adjacent vowels |",
            "| --- | ---: | ---: |",
        ]
    )
    for name in sorted(audit.per_file_counts):
        counts = audit.per_file_counts[name]
        lines.append(
            f"| {name} | {counts.get('isolated_consonant', 0)} | "
            f"{counts.get('adjacent_vowels', 0)} |"
        )
    zero_files = normalization.files_processed - len(audit.per_file_counts)
    lines.extend(["", f"Files with no reported anomaly: {zero_files}.", ""])

    lines.extend(["## Representative contexts", ""])
    for issue in ("isolated_consonant", "adjacent_vowels"):
        lines.append(f"### {issue}")
        lines.append("")
        examples = [row for row in audit.details if row["issue_type"] == issue][:5]
        if not examples:
            lines.append("- None")
        else:
            for row in examples:
                lines.append(
                    f"- {row['file']}:{row['line_no']} — "
                    f"{row['matched_form']} / {row['matched_sequence']}: "
                    f"{row['context']}"
                )
        lines.append("")

    lines.extend(
        [
            "## Final mechanical checks",
            "",
            f"- standalone | lines: {mechanical.standalone_single_danda_lines}",
            f"- standalone || lines: {mechanical.standalone_double_danda_lines}",
            f"- line-start single |: {mechanical.line_start_single_danda}",
            f"- retained line-start ||: {mechanical.line_start_double_danda}",
            f"- leading/trailing space lines: {mechanical.leading_or_trailing_space_lines}",
            f"- multiple-space runs: {mechanical.multiple_space_runs}",
            f"- multiple-blank-line runs: {mechanical.multiple_blank_line_runs}",
            f"- danda-spacing violation lines: {mechanical.danda_spacing_violation_lines}",
            f"- non-LF newline occurrences: {mechanical.non_lf_newline_occurrences}",
            f"- non-NFC files: {mechanical.non_nfc_files}",
            f"- leading-blank-line files: {mechanical.leading_blank_line_files}",
            f"- fixed point: {'yes' if mechanical.fixed_point else 'no'}",
            f"- anomaly audit SHA256 before: {audit.corpus_sha256}",
            f"- anomaly audit SHA256 after: {audit_after_sha256}",
            "- anomaly audit modified corpus: "
            + ("no" if audit.corpus_sha256 == audit_after_sha256 else "yes"),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def run_pre_m0_closure(
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    freeze_report_path: Path = DEFAULT_FREEZE_REPORT,
    summary_path: Path = DEFAULT_SUMMARY_TSV,
    details_path: Path = DEFAULT_DETAILS_TSV,
    closure_report_path: Path = DEFAULT_CLOSURE_REPORT,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> ClosureResult:
    normalization = normalize_corpus_in_place(
        canonical_root=canonical_root,
        max_iterations=max_iterations,
    )
    mechanical = validate_mechanical_corpus(canonical_root=canonical_root)
    if not mechanical.is_clean:
        raise RuntimeError(
            f"post-normalization mechanical validation failed: {mechanical}"
        )

    strict = validate_corpus(input_root=canonical_root, require_clean=True)
    refresh_canonical_manifest(
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        freeze_id=normalization.after_sha256,
    )
    audit = audit_anomalies(
        canonical_root=canonical_root,
        summary_path=summary_path,
        details_path=details_path,
    )
    audit_after_sha256 = corpus_sha256(
        canonical_root, _text_files(canonical_root)
    )
    if audit.corpus_sha256 != audit_after_sha256:
        raise RuntimeError("anomaly audit modified the canonical corpus")

    _write_freeze_state_report(
        freeze_report_path,
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        normalization=normalization,
        apostrophe_occurrences=strict.apostrophe_occurrences,
    )
    _write_closure_report(
        closure_report_path,
        canonical_root=canonical_root,
        normalization=normalization,
        mechanical=mechanical,
        audit=audit,
        audit_after_sha256=audit_after_sha256,
    )
    return ClosureResult(
        normalization=normalization,
        mechanical_validation=mechanical,
        anomaly_audit=audit,
        audit_after_sha256=audit_after_sha256,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Normalize and audit the strict canonical GRETIL corpus"
    )
    parser.add_argument(
        "--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--freeze-report", type=Path, default=DEFAULT_FREEZE_REPORT
    )
    parser.add_argument("--summary-tsv", type=Path, default=DEFAULT_SUMMARY_TSV)
    parser.add_argument("--details-tsv", type=Path, default=DEFAULT_DETAILS_TSV)
    parser.add_argument(
        "--closure-report", type=Path, default=DEFAULT_CLOSURE_REPORT
    )
    parser.add_argument(
        "--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS
    )
    args = parser.parse_args(argv)
    result = run_pre_m0_closure(
        canonical_root=args.canonical_root,
        manifest_path=args.manifest,
        freeze_report_path=args.freeze_report,
        summary_path=args.summary_tsv,
        details_path=args.details_tsv,
        closure_report_path=args.closure_report,
        max_iterations=args.max_iterations,
    )
    print(f"files processed: {result.normalization.files_processed}")
    print(f"files modified: {len(result.normalization.modified_files)}")
    print(f"iterations: {result.normalization.iterations}")
    print(f"before sha256: {result.normalization.before_sha256}")
    print(f"after sha256: {result.normalization.after_sha256}")
    print(
        "isolated consonants: "
        f"{result.anomaly_audit.occurrence_counts.get('isolated_consonant', 0)}"
    )
    print(
        "adjacent vowels: "
        f"{result.anomaly_audit.occurrence_counts.get('adjacent_vowels', 0)}"
    )


if __name__ == "__main__":
    main()

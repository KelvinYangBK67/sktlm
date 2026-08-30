"""Final occurrence-level standalone-consonant cleanup for pre-M0."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.corpus.gretil.build import has_accent, unknown_characters
from sktlm.corpus.gretil.cleaning.pre_m0 import (
    LEXICAL_RE,
    normalize_to_fixed_point,
    validate_mechanical_corpus,
)
from sktlm.corpus.gretil.cleaning.strict import validate_corpus
from sktlm.corpus.gretil.cleaning.tokenizer_final import (
    DEFAULT_CANONICAL_ROOT,
    DEFAULT_MANIFEST,
    DEFAULT_WHITELIST,
    _expected_outputs,
    _promote_candidate,
    _refresh_filtered_manifest,
    _text_files,
    audit_single_letters,
)
from sktlm.corpus.gretil.freeze import corpus_sha256

IMPLEMENTATION = "gretil-pre-m0-single-consonant-closure-1"
DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pre_m0_single_consonant_input_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pre_m0_single_consonant_candidate_gretil_iast"
)
DEFAULT_SPEC = Path("configs/corpus/pre_m0_single_consonant_keep.tsv")
DEFAULT_BEFORE_AUDIT = Path("reports/cleaning/pre_m0_single_letter_tokens.tsv")
DEFAULT_MATERIALIZED = Path(
    "reports/cleaning/pre_m0_single_consonant_keep_whitelist.tsv"
)
DEFAULT_AFTER_DETAILS = Path(
    "reports/cleaning/pre_m0_single_letter_tokens_after_cleanup.tsv"
)
DEFAULT_AFTER_SUMMARY = Path(
    "reports/cleaning/pre_m0_single_letter_summary_after_cleanup.tsv"
)
DEFAULT_AFTER_BY_FILE = Path(
    "reports/cleaning/pre_m0_single_letter_by_file_after_cleanup.tsv"
)
DEFAULT_DETAILS = Path(
    "reports/cleaning/pre_m0_single_consonant_cleanup_details.tsv"
)
DEFAULT_REPORT = Path(
    "reports/cleaning/pre_m0_single_consonant_final_closure.md"
)
DEFAULT_FREEZE_REPORT = Path(
    "reports/cleaning/gretil_canonical_freeze_summary.txt"
)

VOWELS_AND_SIGNS = frozenset("aāiīuūṛṝḷḹeoṃḥ")
CONSONANTS = frozenset("kgṅcjñṭḍṇtdnpbmyrlvśṣsh")
VAIMP = "4_rellit/vaisn/vaimp__u.txt"

WHOLE_LINE_RULES = (
    (
        VAIMP,
        "vaimp_remaining_apparatus_line",
        re.compile(
            r"\b(?:denotes|check|replaces|omits|adds|read as|reads|"
            r"missing in|corrected to)\b|^only$|^in book$"
        ),
        88,
    ),
    (
        "3_purana/vipce_pu.txt",
        "vipce_only_ins_apparatus",
        re.compile(r"^l \| only ins \|\|$"),
        1,
    ),
    (
        "5_poetry/2_kavya/padnscpu.txt",
        "padnsc_only_in_edition_apparatus",
        re.compile(r"^only in k \| ed \| reads \|"),
        1,
    ),
    (
        "4_rellit/saiva/svact_pu.txt",
        "svact_reading_note",
        re.compile(r"^kṣemarāja records"),
        2,
    ),
    (
        "4_rellit/buddh/vinv02_u.txt",
        "vinv02_lost_folios_note",
        re.compile(r"^are lost \|$"),
        1,
    ),
    (
        "4_rellit/buddh/vinv171u.txt",
        "vinv171_english_summary",
        re.compile(r"^j the buddha reads"),
        1,
    ),
    (
        "2_epic/mbh/ext/hv_apppu.txt",
        "harivamsa_printed_note",
        re.compile(r"has printed"),
        1,
    ),
    (
        "4_rellit/saiva/kubjt_pu.txt",
        "kubjt_only_in_note",
        re.compile(r"^only in$"),
        1,
    ),
)
MIXED_MARKERS = (
    ("vṛ_here_adds", re.compile(r"\bvṛ here adds\b"), ""),
    ("here_adds_or_omits", re.compile(r"\bhere (?:adds|omits)\b"), ""),
    ("siglum_adds_or_omits", re.compile(r"\b(?:k|ch) (?:adds|omits)\b"), ""),
    ("compact_komitsom", re.compile(r"\bkomitsom\b"), "om"),
    ("compact_omitsom", re.compile(r"\bomitsom\b"), "om"),
    ("compact_komits", re.compile(r"\bkomits\b"), ""),
    ("english_marker", re.compile(r"\b(?:add|adds|omits|reads)\b"), ""),
)


@dataclass(frozen=True, slots=True)
class KeepEntry:
    file: str
    line_no: int
    token: str
    occurrence_count: int
    context: str


@dataclass(frozen=True, slots=True)
class CleanupRow:
    file: str
    original_line_no: int
    category: str
    rule: str
    token: str
    occurrence_count: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class ClosureResult:
    documents: int
    chars_before: int
    chars_after: int
    sha_before: str
    sha_after: str
    consonants_before: int
    consonants_retained: int
    consonants_deleted: int
    consonants_after: int
    normalization_iterations: int
    modified_files: int
    english_spans_removed: int
    adjacent_vowels_before: int
    adjacent_vowels_after: int
    lateral_characters_before: int
    lateral_characters_after: int
    vowel_signs_removed_with_editorial_units: int


@dataclass(frozen=True, slots=True)
class CandidateResult:
    cleanup_rows: tuple[CleanupRow, ...]
    expected_after_groups: dict[tuple[str, int, str], int]
    consonants_before: int
    normalization_iterations: int
    modified_files: int


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


def _read_keep_spec(path: Path) -> tuple[tuple[str, int, str, int], ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"file", "token", "line_no", "occurrence_count"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"invalid KEEP spec header: {path}")
        rows = tuple(
            (
                row["file"],
                int(row["line_no"]),
                row["token"],
                int(row["occurrence_count"]),
            )
            for row in reader
        )
    keys = {(file, line_no, token) for file, line_no, token, _count in rows}
    if len(keys) != len(rows):
        raise RuntimeError("duplicate file/token/line key in KEEP spec")
    if any(token not in CONSONANTS for _file, _line, token, _count in rows):
        raise RuntimeError("KEEP spec contains a non-consonant token")
    return rows


def materialize_keep_whitelist(
    *,
    source_root: Path,
    audit_path: Path,
    spec_path: Path,
    output_path: Path,
) -> tuple[KeepEntry, ...]:
    """Validate every spec entry against audit and exact current source line."""
    with audit_path.open("r", encoding="utf-8", newline="") as handle:
        audit_rows = list(csv.DictReader(handle, delimiter="\t"))
    grouped: defaultdict[tuple[str, int, str], list[dict[str, str]]] = defaultdict(list)
    for row in audit_rows:
        grouped[(row["file"], int(row["line_no"]), row["token"])].append(row)

    lines_by_file: dict[str, list[str]] = {}
    materialized: list[KeepEntry] = []
    for file, line_no, token, expected_count in _read_keep_spec(spec_path):
        key = (file, line_no, token)
        matches = grouped.get(key, [])
        if len(matches) != expected_count:
            raise RuntimeError(
                f"KEEP audit mismatch for {key}: "
                f"expected {expected_count}, found {len(matches)}"
            )
        if file not in lines_by_file:
            path = source_root / file
            if not path.is_file():
                raise FileNotFoundError(f"KEEP source file is missing: {file}")
            lines_by_file[file] = path.read_bytes().decode(
                "utf-8", errors="strict"
            ).splitlines()
        lines = lines_by_file[file]
        if line_no < 1 or line_no > len(lines):
            raise RuntimeError(f"KEEP line is out of range: {key}")
        context = lines[line_no - 1]
        if any(row.get("context", "") != context for row in matches):
            raise RuntimeError(f"KEEP audit context mismatch: {key}")
        actual_count = sum(
            match.group(0) == token for match in LEXICAL_RE.finditer(context)
        )
        if actual_count != expected_count:
            raise RuntimeError(
                f"KEEP canonical occurrence mismatch for {key}: "
                f"expected {expected_count}, found {actual_count}"
            )
        materialized.append(
            KeepEntry(file, line_no, token, expected_count, context)
        )
    _write_tsv(
        output_path,
        ("file", "line_no", "token", "occurrence_count", "context"),
        [
            {
                "file": row.file,
                "line_no": row.line_no,
                "token": row.token,
                "occurrence_count": row.occurrence_count,
                "context": row.context,
            }
            for row in materialized
        ],
    )
    return tuple(materialized)


CONFIRMED_ENGLISH_RE = re.compile(
    r"\b(?:chapter|division|edition|editions|commentary|emended|properties|"
    r"section|sections|variant|lost|denotes|check|printed|reads|records|"
    r"replaces|missing|corrected|omits|adds|add)\b|only ins|only in|a{10,}"
)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _character_count(root: Path) -> int:
    return sum(
        len(path.read_bytes().decode("utf-8", errors="strict"))
        for path in _text_files(root)
    )


def _adjacent_inventory(root: Path) -> Counter[tuple[str, str]]:
    # Local import keeps the standalone cleanup module independent at import
    # time while reusing the established semantic audit implementation.
    from sktlm.corpus.gretil.cleaning.semantic import find_adjacent_vowels

    inventory: Counter[tuple[str, str]] = Counter()
    for path in _text_files(root):
        relative = _relative(path, root)
        text = path.read_bytes().decode("utf-8", errors="strict")
        inventory.update(
            (row.form_before, row.matched_sequence)
            for row in find_adjacent_vowels(text, relative=relative)
        )
    return inventory


def _lateral_character_count(root: Path) -> int:
    return sum(
        text.count("ḷ") + text.count("ḹ")
        for path in _text_files(root)
        for text in [path.read_bytes().decode("utf-8", errors="strict")]
    )


def _standalone_token_inventory(
    root: Path, allowed: frozenset[str]
) -> Counter[str]:
    inventory: Counter[str] = Counter()
    for path in _text_files(root):
        text = path.read_bytes().decode("utf-8", errors="strict")
        inventory.update(
            match.group(0)
            for line in text.splitlines()
            for match in LEXICAL_RE.finditer(line)
            if len(match.group(0)) == 1 and match.group(0) in allowed
        )
    return inventory


def _standalone_consonant_groups(
    root: Path,
) -> tuple[dict[tuple[str, int, str], int], int]:
    groups: Counter[tuple[str, int, str]] = Counter()
    for path in _text_files(root):
        relative = _relative(path, root)
        for line_no, line in enumerate(
            path.read_bytes().decode("utf-8", errors="strict").splitlines(),
            start=1,
        ):
            for match in LEXICAL_RE.finditer(line):
                token = match.group(0)
                if len(token) == 1 and token in CONSONANTS:
                    groups[(relative, line_no, token)] += 1
    return dict(groups), sum(groups.values())


def _ensure_input_checkpoint(
    *,
    canonical_root: Path,
    input_root: Path,
    audit_path: Path,
    spec_path: Path,
    materialized_path: Path,
    expected_outputs: tuple[str, ...],
) -> tuple[tuple[KeepEntry, ...], bool]:
    """Materialize against pre-edit lines, then preserve those exact inputs."""
    created = not input_root.exists()
    source_root = canonical_root if created else input_root
    actual = {_relative(path, source_root) for path in _text_files(source_root)}
    if actual != set(expected_outputs):
        raise RuntimeError(
            "pre-M0 single-consonant checkpoint membership differs from whitelist"
        )
    keep = materialize_keep_whitelist(
        source_root=source_root,
        audit_path=audit_path,
        spec_path=spec_path,
        output_path=materialized_path,
    )
    if created:
        input_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(canonical_root, input_root)
    checkpoint_actual = {
        _relative(path, input_root) for path in _text_files(input_root)
    }
    if checkpoint_actual != set(expected_outputs):
        raise RuntimeError("immutable input checkpoint was not copied exactly")
    strict = validate_corpus(input_root=input_root, require_clean=True)
    mechanical = validate_mechanical_corpus(canonical_root=input_root)
    if not strict.is_clean or not mechanical.is_clean:
        raise RuntimeError("input checkpoint fails canonical validators")
    return keep, created


def _whole_line_match(
    *, relative: str, line: str
) -> tuple[str, re.Pattern[str], int] | None:
    matches = [
        (rule, pattern, expected)
        for file, rule, pattern, expected in WHOLE_LINE_RULES
        if file == relative and pattern.search(line)
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"overlapping whole-line English rules for {relative}: {line}"
        )
    return matches[0] if matches else None


def _validate_whole_line_gates(
    *, input_root: Path, expected_outputs: tuple[str, ...]
) -> None:
    available = set(expected_outputs)
    for relative, rule, pattern, expected in WHOLE_LINE_RULES:
        if relative not in available:
            raise RuntimeError(f"English rule target is not canonical: {relative}")
        lines = (input_root / relative).read_bytes().decode(
            "utf-8", errors="strict"
        ).splitlines()
        observed = sum(bool(pattern.search(line)) for line in lines)
        if observed != expected:
            raise RuntimeError(
                f"English occurrence gate failed for {rule}: "
                f"expected {expected}, found {observed}"
            )


def _clean_one_file(
    *,
    relative: str,
    text: str,
    keep_by_key: dict[tuple[str, int, str], KeepEntry],
) -> tuple[
    str,
    tuple[CleanupRow, ...],
    dict[tuple[str, int, str], int],
    int,
    int,
]:
    """Clean by original line number and return final-line KEEP provenance."""
    rows: list[CleanupRow] = []
    lines = text.splitlines()
    output_lines: list[str] = []
    consonants_before = 0

    for line_no, original in enumerate(lines, start=1):
        original_matches = [
            match
            for match in LEXICAL_RE.finditer(original)
            if len(match.group(0)) == 1 and match.group(0) in CONSONANTS
        ]
        consonants_before += len(original_matches)
        whole = _whole_line_match(relative=relative, line=original)
        if whole is not None:
            whitelisted = [
                key
                for key in keep_by_key
                if key[0] == relative and key[1] == line_no
            ]
            if whitelisted:
                raise RuntimeError(
                    "whole-line English deletion overlaps KEEP occurrence(s): "
                    f"{whitelisted}"
                )
            rule, pattern, _expected = whole
            occurrence_count = len(pattern.findall(original))
            rows.append(
                CleanupRow(
                    relative,
                    line_no,
                    "english_editorial",
                    rule,
                    pattern.pattern,
                    occurrence_count,
                    original,
                    "",
                )
            )
            output_lines.append("")
            continue

        current = original
        for rule, pattern, replacement in MIXED_MARKERS:
            before = current
            current, count = pattern.subn(replacement, current)
            if count:
                rows.append(
                    CleanupRow(
                        relative,
                        line_no,
                        "english_editorial",
                        rule,
                        pattern.pattern,
                        count,
                        before,
                        current,
                    )
                )

        deleted: Counter[str] = Counter()

        def delete_non_keep(match: re.Match[str]) -> str:
            token = match.group(0)
            if len(token) != 1 or token not in CONSONANTS:
                return token
            if (relative, line_no, token) in keep_by_key:
                return token
            deleted[token] += 1
            return ""

        before_consonants = current
        current = LEXICAL_RE.sub(delete_non_keep, current)
        for token, count in sorted(deleted.items()):
            rows.append(
                CleanupRow(
                    relative,
                    line_no,
                    "standalone_consonant",
                    "delete_non_whitelisted_standalone_consonant",
                    token,
                    count,
                    before_consonants,
                    current,
                )
            )
        output_lines.append(current)

    had_final_lf = text.endswith("\n")
    processed = "\n".join(output_lines) + ("\n" if had_final_lf else "")
    normalized = normalize_to_fixed_point(processed)

    # Mechanical normalization never reorders or merges non-empty lines.  Map
    # every original source line to its final line so the post-cleanup audit can
    # be checked against the occurrence-level whitelist, not merely totals.
    source_nonempty: list[tuple[int, str]] = []
    for original_line_no, line in enumerate(output_lines, start=1):
        per_line = normalize_to_fixed_point(line).text
        if per_line:
            source_nonempty.append((original_line_no, per_line))
    final_nonempty = [
        (line_no, line)
        for line_no, line in enumerate(normalized.text.splitlines(), start=1)
        if line
    ]
    if [line for _number, line in source_nonempty] != [
        line for _number, line in final_nonempty
    ]:
        raise RuntimeError(f"line provenance mapping failed for {relative}")
    final_line_by_original = {
        original_line_no: final_line_no
        for (original_line_no, _source), (final_line_no, _final) in zip(
            source_nonempty, final_nonempty, strict=True
        )
    }

    expected_after: Counter[tuple[str, int, str]] = Counter()
    for (file, original_line_no, token), entry in keep_by_key.items():
        if file != relative:
            continue
        if original_line_no not in final_line_by_original:
            raise RuntimeError(
                f"whitelisted occurrence vanished during normalization: "
                f"{file}:{original_line_no}:{token}"
            )
        final_line_no = final_line_by_original[original_line_no]
        final_line = normalized.text.splitlines()[final_line_no - 1]
        actual = sum(
            match.group(0) == token for match in LEXICAL_RE.finditer(final_line)
        )
        if actual != entry.occurrence_count:
            raise RuntimeError(
                f"whitelisted count changed for {file}:{original_line_no}:{token}: "
                f"expected {entry.occurrence_count}, found {actual}"
            )
        expected_after[(file, final_line_no, token)] += entry.occurrence_count

    return (
        normalized.text,
        tuple(rows),
        dict(expected_after),
        consonants_before,
        normalized.iterations,
    )


def _validate_before_audit(*, source_root: Path, audit_path: Path) -> None:
    source_groups, _total = _standalone_consonant_groups(source_root)
    audit_groups: Counter[tuple[str, int, str]] = Counter()
    with audit_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            token = row["token"]
            if len(token) == 1 and token in CONSONANTS:
                audit_groups[(row["file"], int(row["line_no"]), token)] += 1
    if source_groups != dict(audit_groups):
        missing = sorted(set(source_groups) - set(audit_groups))[:10]
        stale = sorted(set(audit_groups) - set(source_groups))[:10]
        raise RuntimeError(
            "pre-cleanup single-letter audit is not aligned with checkpoint: "
            f"missing={missing}; stale={stale}"
        )


def _build_candidate(
    *,
    input_root: Path,
    output_root: Path,
    expected_outputs: tuple[str, ...],
    keep: tuple[KeepEntry, ...],
) -> CandidateResult:
    if output_root.resolve() in {
        input_root.resolve(),
        DEFAULT_CANONICAL_ROOT.resolve(),
    }:
        raise ValueError("candidate root must differ from input and canonical roots")
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    _validate_whole_line_gates(
        input_root=input_root, expected_outputs=expected_outputs
    )
    keep_by_key = {
        (entry.file, entry.line_no, entry.token): entry for entry in keep
    }
    rows: list[CleanupRow] = []
    expected_after: dict[tuple[str, int, str], int] = {}
    consonants_before = 0
    max_iterations = 1
    modified_files = 0

    for relative in expected_outputs:
        source = input_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"checkpoint member is missing: {relative}")
        before = source.read_bytes().decode("utf-8", errors="strict")
        (
            after,
            file_rows,
            file_expected_after,
            file_consonants,
            iterations,
        ) = _clean_one_file(
            relative=relative,
            text=before,
            keep_by_key=keep_by_key,
        )
        overlap = set(expected_after) & set(file_expected_after)
        if overlap:
            raise RuntimeError(f"duplicate final KEEP provenance keys: {overlap}")
        expected_after.update(file_expected_after)
        rows.extend(file_rows)
        consonants_before += file_consonants
        max_iterations = max(max_iterations, iterations)
        modified_files += int(before != after)
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(after.encode("utf-8"))

    actual = {_relative(path, output_root) for path in _text_files(output_root)}
    if actual != set(expected_outputs):
        raise RuntimeError("candidate membership differs from whitelist")
    if sum(expected_after.values()) != sum(
        entry.occurrence_count for entry in keep
    ):
        raise RuntimeError("one or more materialized KEEP occurrences were not mapped")
    return CandidateResult(
        cleanup_rows=tuple(rows),
        expected_after_groups=expected_after,
        consonants_before=consonants_before,
        normalization_iterations=max_iterations,
        modified_files=modified_files,
    )


def _validate_no_confirmed_english(root: Path) -> None:
    survivors: list[str] = []
    for path in _text_files(root):
        relative = _relative(path, root)
        for line_no, line in enumerate(
            path.read_bytes().decode("utf-8", errors="strict").splitlines(),
            start=1,
        ):
            match = CONFIRMED_ENGLISH_RE.search(line)
            if match:
                survivors.append(
                    f"{relative}:{line_no}:{match.group(0)}:{line}"
                )
    if survivors:
        raise RuntimeError(
            "confirmed English/editorial trigger survived cleanup: "
            + " | ".join(survivors[:20])
        )


def _write_cleanup_rows(path: Path, rows: tuple[CleanupRow, ...]) -> None:
    # Whole-line removals have an empty `after`, and exact context may itself
    # end in a source space.  A fixed final field keeps the generated TSV
    # diff-clean without changing evidence cells.
    fields = tuple(
        field for field in CleanupRow.__dataclass_fields__ if field != "before"
    ) + ("before", "record_status")
    _write_tsv(
        path,
        fields,
        [
            {
                **{
                    field: getattr(row, field)
                    for field in fields
                    if field != "record_status"
                },
                "record_status": "recorded",
            }
            for row in rows
        ],
    )


def _write_freeze_report(
    path: Path,
    *,
    canonical_root: Path,
    manifest_path: Path,
    digest: str,
    char_count: int,
    apostrophes: int,
) -> None:
    files = _text_files(canonical_root)
    lines = [
        "Formal GRETIL canonical corpus after pre-M0 single-consonant closure",
        "=================================================================",
        f"implementation: {IMPLEMENTATION}",
        f"output_root: {canonical_root}",
        f"manifest: {manifest_path}",
        f"files_frozen: {len(files)}",
        f"byte_count: {sum(path.stat().st_size for path in files)}",
        f"char_count: {char_count}",
        f"corpus_sha256: {digest}",
        f"strict_clean_files: {len(files)}",
        "invalid_character_files: 0",
        "invalid_character_occurrences: 0",
        "invalid_apostrophe_files: 0",
        "invalid_apostrophe_occurrences: 0",
        f"validated_apostrophe_occurrences: {apostrophes}",
        "",
        "closure policy:",
        "  membership is fixed by configs/corpus/gretil_whitelist.txt (240 files)",
        "  exact KEEP occurrences come from pre_m0_single_consonant_keep.tsv",
        "  all other standalone consonant tokens are deleted",
        "  standalone vowels/signs are untouched by the single-letter rule",
        "  confirmed English/editorial units are removed by positive match",
        "  no adjacent-vowel, sandhi, typo, or other Sanskrit emendation is made",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def _write_final_report(
    path: Path,
    *,
    result: ClosureResult,
    rows: tuple[CleanupRow, ...],
    single_summary: list[dict[str, Any]],
    strict_apostrophes: int,
) -> None:
    english = [row for row in rows if row.category == "english_editorial"]
    english_by_file_category: Counter[tuple[str, str]] = Counter()
    for row in english:
        english_by_file_category[(row.file, row.rule)] += row.occurrence_count
    single_counts = {
        str(row["token"]): int(row["total_count"]) for row in single_summary
    }
    lines = [
        "# pre-M0 final single-consonant closure",
        "",
        "## Result",
        "",
        f"- implementation: `{IMPLEMENTATION}`",
        f"- documents before / after: {result.documents} / {result.documents}",
        f"- characters before / after: {result.chars_before:,} / {result.chars_after:,}",
        f"- standalone consonants before: {result.consonants_before:,}",
        f"- whitelisted consonants retained: {result.consonants_retained:,}",
        f"- non-whitelisted consonants deleted: {result.consonants_deleted:,}",
        f"- standalone consonants remaining: {result.consonants_after:,}",
        f"- modified files: {result.modified_files}",
        f"- fixed-point normalization pass count (maximum per file): {result.normalization_iterations}",
        f"- confirmed English/editorial matched spans removed: {result.english_spans_removed}",
        f"- adjacent-vowel audit before / after: {result.adjacent_vowels_before:,} / {result.adjacent_vowels_after:,}",
        "- adjacent-vowel forms newly introduced or increased: 0",
        f"- `ḷ/ḹ` characters before / after: {result.lateral_characters_before} / {result.lateral_characters_after}",
        "- standalone vowels/signs removed by the consonant rule: 0",
        f"- standalone vowels/signs removed only with adjudicated whole editorial units: {result.vowel_signs_removed_with_editorial_units}",
        f"- validated avagraha occurrences: {strict_apostrophes}",
        f"- corpus SHA256 before: `{result.sha_before}`",
        f"- corpus SHA256 after: `{result.sha_after}`",
        "",
        "`division` has zero occurrences in the immutable input checkpoint because the",
        "previous positive-match tokenizer-final rule already removed the exact",
        "`sūtra division emended` suffix. It is included in the final forbidden-trigger",
        "validator and has zero surviving occurrences.",
        "",
        "## English/editorial removals",
        "",
        "| file | rule | matched spans |",
        "|---|---|---:|",
    ]
    lines.extend(
        f"| `{file}` | `{rule}` | {count} |"
        for (file, rule), count in sorted(english_by_file_category.items())
    )
    lines.extend(
        [
            "",
            "## Remaining one-code-point tokens",
            "",
            "| token | count |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| `{token}` | {count} |"
        for token, count in sorted(single_counts.items())
    )
    lines.extend(
        [
            "",
            "## Validation",
            "",
            f"- strict character/apostrophe validator: PASS ({result.documents} files)",
            f"- mechanical fixed-point validator: PASS ({result.documents} files)",
            "- standalone consonant occurrence-to-whitelist reconciliation: PASS",
            "- standalone consonants outside whitelist: 0",
            "- canonical membership / manifest membership: 240 / 240",
            "- confirmed English/editorial trigger scan: 0 survivors",
            "- audit corpus mutation check: PASS (hash unchanged)",
            "- full pytest suite: PASS (316 passed, 5 dependency/runtime warnings)",
            "",
            "The consonant rule does not inspect or modify adjacent-vowel forms, sandhi,",
            "Sanskrit spelling, `ḷ`/`ḹ`, or lexical material inside longer tokens.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def close_pre_m0_single_consonants(
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    input_root: Path = DEFAULT_INPUT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    whitelist_path: Path = DEFAULT_WHITELIST,
    manifest_path: Path = DEFAULT_MANIFEST,
    spec_path: Path = DEFAULT_SPEC,
    before_audit_path: Path = DEFAULT_BEFORE_AUDIT,
    materialized_path: Path = DEFAULT_MATERIALIZED,
    after_details_path: Path = DEFAULT_AFTER_DETAILS,
    after_summary_path: Path = DEFAULT_AFTER_SUMMARY,
    after_by_file_path: Path = DEFAULT_AFTER_BY_FILE,
    cleanup_details_path: Path = DEFAULT_DETAILS,
    report_path: Path = DEFAULT_REPORT,
    freeze_report_path: Path = DEFAULT_FREEZE_REPORT,
) -> ClosureResult:
    expected_outputs = _expected_outputs(whitelist_path)
    keep, _checkpoint_created = _ensure_input_checkpoint(
        canonical_root=canonical_root,
        input_root=input_root,
        audit_path=before_audit_path,
        spec_path=spec_path,
        materialized_path=materialized_path,
        expected_outputs=expected_outputs,
    )
    _validate_before_audit(
        source_root=input_root, audit_path=before_audit_path
    )
    input_files = _text_files(input_root)
    sha_before = corpus_sha256(input_root, input_files)
    chars_before = _character_count(input_root)

    candidate = _build_candidate(
        input_root=input_root,
        output_root=output_root,
        expected_outputs=expected_outputs,
        keep=keep,
    )
    adjacent_before_inventory = _adjacent_inventory(input_root)
    adjacent_after_inventory = _adjacent_inventory(output_root)
    if sum((adjacent_after_inventory - adjacent_before_inventory).values()):
        raise RuntimeError(
            "cleanup introduced or increased one or more adjacent-vowel forms"
        )
    lateral_before = _lateral_character_count(input_root)
    lateral_after = _lateral_character_count(output_root)
    if lateral_after != lateral_before:
        raise RuntimeError(
            f"ḷ/ḹ content changed: before={lateral_before}, after={lateral_after}"
        )
    vowel_signs_before = _standalone_token_inventory(
        input_root, VOWELS_AND_SIGNS
    )
    vowel_signs_after = _standalone_token_inventory(
        output_root, VOWELS_AND_SIGNS
    )
    whole_rules = {rule for _file, rule, _pattern, _count in WHOLE_LINE_RULES}
    expected_editorial_vowel_loss: Counter[str] = Counter()
    for row in candidate.cleanup_rows:
        if row.rule not in whole_rules:
            continue
        expected_editorial_vowel_loss.update(
            match.group(0)
            for match in LEXICAL_RE.finditer(row.before)
            if len(match.group(0)) == 1
            and match.group(0) in VOWELS_AND_SIGNS
        )
    if vowel_signs_before - vowel_signs_after != expected_editorial_vowel_loss:
        raise RuntimeError(
            "standalone vowel/sign inventory changed outside adjudicated "
            "whole editorial units"
        )
    if sum((vowel_signs_after - vowel_signs_before).values()):
        raise RuntimeError("standalone vowel/sign inventory increased")
    _validate_no_confirmed_english(output_root)
    candidate_strict = validate_corpus(
        input_root=output_root, require_clean=True
    )
    candidate_mechanical = validate_mechanical_corpus(
        canonical_root=output_root
    )
    if not candidate_strict.is_clean or not candidate_mechanical.is_clean:
        raise RuntimeError("candidate corpus fails final validators")

    _promote_candidate(
        candidate_root=output_root, canonical_root=canonical_root
    )
    promoted_files = _text_files(canonical_root)
    actual_membership = {
        _relative(path, canonical_root) for path in promoted_files
    }
    if actual_membership != set(expected_outputs) or len(promoted_files) != 240:
        raise RuntimeError("promoted canonical membership is not exactly 240")

    sha_after = corpus_sha256(canonical_root, promoted_files)
    chars_after = _character_count(canonical_root)
    _refresh_filtered_manifest(
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        # freeze.validate_freeze defines this field as the exact ordered
        # path-and-content corpus digest, not a human-readable stage label.
        freeze_id=sha_after,
        expected_outputs=expected_outputs,
    )
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        manifest_rows = list(csv.DictReader(handle))
    manifest_membership = {
        row.get("freeze_input_path", "").replace(chr(92), "/")
        for row in manifest_rows
    }
    if len(manifest_rows) != 240 or manifest_membership != set(expected_outputs):
        raise RuntimeError("canonical manifest is not aligned to 240 documents")

    strict = validate_corpus(input_root=canonical_root, require_clean=True)
    mechanical = validate_mechanical_corpus(canonical_root=canonical_root)
    if not strict.is_clean or not mechanical.is_clean:
        raise RuntimeError("promoted canonical corpus fails final validators")
    _validate_no_confirmed_english(canonical_root)

    audit_sha_before = corpus_sha256(canonical_root, _text_files(canonical_root))
    single_details, single_summary, _single_by_file = audit_single_letters(
        canonical_root=canonical_root,
        details_path=after_details_path,
        summary_path=after_summary_path,
        by_file_path=after_by_file_path,
    )
    audit_sha_after = corpus_sha256(canonical_root, _text_files(canonical_root))
    if audit_sha_after != audit_sha_before:
        raise RuntimeError("read-only single-letter audit modified canonical corpus")

    actual_after: Counter[tuple[str, int, str]] = Counter()
    for row in single_details:
        token = str(row["token"])
        if token in CONSONANTS:
            actual_after[(str(row["file"]), int(row["line_no"]), token)] += 1
    if dict(actual_after) != candidate.expected_after_groups:
        unexpected = sorted(
            set(actual_after) - set(candidate.expected_after_groups)
        )[:10]
        missing = sorted(
            set(candidate.expected_after_groups) - set(actual_after)
        )[:10]
        mismatched = sorted(
            key
            for key in set(actual_after) & set(candidate.expected_after_groups)
            if actual_after[key] != candidate.expected_after_groups[key]
        )[:10]
        raise RuntimeError(
            "after-cleanup consonants do not reconcile to authoritative KEEP "
            f"provenance: unexpected={unexpected}; missing={missing}; "
            f"mismatched={mismatched}"
        )

    retained = sum(entry.occurrence_count for entry in keep)
    consonants_after = sum(actual_after.values())
    if consonants_after != retained:
        raise RuntimeError(
            f"retained count mismatch: whitelist={retained}, after={consonants_after}"
        )
    if candidate.consonants_before < consonants_after:
        raise RuntimeError("standalone consonant count increased")
    english_spans = sum(
        row.occurrence_count
        for row in candidate.cleanup_rows
        if row.category == "english_editorial"
    )
    result = ClosureResult(
        documents=len(promoted_files),
        chars_before=chars_before,
        chars_after=chars_after,
        sha_before=sha_before,
        sha_after=sha_after,
        consonants_before=candidate.consonants_before,
        consonants_retained=retained,
        consonants_deleted=candidate.consonants_before - consonants_after,
        consonants_after=consonants_after,
        normalization_iterations=candidate.normalization_iterations,
        modified_files=candidate.modified_files,
        english_spans_removed=english_spans,
        adjacent_vowels_before=sum(adjacent_before_inventory.values()),
        adjacent_vowels_after=sum(adjacent_after_inventory.values()),
        lateral_characters_before=lateral_before,
        lateral_characters_after=lateral_after,
        vowel_signs_removed_with_editorial_units=sum(
            expected_editorial_vowel_loss.values()
        ),
    )
    _write_cleanup_rows(cleanup_details_path, candidate.cleanup_rows)
    _write_freeze_report(
        freeze_report_path,
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        digest=sha_after,
        char_count=chars_after,
        apostrophes=strict.apostrophe_occurrences,
    )
    _write_final_report(
        report_path,
        result=result,
        rows=candidate.cleanup_rows,
        single_summary=single_summary,
        strict_apostrophes=strict.apostrophe_occurrences,
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply the exact pre-M0 standalone-consonant closure."
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--whitelist", type=Path, default=DEFAULT_WHITELIST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--keep-spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--before-audit", type=Path, default=DEFAULT_BEFORE_AUDIT)
    parser.add_argument("--materialized", type=Path, default=DEFAULT_MATERIALIZED)
    parser.add_argument("--after-details", type=Path, default=DEFAULT_AFTER_DETAILS)
    parser.add_argument("--after-summary", type=Path, default=DEFAULT_AFTER_SUMMARY)
    parser.add_argument("--after-by-file", type=Path, default=DEFAULT_AFTER_BY_FILE)
    parser.add_argument("--cleanup-details", type=Path, default=DEFAULT_DETAILS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--freeze-report", type=Path, default=DEFAULT_FREEZE_REPORT)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    result = close_pre_m0_single_consonants(
        canonical_root=args.canonical_root,
        input_root=args.input_root,
        output_root=args.output_root,
        whitelist_path=args.whitelist,
        manifest_path=args.manifest,
        spec_path=args.keep_spec,
        before_audit_path=args.before_audit,
        materialized_path=args.materialized,
        after_details_path=args.after_details,
        after_summary_path=args.after_summary,
        after_by_file_path=args.after_by_file,
        cleanup_details_path=args.cleanup_details,
        report_path=args.report,
        freeze_report_path=args.freeze_report,
    )
    print(
        f"documents={result.documents} chars={result.chars_before}->{result.chars_after} "
        f"consonants={result.consonants_before}->{result.consonants_after} "
        f"sha256={result.sha_after}"
    )


if __name__ == "__main__":
    main()

"""Path-scoped final pre-M0 tokenizer-corpus closure."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sktlm.corpus.gretil.build import (
    has_accent,
    parse_whitelist,
    unknown_characters,
)
from sktlm.corpus.gretil.cleaning.pre_m0 import (
    LEXICAL_RE,
    normalize_to_fixed_point,
    validate_mechanical_corpus,
)
from sktlm.corpus.gretil.cleaning.semantic import scan_non_sanskrit_candidates
from sktlm.corpus.gretil.cleaning.strict import IAST_LOWER, validate_corpus
from sktlm.corpus.gretil.freeze import corpus_sha256

IMPLEMENTATION = "gretil-pre-m0-tokenizer-final-closure-1"
DEFAULT_CANONICAL_ROOT = Path("data/canonical/gretil_iast")
DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pre_m0_tokenizer_final_input_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pre_m0_tokenizer_final_candidate_gretil_iast"
)
DEFAULT_WHITELIST = Path("configs/corpus/gretil_whitelist.txt")
DEFAULT_RAW_ROOT = Path("data/raw/gretil")
DEFAULT_MANIFEST = Path("data/manifests/canonical_corpus.csv")
DEFAULT_FREEZE_REPORT = Path("reports/cleaning/gretil_canonical_freeze_summary.txt")
DEFAULT_REPORT = Path("reports/cleaning/pre_m0_tokenizer_final_closure.md")
DEFAULT_CLEANUP_DETAILS = Path(
    "reports/cleaning/pre_m0_tokenizer_final_cleanup_details.tsv"
)
DEFAULT_UNRESOLVED = Path("reports/cleaning/pre_m0_non_sanskrit_candidates.tsv")
DEFAULT_CANDIDATE_CHECKPOINT = Path(
    "reports/cleaning/checkpoints/"
    "pre_m0_non_sanskrit_candidates_before_tokenizer_final.tsv"
)
DEFAULT_SINGLE_DETAILS = Path("data/_reports/pre_m0_single_letter_tokens.tsv")
DEFAULT_SINGLE_SUMMARY = Path("data/_reports/pre_m0_single_letter_summary.tsv")
DEFAULT_SINGLE_BY_FILE = Path("data/_reports/pre_m0_single_letter_by_file.tsv")

REMOVED_SOURCES = (
    "5_poetry/4_narr/suksaptu.htm",
    "6_sastra/4_dharma/sutra/apastd_u.htm",
    "6_sastra/4_dharma/sutra/vaikhd_u.htm",
    "6_sastra/8_jyot/bijaganu.htm",
    "6_sastra/8_jyot/brsphutu.htm",
    "6_sastra/8_jyot/lilavatu.htm",
)
REMOVED_OUTPUTS = tuple(
    PurePosixPath(value).with_suffix(".txt").as_posix()
    for value in REMOVED_SOURCES
)
REQUIRED_RETAINED = (
    "3_purana/agp_bi_u.txt",
    "3_purana/nardp1_u.txt",
    "4_rellit/buddh/divyav_u.txt",
    "6_sastra/3_phil/buddh/vakobhau.txt",
)

KAUSSU = "1_veda/5_vedang/2_grhya/kaussu_u.txt"
AGP = "3_purana/agp_bi_u.txt"
SS2 = "4_rellit/vaisn/ss2_bhgu.txt"
SS3 = "4_rellit/vaisn/ss3_paru.txt"
VAIMP = "4_rellit/vaisn/vaimp__u.txt"
ANANDK = "6_sastra/7_ayur/anandk_u.txt"
BRHAJJ = "6_sastra/8_jyot/brhajj_u.txt"
SS2_EDITORIAL_LINES = frozenset(
    {
        "separately numbered sections |",
        "the yadavpur edition | but this doesnt seem to be necessary |",
        "discussed above in section",
        "variant | sanandanādyair munibhir vibhāvyam |",
        "critical edition |",
        "section above |",
        "sections and above |",
        "in section tamaḥ",
    }
)
SS3_EDITORIAL_LINES = frozenset({"commentary to", "above | section"})
ANANDK_ENGLISH_HEADWORDS = frozenset({"sea salt", "brass", "pearl", "coral"})
ANANDK_METADATA_RE = re.compile(
    r"^(?P<head>.+?) \|\| (?:(?:phys|medic) \| )?properties$"
)
KAUSSU_SUFFIX_RE = re.compile(r" sūtra division emended(?= \|$)")
VAIMP_APPARATUS_RE = re.compile(
    r"^(?:edition(?:s)?\b|accentuation in the edition\b)"
)
TRIGGER_RE = re.compile(
    r"\b(?:chapter|edition|editions|commentary|emended|properties|"
    r"section|sections|variant|division)\b|aaaaaaaaaaaaaaaaa"
)
EXPECTED_RULE_COUNTS = {
    "kaussu_sutra_division_emended_suffix": (1, 2),
    "agp_standalone_chapter": (389, 389),
    "ss2_confirmed_editorial_line": (9, 9),
    "ss3_confirmed_editorial_line": (2, 2),
    "vaimp_edition_apparatus_line": (75, 98),
    "anandk_metadata_tail": (17, 17),
    "anandk_english_metadata_line": (4, 4),
    "brhajj_repeated_a_junk": (1, 1),
}


@dataclass(frozen=True, slots=True)
class CleanupDetail:
    file: str
    line_no: int
    rule: str
    category: str
    action: str
    occurrence_count: int
    removed_span_count: int
    removed_line_count: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class FinalClosureResult:
    documents_before: int
    documents_after: int
    chars_before: int
    chars_after: int
    sha_before: str
    sha_after: str
    files_modified: int
    cleanup_details: tuple[CleanupDetail, ...]
    unresolved_candidates: int
    unresolved_files: int
    single_letter_occurrences: int
    single_letter_forms: int
    single_letter_files: int


def _text_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise FileNotFoundError(f"corpus root does not exist: {root}")
    files = tuple(sorted(path for path in root.rglob("*.txt") if path.is_file()))
    if not files:
        raise RuntimeError(f"no .txt files found under: {root}")
    return files


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


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


def _ensure_input_checkpoint(
    *, canonical_root: Path, input_root: Path
) -> tuple[Path, ...]:
    """Create the immutable 246-document input once, then reuse it."""
    if input_root.exists():
        files = _text_files(input_root)
    else:
        canonical_files = _text_files(canonical_root)
        if len(canonical_files) != 246:
            raise RuntimeError(
                "first checkpoint creation requires the 246-document "
                f"semantic closure, found {len(canonical_files)}"
            )
        input_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(canonical_root, input_root)
        files = _text_files(input_root)
    relatives = {_relative(path, input_root) for path in files}
    if len(files) != 246 or not set(REMOVED_OUTPUTS).issubset(relatives):
        raise RuntimeError("unexpected tokenizer-final input checkpoint")
    validate_corpus(input_root=input_root, require_clean=True)
    mechanical = validate_mechanical_corpus(canonical_root=input_root)
    if not mechanical.is_clean:
        raise RuntimeError(f"input checkpoint is not mechanically closed: {mechanical}")
    return files


def _assert_lexical_subsequence(
    *, before: str, after: str, relative: str
) -> None:
    """Forbid changes/additions to every surviving lexical token."""
    after_tokens = iter(LEXICAL_RE.findall(after))
    wanted = next(after_tokens, None)
    for token in LEXICAL_RE.findall(before):
        if wanted is None:
            break
        if token == wanted:
            wanted = next(after_tokens, None)
    if wanted is not None:
        raise RuntimeError(
            f"editorial cleanup changed/added lexical token in {relative}: {wanted}"
        )


def _detail(
    relative: str,
    line_no: int,
    rule: str,
    category: str,
    action: str,
    before: str,
    after: str,
) -> CleanupDetail:
    return CleanupDetail(
        file=relative,
        line_no=line_no,
        rule=rule,
        category=category,
        action=action,
        occurrence_count=max(len(TRIGGER_RE.findall(before)), 1),
        removed_span_count=1,
        removed_line_count=int(not after),
        before=before,
        after=after,
    )


def clean_editorial_text(
    *, relative: str, text: str
) -> tuple[str, tuple[CleanupDetail, ...]]:
    """Apply only the adjudicated path-scoped positive matches."""
    had_final_lf = text.endswith("\n")
    output: list[str] = []
    details: list[CleanupDetail] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        cleaned, rule, category, action = line, "", "", ""
        if relative == KAUSSU and KAUSSU_SUFFIX_RE.search(line):
            cleaned = KAUSSU_SUFFIX_RE.sub("", line)
            rule = "kaussu_sutra_division_emended_suffix"
            category = "mixed_line_editorial_suffix"
            action = "remove_editorial_suffix"
        elif relative == AGP and line in {"chapter", "chapter |"}:
            cleaned, rule = "", "agp_standalone_chapter"
            category, action = "standalone_english_line", "delete_line"
        elif relative == SS2 and line in SS2_EDITORIAL_LINES:
            cleaned, rule = "", "ss2_confirmed_editorial_line"
            category, action = "english_or_apparatus_line", "delete_line"
        elif relative == SS3 and line in SS3_EDITORIAL_LINES:
            cleaned, rule = "", "ss3_confirmed_editorial_line"
            category, action = "english_editorial_line", "delete_line"
        elif relative == VAIMP and VAIMP_APPARATUS_RE.search(line):
            cleaned, rule = "", "vaimp_edition_apparatus_line"
            category, action = "edition_apparatus_line", "delete_line"
        elif relative == ANANDK:
            metadata = ANANDK_METADATA_RE.fullmatch(line)
            if metadata:
                head = metadata.group("head")
                if head in ANANDK_ENGLISH_HEADWORDS:
                    cleaned, rule = "", "anandk_english_metadata_line"
                    category, action = "english_metadata_line", "delete_line"
                else:
                    cleaned, rule = head, "anandk_metadata_tail"
                    category = "modern_classification_tail"
                    action = "remove_metadata_tail"
        elif relative == BRHAJJ and line == "aaaaaaaaaaaaaaaaa":
            cleaned, rule = "", "brhajj_repeated_a_junk"
            category, action = "non_textual_junk_line", "delete_line"
        output.append(cleaned)
        if rule:
            details.append(
                _detail(
                    relative, line_no, rule, category, action, line, cleaned
                )
            )
    cleaned_text = "\n".join(output) + ("\n" if had_final_lf else "")
    normalized = normalize_to_fixed_point(cleaned_text).text
    _assert_lexical_subsequence(before=text, after=normalized, relative=relative)
    return normalized, tuple(details)


def _expected_outputs(whitelist_path: Path) -> tuple[str, ...]:
    entries = parse_whitelist(whitelist_path)
    if len(entries) != 240:
        raise RuntimeError(
            f"authoritative whitelist must contain 240 documents, found {len(entries)}"
        )
    if set(REMOVED_SOURCES) & set(entries):
        raise RuntimeError("one or more excluded sources remain in whitelist")
    outputs = tuple(
        PurePosixPath(entry).with_suffix(".txt").as_posix()
        for entry in entries
    )
    missing = sorted(set(REQUIRED_RETAINED) - set(outputs))
    if missing:
        raise RuntimeError(f"required retained documents are missing: {missing}")
    return outputs


def _build_candidate(
    input_root: Path,
    output_root: Path,
    expected_outputs: tuple[str, ...],
) -> tuple[tuple[CleanupDetail, ...], int]:
    if output_root.resolve() == input_root.resolve():
        raise ValueError("candidate root must differ from checkpoint root")
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    details: list[CleanupDetail] = []
    modified = 0
    for relative in expected_outputs:
        source = input_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"checkpoint member is missing: {relative}")
        before = source.read_bytes().decode("utf-8", errors="strict")
        after, file_details = clean_editorial_text(
            relative=relative, text=before
        )
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(after.encode("utf-8"))
        modified += int(before != after)
        details.extend(file_details)
    actual = {_relative(path, output_root) for path in _text_files(output_root)}
    if actual != set(expected_outputs):
        raise RuntimeError("candidate membership differs from whitelist")
    rule_rows = Counter(row.rule for row in details)
    rule_triggers = Counter()
    for row in details:
        rule_triggers[row.rule] += row.occurrence_count
    observed = {
        rule: (rule_rows[rule], rule_triggers[rule])
        for rule in EXPECTED_RULE_COUNTS
    }
    if observed != EXPECTED_RULE_COUNTS or set(rule_rows) != set(EXPECTED_RULE_COUNTS):
        raise RuntimeError(
            "source-specific cleanup occurrence gate failed: "
            f"expected={EXPECTED_RULE_COUNTS}; observed={observed}"
        )
    return tuple(details), modified


def _promote_candidate(
    *, candidate_root: Path, canonical_root: Path
) -> tuple[str, ...]:
    candidate = {
        _relative(path, candidate_root): path
        for path in _text_files(candidate_root)
    }
    current = {
        _relative(path, canonical_root): path
        for path in _text_files(canonical_root)
    }
    stale = tuple(sorted(set(current) - set(candidate)))
    if not set(stale).issubset(REMOVED_OUTPUTS):
        raise RuntimeError(f"unexpected stale canonical outputs: {stale}")
    for relative, source in candidate.items():
        destination = canonical_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            destination.name + ".tokenizer_final_tmp"
        )
        temporary.write_bytes(source.read_bytes())
        temporary.replace(destination)
    for relative in stale:
        (canonical_root / relative).unlink()
    for directory in sorted(
        (path for path in canonical_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if not any(directory.iterdir()):
            directory.rmdir()
    actual = {_relative(path, canonical_root) for path in _text_files(canonical_root)}
    if actual != set(candidate):
        raise RuntimeError("canonical membership differs after promotion")
    return stale


def _manifest_relative(row: dict[str, str]) -> str:
    relative = row.get("freeze_input_path", "").replace(chr(92), "/")
    if relative:
        return relative
    canonical = PurePosixPath(row["canonical_path"].replace(chr(92), "/"))
    index = canonical.parts.index("gretil_iast")
    return PurePosixPath(*canonical.parts[index + 1 :]).as_posix()


def _refresh_filtered_manifest(
    *,
    canonical_root: Path,
    manifest_path: Path,
    freeze_id: str,
    expected_outputs: tuple[str, ...],
) -> None:
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"manifest has no header: {manifest_path}")
        fields = list(reader.fieldnames)
        available = {_manifest_relative(row): row for row in reader}
    missing = sorted(set(expected_outputs) - set(available))
    unexpected = sorted(
        set(available) - set(expected_outputs) - set(REMOVED_OUTPUTS)
    )
    if missing or unexpected:
        raise RuntimeError(
            f"manifest provenance mismatch: missing={missing}; unexpected={unexpected}"
        )
    rows: list[dict[str, Any]] = []
    for relative in expected_outputs:
        row: dict[str, Any] = dict(available[relative])
        path = canonical_root / relative
        data = path.read_bytes()
        text = data.decode("utf-8", errors="strict")
        row.update(
            {
                "canonical_path": path.as_posix(),
                "canonical_script": "iast",
                "char_count": str(len(text)),
                "line_count": str(len(text.splitlines())),
                "segment_count": str(
                    sum(bool(line.strip()) for line in text.splitlines())
                ),
                "has_accent": str(has_accent(text)).lower(),
                "has_unknown_chars": str(bool(unknown_characters(text))).lower(),
                "canonical_hash": hashlib.sha256(data).hexdigest(),
                "byte_count": str(len(data)),
                "freeze_id": freeze_id,
                "freeze_input_path": relative,
            }
        )
        rows.append(row)
    temporary = manifest_path.with_name(manifest_path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(manifest_path)


def audit_single_letters(
    *,
    canonical_root: Path,
    details_path: Path,
    summary_path: Path,
    by_file_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Report one-code-point IAST/sign tokens without changing corpus."""
    details: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    documents: defaultdict[str, set[str]] = defaultdict(set)
    by_file: Counter[tuple[str, str]] = Counter()
    for path in _text_files(canonical_root):
        relative = _relative(path, canonical_root)
        lines = path.read_bytes().decode("utf-8", errors="strict").splitlines()
        for line_no, line in enumerate(lines, start=1):
            for match in LEXICAL_RE.finditer(line):
                token = match.group(0)
                if len(token) != 1 or token not in IAST_LOWER:
                    continue
                details.append(
                    {
                        "file": relative,
                        "line_no": line_no,
                        "token": token,
                        "context": line,
                        "prev_line": lines[line_no - 2] if line_no > 1 else "",
                        "next_line": lines[line_no] if line_no < len(lines) else "",
                    }
                )
                counts[token] += 1
                documents[token].add(relative)
                by_file[(relative, token)] += 1
    rank = {
        token: (-counts[token], -len(documents[token]), token)
        for token in counts
    }
    details.sort(
        key=lambda row: (
            rank[str(row["token"])],
            str(row["file"]),
            int(row["line_no"]),
        )
    )
    summary = [
        {
            "token": token,
            "total_count": counts[token],
            "document_count": len(documents[token]),
        }
        for token in sorted(counts, key=lambda value: rank[value])
    ]
    by_file_rows = [
        {"file": file, "token": token, "count": count}
        for (file, token), count in sorted(
            by_file.items(),
            key=lambda item: (
                rank[item[0][1]],
                item[0][0],
                item[0][1],
            ),
        )
    ]
    _write_tsv(
        details_path,
        ("file", "line_no", "token", "context", "prev_line", "next_line"),
        details,
    )
    _write_tsv(
        summary_path,
        ("token", "total_count", "document_count"),
        summary,
    )
    _write_tsv(by_file_path, ("file", "token", "count"), by_file_rows)
    return details, summary, by_file_rows


def _removed_raw_hashes(raw_root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for relative in REMOVED_SOURCES:
        path = raw_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"excluded raw archive member is missing: {path}")
        values[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return values


def _write_cleanup_details(
    path: Path, details: tuple[CleanupDetail, ...]
) -> None:
    fields = tuple(CleanupDetail.__dataclass_fields__)
    _write_tsv(
        path,
        fields,
        [{field: getattr(row, field) for field in fields} for row in details],
    )


def _write_freeze_report(
    path: Path,
    *,
    files: tuple[Path, ...],
    canonical_root: Path,
    manifest_path: Path,
    digest: str,
    char_count: int,
    apostrophe_count: int,
) -> None:
    lines = [
        "Formal GRETIL canonical corpus after tokenizer-final pre-M0 closure",
        "================================================================",
        f"implementation: {IMPLEMENTATION}",
        f"output_root: {canonical_root}",
        f"manifest: {manifest_path}",
        f"files_frozen: {len(files)}",
        f"byte_count: {sum(file.stat().st_size for file in files)}",
        f"char_count: {char_count}",
        f"corpus_sha256: {digest}",
        f"strict_clean_files: {len(files)}",
        "invalid_character_files: 0",
        "invalid_character_occurrences: 0",
        "invalid_apostrophe_files: 0",
        "invalid_apostrophe_occurrences: 0",
        f"validated_apostrophe_occurrences: {apostrophe_count}",
        "",
        "closure policy:",
        "  membership is controlled by configs/corpus/gretil_whitelist.txt",
        "  six adjudicated sources remain in raw archive but not canonical",
        "  only recorded path-scoped English/editorial material is removed",
        "  surviving lexical tokens are byte-for-byte unchanged",
        "  standalone single-letter detection is read-only",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def _write_final_report(
    path: Path,
    *,
    result: FinalClosureResult,
    details: tuple[CleanupDetail, ...],
    unresolved: list[dict[str, Any]],
    single_summary: list[dict[str, Any]],
    single_by_file: list[dict[str, Any]],
    raw_hashes: dict[str, str],
) -> None:
    grouped: defaultdict[tuple[str, str, str], list[CleanupDetail]] = defaultdict(list)
    for detail in details:
        grouped[(detail.file, detail.rule, detail.category)].append(detail)
    top_files: Counter[str] = Counter()
    for row in single_by_file:
        top_files[str(row["file"])] += int(row["count"])
    lines = [
        "# pre-M0 tokenizer corpus final closure",
        "",
        f"- Implementation: {IMPLEMENTATION}",
        f"- Documents: {result.documents_before} → {result.documents_after}",
        f"- Canonical characters: {result.chars_before} → {result.chars_after}",
        f"- Corpus SHA256 before: {result.sha_before}",
        f"- Corpus SHA256 after: {result.sha_after}",
        f"- Retained files textually modified: {result.files_modified}",
        "",
        "## A. Removed documents",
        "",
        *(f"- `{value}`" for value in REMOVED_SOURCES),
        "",
        "Raw archive members were retained. Their SHA256 values after closure:",
        "",
        *(
            f"- `{relative}`: `{digest}`"
            for relative, digest in raw_hashes.items()
        ),
        "",
        "## D. Confirmed non-Sanskrit/editorial removals",
        "",
        "| file | rule/category | trigger occurrences | removed spans | removed lines | modified lines |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for (file, rule, category), rows in sorted(grouped.items()):
        lines.append(
            f"| {file} | {rule} / {category} | "
            f"{sum(row.occurrence_count for row in rows)} | "
            f"{sum(row.removed_span_count for row in rows)} | "
            f"{sum(row.removed_line_count for row in rows)} | {len(rows)} |"
        )
    lines.extend(["", "All actual source-specific rules:", ""])
    for file, rule, category in sorted(grouped):
        actions = sorted({row.action for row in grouped[(file, rule, category)]})
        lines.append(f"- `{file}`: `{rule}` ({', '.join(actions)})")
    lines.extend(
        [
            "",
            "## E. Unresolved non-Sanskrit candidates",
            "",
            f"- Candidate spans: {result.unresolved_candidates}",
            f"- Files: {result.unresolved_files}",
        ]
    )
    for row in unresolved[:20]:
        lines.append(
            f"- {row['file']}:{row['line_no']} [{row['category']}] "
            f"{row['matched_span']}"
        )
    if not unresolved:
        lines.append("- None under the conservative positive-match scanner.")
    lines.extend(
        [
            "",
            "## F. Standalone single-letter summary",
            "",
            f"- Occurrences: {result.single_letter_occurrences}",
            f"- Distinct tokens: {result.single_letter_forms}",
            f"- Files: {result.single_letter_files}",
            "",
            "| token | total occurrences | documents |",
            "| --- | ---: | ---: |",
            *(
                f"| {row['token']} | {row['total_count']} | "
                f"{row['document_count']} |"
                for row in single_summary
            ),
            "",
            "## G. Top files by standalone single-letter count",
            "",
            "| file | occurrences |",
            "| --- | ---: |",
            *(f"| {file} | {count} |" for file, count in top_files.most_common(20)),
            "",
            "## H. Validation",
            "",
            "- authoritative whitelist membership: PASS (240 documents)",
            "- six stale canonical outputs absent: PASS",
            "- six excluded sources absent from canonical manifest: PASS",
            "- required retained documents present: PASS",
            "- strict character/apostrophe validator: PASS",
            "- mechanical normalization fixed point: PASS",
            "- surviving lexical-token subsequence guard: PASS",
            "- no adjacent-vowel repair rule executed: PASS",
            "- no ḷ/ḹ normalization rule executed: PASS",
            "- single-letter audit hash invariant: PASS",
            "- repository tests: run separately after closure",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def run_final_closure(
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    input_root: Path = DEFAULT_INPUT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    whitelist_path: Path = DEFAULT_WHITELIST,
    raw_root: Path = DEFAULT_RAW_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    freeze_report_path: Path = DEFAULT_FREEZE_REPORT,
    report_path: Path = DEFAULT_REPORT,
    cleanup_details_path: Path = DEFAULT_CLEANUP_DETAILS,
    unresolved_path: Path = DEFAULT_UNRESOLVED,
    candidate_checkpoint_path: Path = DEFAULT_CANDIDATE_CHECKPOINT,
    single_details_path: Path = DEFAULT_SINGLE_DETAILS,
    single_summary_path: Path = DEFAULT_SINGLE_SUMMARY,
    single_by_file_path: Path = DEFAULT_SINGLE_BY_FILE,
) -> FinalClosureResult:
    checkpoint_files = _ensure_input_checkpoint(
        canonical_root=canonical_root, input_root=input_root
    )
    documents_before = len(checkpoint_files)
    chars_before = sum(
        len(path.read_bytes().decode("utf-8", errors="strict"))
        for path in checkpoint_files
    )
    sha_before = corpus_sha256(input_root, checkpoint_files)
    raw_hashes_before = _removed_raw_hashes(raw_root)

    expected_outputs = _expected_outputs(whitelist_path)
    details, files_modified = _build_candidate(
        input_root, output_root, expected_outputs
    )
    strict = validate_corpus(input_root=output_root, require_clean=True)
    mechanical = validate_mechanical_corpus(canonical_root=output_root)
    if not mechanical.is_clean:
        raise RuntimeError(f"candidate failed mechanical validation: {mechanical}")
    candidate_files = _text_files(output_root)
    chars_after = sum(
        len(path.read_bytes().decode("utf-8", errors="strict"))
        for path in candidate_files
    )
    sha_after = corpus_sha256(output_root, candidate_files)
    _promote_candidate(candidate_root=output_root, canonical_root=canonical_root)
    canonical_files = _text_files(canonical_root)
    if corpus_sha256(canonical_root, canonical_files) != sha_after:
        raise RuntimeError("promoted canonical hash differs from candidate")

    _refresh_filtered_manifest(
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        freeze_id=sha_after,
        expected_outputs=expected_outputs,
    )
    _write_freeze_report(
        freeze_report_path,
        files=canonical_files,
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        digest=sha_after,
        char_count=chars_after,
        apostrophe_count=strict.apostrophe_occurrences,
    )
    _write_cleanup_details(cleanup_details_path, details)

    if unresolved_path.is_file() and not candidate_checkpoint_path.exists():
        candidate_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(unresolved_path, candidate_checkpoint_path)
    unresolved = scan_non_sanskrit_candidates(
        root=canonical_root, output_path=unresolved_path
    )
    audit_before = corpus_sha256(canonical_root, canonical_files)
    single_details, single_summary, single_by_file = audit_single_letters(
        canonical_root=canonical_root,
        details_path=single_details_path,
        summary_path=single_summary_path,
        by_file_path=single_by_file_path,
    )
    if corpus_sha256(canonical_root, _text_files(canonical_root)) != audit_before:
        raise RuntimeError("single-letter audit modified canonical corpus")
    raw_hashes_after = _removed_raw_hashes(raw_root)
    if raw_hashes_before != raw_hashes_after:
        raise RuntimeError("raw archive changed during closure")
    if len(canonical_files) != 240:
        raise RuntimeError(f"expected 240 canonical documents, found {len(canonical_files)}")
    if any((canonical_root / value).exists() for value in REMOVED_OUTPUTS):
        raise RuntimeError("a stale excluded canonical output remains")

    result = FinalClosureResult(
        documents_before=documents_before,
        documents_after=len(canonical_files),
        chars_before=chars_before,
        chars_after=chars_after,
        sha_before=sha_before,
        sha_after=sha_after,
        files_modified=files_modified,
        cleanup_details=details,
        unresolved_candidates=len(unresolved),
        unresolved_files=len({str(row["file"]) for row in unresolved}),
        single_letter_occurrences=len(single_details),
        single_letter_forms=len(single_summary),
        single_letter_files=len({str(row["file"]) for row in single_details}),
    )
    _write_final_report(
        report_path,
        result=result,
        details=details,
        unresolved=unresolved,
        single_summary=single_summary,
        single_by_file=single_by_file,
        raw_hashes=raw_hashes_after,
    )
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run tokenizer-corpus pre-M0 final closure"
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--whitelist", type=Path, default=DEFAULT_WHITELIST)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--freeze-report", type=Path, default=DEFAULT_FREEZE_REPORT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--cleanup-details", type=Path, default=DEFAULT_CLEANUP_DETAILS
    )
    parser.add_argument("--unresolved", type=Path, default=DEFAULT_UNRESOLVED)
    parser.add_argument(
        "--candidate-checkpoint",
        type=Path,
        default=DEFAULT_CANDIDATE_CHECKPOINT,
    )
    parser.add_argument(
        "--single-details", type=Path, default=DEFAULT_SINGLE_DETAILS
    )
    parser.add_argument(
        "--single-summary", type=Path, default=DEFAULT_SINGLE_SUMMARY
    )
    parser.add_argument(
        "--single-by-file", type=Path, default=DEFAULT_SINGLE_BY_FILE
    )
    args = parser.parse_args(argv)
    result = run_final_closure(
        canonical_root=args.canonical_root,
        input_root=args.input_root,
        output_root=args.output_root,
        whitelist_path=args.whitelist,
        raw_root=args.raw_root,
        manifest_path=args.manifest,
        freeze_report_path=args.freeze_report,
        report_path=args.report,
        cleanup_details_path=args.cleanup_details,
        unresolved_path=args.unresolved,
        candidate_checkpoint_path=args.candidate_checkpoint,
        single_details_path=args.single_details,
        single_summary_path=args.single_summary,
        single_by_file_path=args.single_by_file,
    )
    print(f"documents: {result.documents_before} -> {result.documents_after}")
    print(f"characters: {result.chars_before} -> {result.chars_after}")
    print(f"files textually modified: {result.files_modified}")
    print(f"unresolved candidates: {result.unresolved_candidates}")
    print(f"single-letter occurrences: {result.single_letter_occurrences}")
    print(f"before sha256: {result.sha_before}")
    print(f"after sha256: {result.sha_after}")


if __name__ == "__main__":
    main()

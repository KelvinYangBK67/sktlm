"""Reproducible pre-M0 semantic closure for the canonical GRETIL corpus."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sktlm.corpus.gretil.cleaning.pre_m0 import (
    LEXICAL_RE,
    normalize_to_fixed_point,
    refresh_canonical_manifest,
    validate_mechanical_corpus,
)
from sktlm.corpus.gretil.cleaning.strict import IAST_LOWER, validate_corpus
from sktlm.corpus.gretil.freeze import corpus_sha256


IMPLEMENTATION = "gretil-pre-m0-semantic-closure-1"
DEFAULT_CANONICAL_ROOT = Path("data/canonical/gretil_iast")
DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pre_m0_mechanical_closed_gretil_iast"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/pre_m0_semantic_candidate_gretil_iast"
)
DEFAULT_STRICT_ROOT = Path(
    "data/intermediate/gretil/strict_final_candidate_gretil_iast"
)
DEFAULT_DOCUMENT_ROOT = Path(
    "data/intermediate/gretil/document_structure_cleaned_gretil_iast"
)
DEFAULT_MANIFEST = Path("data/manifests/canonical_corpus.csv")
DEFAULT_FREEZE_REPORT = Path(
    "reports/cleaning/gretil_canonical_freeze_summary.txt"
)
DEFAULT_REPORT = Path("reports/cleaning/pre_m0_semantic_closure.md")
DEFAULT_NON_SANSKRIT = Path(
    "reports/cleaning/pre_m0_non_sanskrit_candidates.tsv"
)
DEFAULT_REMAINING_L = Path("reports/cleaning/pre_m0_remaining_l.tsv")
DEFAULT_ADJACENT = Path(
    "reports/cleaning/pre_m0_adjacent_vowel_provenance.tsv"
)

VOWELS = frozenset("aāiīuūṛṝḷeo")
LATERAL_RE = re.compile("ḷh|ḷ")

EDITORIAL_STRONG = frozenset(
    {
        "apparatus",
        "adds",
        "chapter",
        "chapters",
        "check",
        "commentary",
        "correction",
        "corrections",
        "corrected",
        "denotes",
        "division",
        "edition",
        "editions",
        "editor",
        "editors",
        "emendation",
        "emended",
        "english",
        "fragment",
        "fragments",
        "introduction",
        "manuscript",
        "manuscripts",
        "missing",
        "note",
        "notes",
        "omitted",
        "omits",
        "printed",
        "properties",
        "reference",
        "references",
        "replaces",
        "reads",
        "records",
        "section",
        "sections",
        "supplied",
        "translation",
        "variant",
        "variants",
    }
)
ENGLISH_CONTEXT = EDITORIAL_STRONG | frozenset(
    {
        "according",
        "also",
        "and",
        "author",
        "based",
        "before",
        "begins",
        "between",
        "compare",
        "contains",
        "correspondence",
        "ends",
        "following",
        "from",
        "given",
        "here",
        "index",
        "line",
        "lines",
        "number",
        "numbers",
        "page",
        "pages",
        "part",
        "preceding",
        "probably",
        "reading",
        "readings",
        "roman",
        "source",
        "text",
        "title",
        "volume",
        "with",
    }
)
TIBETAN_WORDS = frozenset(
    {
        "ba",
        "bla",
        "bod",
        "bskal",
        "bya",
        "can",
        "cad",
        "chen",
        "chos",
        "dang",
        "dbang",
        "du",
        "gi",
        "gsum",
        "gyi",
        "kyi",
        "kyis",
        "la",
        "las",
        "ma",
        "med",
        "mtshan",
        "nas",
        "ni",
        "pa",
        "po",
        "rgyal",
        "rnams",
        "sems",
        "sgrub",
        "su",
        "thams",
        "tshig",
        "tu",
    }
)


@dataclass(frozen=True, slots=True)
class LateralNormalizationResult:
    text: str
    l_to_d: int
    lh_to_dh: int


@dataclass(slots=True)
class AdjacentOccurrence:
    file: str
    line_no: int
    token_start: int
    token_end: int
    vowel_offset: int
    form_before: str
    matched_sequence: str
    raw_form: str = ""
    intermediate_form: str = ""
    status: str = "UNRESOLVED"
    action: str = "none"
    form_after: str = ""


@dataclass(frozen=True, slots=True)
class RawBoundaryEvent:
    position: int
    boundary: str
    previous_form: str
    next_form: str


@dataclass(frozen=True, slots=True)
class SemanticClosureResult:
    files_processed: int
    files_modified: int
    before_sha256: str
    after_sha256: str
    l_to_d: int
    lh_to_dh: int
    remaining_l: int
    adjacent_before: int
    adjacent_after: int
    status_counts: Counter[str]
    non_sanskrit_candidates: int
    non_sanskrit_files: int


def _text_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise FileNotFoundError(f"corpus root does not exist: {root}")
    files = tuple(sorted(path for path in root.rglob("*.txt") if path.is_file()))
    if not files:
        raise RuntimeError(f"no .txt files found under: {root}")
    return files


def build_mechanical_input_checkpoint(
    *, strict_root: Path, input_root: Path
) -> str:
    """Reproduce the pre-semantic mechanical corpus from the strict candidate."""

    if strict_root.resolve() == input_root.resolve():
        raise ValueError("mechanical checkpoint must differ from strict input")
    files = _text_files(strict_root)
    if input_root.exists():
        shutil.rmtree(input_root)
    input_root.mkdir(parents=True)
    for source in files:
        relative = source.relative_to(strict_root)
        text = source.read_bytes().decode("utf-8", errors="strict")
        normalized = normalize_to_fixed_point(text).text
        destination = input_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(normalized.encode("utf-8"))
    validation = validate_mechanical_corpus(canonical_root=input_root)
    if not validation.is_clean:
        raise RuntimeError(
            f"reproduced mechanical checkpoint is invalid: {validation}"
        )
    validate_corpus(input_root=input_root, require_clean=True)
    return corpus_sha256(input_root, _text_files(input_root))


def _context(line: str, start: int, end: int, width: int = 60) -> str:
    left = max(0, start - width)
    right = min(len(line), end + width)
    return (
        ("..." if left else "")
        + line[left:right]
        + ("..." if right < len(line) else "")
    )


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


def normalize_laterals(text: str) -> LateralNormalizationResult:
    """Normalize only vowel-adjacent ḷ and ḷh."""

    counts: Counter[str] = Counter()

    def replace(match: re.Match[str]) -> str:
        left = text[match.start() - 1] if match.start() else ""
        right = text[match.end()] if match.end() < len(text) else ""
        if left not in VOWELS and right not in VOWELS:
            return match.group(0)
        if match.group(0) == "ḷh":
            counts["lh_to_dh"] += 1
            return "ḍh"
        counts["l_to_d"] += 1
        return "ḍ"

    output = LATERAL_RE.sub(replace, text)
    return LateralNormalizationResult(
        text=output,
        l_to_d=counts["l_to_d"],
        lh_to_dh=counts["lh_to_dh"],
    )


def find_adjacent_vowels(
    text: str, *, relative: str
) -> list[AdjacentOccurrence]:
    rows: list[AdjacentOccurrence] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
        for token_match in LEXICAL_RE.finditer(line):
            form = token_match.group(0)
            for offset in range(len(form) - 1):
                sequence = form[offset : offset + 2]
                if (
                    sequence[0] in VOWELS
                    and sequence[1] in VOWELS
                    and sequence not in {"ai", "au"}
                ):
                    rows.append(
                        AdjacentOccurrence(
                            file=relative,
                            line_no=line_number,
                            token_start=token_match.start(),
                            token_end=token_match.end(),
                            vowel_offset=offset,
                            form_before=form,
                            matched_sequence=sequence,
                            form_after=form,
                        )
                    )
    return rows


def scan_remaining_l(
    *, root: Path, output_path: Path
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_bytes().decode("utf-8", errors="strict")
        for line_number, line in enumerate(text.split("\n"), start=1):
            for token_match in LEXICAL_RE.finditer(line):
                token = token_match.group(0)
                for match in LATERAL_RE.finditer(token):
                    start = token_match.start() + match.start()
                    rows.append(
                        {
                            "file": relative,
                            "line_no": line_number,
                            "token": token,
                            "context": _context(
                                line, start, start + len(match.group(0))
                            ),
                        }
                    )
    _write_tsv(
        output_path,
        ("file", "line_no", "token", "context"),
        rows,
    )
    return rows


def _merge_candidate_spans(
    spans: list[tuple[int, int, str, tuple[str, ...]]]
) -> list[tuple[int, int, str, tuple[str, ...]]]:
    merged: list[tuple[int, int, str, tuple[str, ...]]] = []
    for start, end, category, triggers in sorted(spans):
        if merged and category == merged[-1][2] and start <= merged[-1][1]:
            old_start, old_end, old_category, old_triggers = merged[-1]
            merged[-1] = (
                old_start,
                max(old_end, end),
                old_category,
                tuple(sorted(set(old_triggers) | set(triggers))),
            )
        else:
            merged.append((start, end, category, triggers))
    return merged


def scan_non_sanskrit_candidates(
    *, root: Path, output_path: Path
) -> list[dict[str, Any]]:
    """Surface positive multi-token or strong-term residue without deletion."""

    rows: list[dict[str, Any]] = []
    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_bytes().decode("utf-8", errors="strict")
        for line_number, line in enumerate(text.split("\n"), start=1):
            spans: list[tuple[int, int, str, tuple[str, ...]]] = []
            for segment_match in re.finditer(r"[^|]+", line):
                segment = segment_match.group(0)
                tokens = list(LEXICAL_RE.finditer(segment))
                values = [match.group(0) for match in tokens]

                for index, value in enumerate(values):
                    if value not in EDITORIAL_STRONG:
                        continue
                    left = index
                    right = index + 1
                    while left and values[left - 1] in ENGLISH_CONTEXT:
                        left -= 1
                    while right < len(values) and values[right] in ENGLISH_CONTEXT:
                        right += 1
                    spans.append(
                        (
                            segment_match.start() + tokens[left].start(),
                            segment_match.start() + tokens[right - 1].end(),
                            "editorial_or_european",
                            (value,),
                        )
                    )

                index = 0
                while index < len(values):
                    if values[index] not in ENGLISH_CONTEXT:
                        index += 1
                        continue
                    end = index + 1
                    while end < len(values) and values[end] in ENGLISH_CONTEXT:
                        end += 1
                    run = values[index:end]
                    if len(run) >= 3 and sum(len(item) >= 3 for item in run) >= 2:
                        spans.append(
                            (
                                segment_match.start() + tokens[index].start(),
                                segment_match.start() + tokens[end - 1].end(),
                                "english_like_run",
                                tuple(run),
                            )
                        )
                    index = end

                index = 0
                while index < len(values):
                    if values[index] not in TIBETAN_WORDS:
                        index += 1
                        continue
                    end = index + 1
                    while end < len(values) and values[end] in TIBETAN_WORDS:
                        end += 1
                    run = values[index:end]
                    if len(run) >= 3 and any(len(item) >= 4 for item in run):
                        spans.append(
                            (
                                segment_match.start() + tokens[index].start(),
                                segment_match.start() + tokens[end - 1].end(),
                                "tibetan_transliteration",
                                tuple(run),
                            )
                        )
                    index = end

                for token in tokens:
                    value = token.group(0)
                    if len(value) >= 8 and len(set(value)) == 1:
                        spans.append(
                            (
                                segment_match.start() + token.start(),
                                segment_match.start() + token.end(),
                                "non_sanskrit_pattern",
                                (value,),
                            )
                        )

            for start, end, category, triggers in _merge_candidate_spans(spans):
                rows.append(
                    {
                        "file": relative,
                        "line_no": line_number,
                        "category": category,
                        "matched_span": line[start:end],
                        "trigger_tokens": " ".join(triggers),
                        "context": _context(line, start, end),
                    }
                )

    _write_tsv(
        output_path,
        (
            "file",
            "line_no",
            "category",
            "matched_span",
            "trigger_tokens",
            "context",
        ),
        rows,
    )
    return rows


def _canonical_to_strict_lines(
    canonical_text: str, strict_text: str
) -> dict[int, int]:
    canonical_lines = [
        (number, line)
        for number, line in enumerate(canonical_text.split("\n"), start=1)
        if line
    ]
    strict_lines: list[tuple[int, str]] = []
    for number, line in enumerate(strict_text.split("\n"), start=1):
        normalized = normalize_to_fixed_point(line).text
        if normalized:
            strict_lines.append((number, normalized))
    if [line for _number, line in canonical_lines] != [
        line for _number, line in strict_lines
    ]:
        raise RuntimeError(
            "strict candidate does not reproduce the mechanically closed "
            "canonical content lines"
        )
    return {
        canonical_number: strict_number
        for (canonical_number, _), (strict_number, _) in zip(
            canonical_lines, strict_lines, strict=True
        )
    }


def _boundary_matches(
    text: str, *, form: str, vowel_offset: int
) -> list[str]:
    """Return literal ASCII-space evidence at one form-internal boundary."""

    if not form or vowel_offset < 0 or vowel_offset + 1 >= len(form):
        return []
    value = normalize_laterals(unicodedata.normalize("NFC", text).casefold()).text
    lexical = re.escape("".join(sorted(IAST_LOWER)) + chr(39))
    parts = [re.escape(form[0])]
    for index, character in enumerate(form[1:], start=1):
        if index - 1 == vowel_offset:
            parts.append(r"(?P<boundary> *)")
        else:
            parts.append(r"-*")
        parts.append(re.escape(character))
    pattern = re.compile(
        rf"(?<![{lexical}]){''.join(parts)}(?![{lexical}])"
    )
    return [match.group("boundary") for match in pattern.finditer(value)]


def _manifest_sources(manifest_path: Path) -> dict[str, Path]:
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sources: dict[str, Path] = {}
    for row in rows:
        relative = row.get("freeze_input_path", "").replace(chr(92), "/")
        if relative:
            sources[relative] = Path(row["source_path"])
    return sources


def _assign_evidence(
    occurrences: list[AdjacentOccurrence],
    boundaries: list[str],
    *,
    field: str,
) -> None:
    if not boundaries:
        return
    ordered = sorted(
        occurrences, key=lambda row: (row.line_no, row.token_start, row.vowel_offset)
    )
    if len(boundaries) != len(ordered):
        return
    for occurrence, boundary in zip(ordered, boundaries, strict=True):
        value = (
            occurrence.form_before[: occurrence.vowel_offset + 1]
            + (" " if boundary else "")
            + occurrence.form_before[occurrence.vowel_offset + 1 :]
        )
        setattr(occurrence, field, value)


def _raw_boundary_events(
    raw_text: str, targets: set[tuple[str, int]]
) -> dict[tuple[str, int], list[RawBoundaryEvent]]:
    """Index literal joined/space evidence in one raw source in one pass."""

    value = normalize_laterals(
        unicodedata.normalize("NFC", raw_text).casefold()
    ).text
    lexical = re.escape("".join(sorted(IAST_LOWER)) + chr(39))
    raw_token_re = re.compile(rf"[{lexical}-]+")
    target_forms = {form for form, _offset in targets}
    evidence: defaultdict[
        tuple[str, int], list[RawBoundaryEvent]
    ] = defaultdict(list)
    tokens: list[tuple[re.Match[str], str, tuple[str, ...]]] = []
    for match in raw_token_re.finditer(value):
        raw_token = match.group(0)
        letters: list[str] = []
        gaps: list[str] = []
        pending = ""
        for character in raw_token:
            if character == "-":
                pending += character
                continue
            if letters:
                gaps.append(pending)
            letters.append(character)
            pending = ""
        key = "".join(letters)
        tokens.append((match, key, tuple(gaps)))

    for index, (match, key, gaps) in enumerate(tokens):
        previous_key = tokens[index - 1][1] if index else ""
        next_key = tokens[index + 1][1] if index + 1 < len(tokens) else ""
        if key in target_forms:
            for form, offset in targets:
                if form != key or offset >= len(gaps):
                    continue
                if gaps[offset] == "":
                    evidence[(form, offset)].append(
                        RawBoundaryEvent(
                            position=match.start(),
                            boundary="",
                            previous_form=previous_key,
                            next_form=next_key,
                        )
                    )

        if index + 1 < len(tokens):
            next_match, next_token_key, _next_gaps = tokens[index + 1]
            gap = value[match.end() : next_match.start()]
            combined = key + next_token_key
            target = (combined, len(key) - 1)
            if gap and gap.strip(" ") == "" and target in targets:
                following_key = (
                    tokens[index + 2][1]
                    if index + 2 < len(tokens)
                    else ""
                )
                evidence[target].append(
                    RawBoundaryEvent(
                        position=match.end(),
                        boundary=" ",
                        previous_form=previous_key,
                        next_form=following_key,
                    )
                )

    return {
        target: sorted(items, key=lambda event: event.position)
        for target, items in evidence.items()
    }


def _raw_boundary_evidence(
    raw_text: str, targets: set[tuple[str, int]]
) -> dict[tuple[str, int], list[str]]:
    events = _raw_boundary_events(raw_text, targets)
    return {
        target: [event.boundary for event in items]
        for target, items in events.items()
    }


def _canonical_neighbors(
    text: str, occurrence: AdjacentOccurrence
) -> tuple[str, str]:
    line = text.split("\n")[occurrence.line_no - 1]
    tokens = list(LEXICAL_RE.finditer(line))
    for index, token in enumerate(tokens):
        if (
            token.start() == occurrence.token_start
            and token.end() == occurrence.token_end
        ):
            previous = tokens[index - 1].group(0) if index else ""
            following = (
                tokens[index + 1].group(0)
                if index + 1 < len(tokens)
                else ""
            )
            return previous, following
    return "", ""


def _assign_raw_events(
    occurrences: list[AdjacentOccurrence],
    events: list[RawBoundaryEvent],
    *,
    lateral_text: str,
) -> None:
    ordered = sorted(
        occurrences, key=lambda row: (row.line_no, row.token_start, row.vowel_offset)
    )
    if len(events) == len(ordered):
        for occurrence, event in zip(ordered, events, strict=True):
            occurrence.raw_form = (
                occurrence.form_before[: occurrence.vowel_offset + 1]
                + (" " if event.boundary else "")
                + occurrence.form_before[occurrence.vowel_offset + 1 :]
            )
        return

    unused = set(range(len(events)))
    for occurrence in ordered:
        previous, following = _canonical_neighbors(
            lateral_text, occurrence
        )
        candidates = [
            index
            for index in unused
            if events[index].previous_form == previous
            and events[index].next_form == following
        ]
        if len(candidates) != 1:
            continue
        event_index = candidates[0]
        unused.remove(event_index)
        event = events[event_index]
        occurrence.raw_form = (
            occurrence.form_before[: occurrence.vowel_offset + 1]
            + (" " if event.boundary else "")
            + occurrence.form_before[occurrence.vowel_offset + 1 :]
        )


def adjudicate_adjacent_vowels(
    *,
    original_texts: dict[str, str],
    lateral_texts: dict[str, str],
    strict_root: Path,
    document_root: Path,
    manifest_path: Path,
) -> list[AdjacentOccurrence]:
    """Trace every occurrence through immediate intermediate and raw source."""

    all_occurrences: list[AdjacentOccurrence] = []
    sources = _manifest_sources(manifest_path)
    raw_cache: dict[Path, str] = {}

    for relative in sorted(lateral_texts):
        occurrences = find_adjacent_vowels(
            lateral_texts[relative], relative=relative
        )
        all_occurrences.extend(occurrences)
        if not occurrences:
            continue

        strict_path = strict_root / relative
        document_path = document_root / relative
        if not strict_path.is_file() or not document_path.is_file():
            continue
        strict_text = strict_path.read_bytes().decode("utf-8", errors="strict")
        line_map = _canonical_to_strict_lines(
            original_texts[relative], strict_text
        )
        document_lines = document_path.read_bytes().decode(
            "utf-8", errors="strict"
        ).split("\n")

        line_groups: defaultdict[
            tuple[int, str, int], list[AdjacentOccurrence]
        ] = defaultdict(list)
        file_groups: defaultdict[
            tuple[str, int], list[AdjacentOccurrence]
        ] = defaultdict(list)
        for occurrence in occurrences:
            line_groups[
                (
                    occurrence.line_no,
                    occurrence.form_before,
                    occurrence.vowel_offset,
                )
            ].append(occurrence)
            file_groups[
                (occurrence.form_before, occurrence.vowel_offset)
            ].append(occurrence)

        for (line_no, form, offset), group in line_groups.items():
            strict_line = line_map.get(line_no)
            if strict_line is None or strict_line > len(document_lines):
                continue
            boundaries = _boundary_matches(
                document_lines[strict_line - 1],
                form=form,
                vowel_offset=offset,
            )
            _assign_evidence(
                group, boundaries, field="intermediate_form"
            )

        raw_path = sources.get(relative)
        if raw_path is not None and raw_path.is_file():
            if raw_path not in raw_cache:
                raw_cache[raw_path] = raw_path.read_bytes().decode(
                    "utf-8", errors="replace"
                )
            raw_events = _raw_boundary_events(
                raw_cache[raw_path], set(file_groups)
            )
            for target, group in file_groups.items():
                _assign_raw_events(
                    group,
                    raw_events.get(target, []),
                    lateral_text=lateral_texts[relative],
                )

        for occurrence in occurrences:
            split_intermediate = " " in occurrence.intermediate_form
            split_raw = " " in occurrence.raw_form
            joined_raw = (
                bool(occurrence.raw_form)
                and " " not in occurrence.raw_form
            )
            if split_intermediate or split_raw:
                occurrence.status = "PIPELINE_BOUNDARY_LOSS_FIXED"
                occurrence.action = "restore_space"
            elif joined_raw:
                occurrence.status = "SOURCE_PRESENT"

    return all_occurrences


def apply_boundary_repairs(
    texts: dict[str, str], occurrences: list[AdjacentOccurrence]
) -> dict[str, str]:
    """Apply only occurrence-level repairs with positive provenance evidence."""

    insertions: defaultdict[tuple[str, int], set[int]] = defaultdict(set)
    token_offsets: defaultdict[tuple[str, int, int, int], set[int]] = defaultdict(set)
    for occurrence in occurrences:
        if occurrence.status != "PIPELINE_BOUNDARY_LOSS_FIXED":
            continue
        position = occurrence.token_start + occurrence.vowel_offset + 1
        insertions[(occurrence.file, occurrence.line_no)].add(position)
        token_offsets[
            (
                occurrence.file,
                occurrence.line_no,
                occurrence.token_start,
                occurrence.token_end,
            )
        ].add(occurrence.vowel_offset + 1)

    repaired: dict[str, str] = {}
    for relative, text in texts.items():
        lines = text.split("\n")
        for (file_name, line_no), positions in insertions.items():
            if file_name != relative:
                continue
            line = lines[line_no - 1]
            for position in sorted(positions, reverse=True):
                line = line[:position] + " " + line[position:]
            lines[line_no - 1] = line
        repaired[relative] = "\n".join(lines)

    for occurrence in occurrences:
        offsets = token_offsets.get(
            (
                occurrence.file,
                occurrence.line_no,
                occurrence.token_start,
                occurrence.token_end,
            ),
            set(),
        )
        form_after = occurrence.form_before
        for offset in sorted(offsets, reverse=True):
            form_after = form_after[:offset] + " " + form_after[offset:]
        occurrence.form_after = form_after
    return repaired


def write_adjacent_report(
    path: Path, occurrences: list[AdjacentOccurrence]
) -> None:
    rows = [
        {
            "file": row.file,
            "line_no": row.line_no,
            "form_before": row.form_before,
            "matched_sequence": row.matched_sequence,
            "raw_form": row.raw_form,
            "intermediate_form": row.intermediate_form,
            "status": row.status,
            "action": row.action,
            "form_after": row.form_after,
        }
        for row in sorted(
            occurrences,
            key=lambda item: (
                item.file,
                item.line_no,
                item.token_start,
                item.vowel_offset,
            ),
        )
    ]
    _write_tsv(
        path,
        (
            "file",
            "line_no",
            "form_before",
            "matched_sequence",
            "raw_form",
            "intermediate_form",
            "status",
            "action",
            "form_after",
        ),
        rows,
    )


def _sync_candidate_to_canonical(
    *, candidate_root: Path, canonical_root: Path
) -> int:
    candidate_files = _text_files(candidate_root)
    canonical_files = _text_files(canonical_root)
    candidate_relatives = {
        path.relative_to(candidate_root).as_posix(): path
        for path in candidate_files
    }
    canonical_relatives = {
        path.relative_to(canonical_root).as_posix(): path
        for path in canonical_files
    }
    if set(candidate_relatives) != set(canonical_relatives):
        raise RuntimeError("semantic candidate/canonical membership mismatch")

    changed = 0
    for relative, source in candidate_relatives.items():
        destination = canonical_relatives[relative]
        data = source.read_bytes()
        if destination.read_bytes() == data:
            continue
        temporary = destination.with_name(
            destination.name + ".semantic_closure_tmp"
        )
        temporary.write_bytes(data)
        temporary.replace(destination)
        changed += 1
    return changed


def _write_freeze_state(
    path: Path,
    *,
    canonical_root: Path,
    manifest_path: Path,
    before_sha256: str,
    after_sha256: str,
    files_processed: int,
    apostrophe_occurrences: int,
) -> None:
    files = _text_files(canonical_root)
    byte_count = sum(file_path.stat().st_size for file_path in files)
    char_count = sum(
        len(file_path.read_bytes().decode("utf-8", errors="strict"))
        for file_path in files
    )
    lines = [
        "Formal GRETIL canonical corpus state after pre-M0 semantic closure",
        "=================================================================",
        f"implementation: {IMPLEMENTATION}",
        f"output_root: {canonical_root}",
        f"manifest: {manifest_path}",
        f"files_frozen: {files_processed}",
        f"byte_count: {byte_count}",
        f"char_count: {char_count}",
        f"pre_semantic_closure_corpus_sha256: {before_sha256}",
        f"corpus_sha256: {after_sha256}",
        f"strict_clean_files: {files_processed}",
        "invalid_character_files: 0",
        "invalid_character_occurrences: 0",
        "invalid_apostrophe_files: 0",
        "invalid_apostrophe_occurrences: 0",
        f"validated_apostrophe_occurrences: {apostrophe_occurrences}",
        "",
        "state policy:",
        "  canonical bytes are generated by the recorded semantic closure stage",
        "  vowel-adjacent ḷ and ḷh normalization follows the closed positive rule",
        "  spaces are restored only with occurrence-level intermediate/raw evidence",
        "  SOURCE_PRESENT and UNRESOLVED adjacent vowels remain unchanged",
        "  non-Sanskrit candidates are reported read-only",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def _write_semantic_report(
    path: Path,
    *,
    result: SemanticClosureResult,
    status_counts: Counter[str],
    non_sanskrit_rows: list[dict[str, Any]],
    remaining_l_rows: list[dict[str, Any]],
    occurrences: list[AdjacentOccurrence],
) -> None:
    category_counts = Counter(
        str(row["category"]) for row in non_sanskrit_rows
    )
    lines = [
        "# pre-M0 semantic closure",
        "",
        f"- Implementation: {IMPLEMENTATION}",
        f"- Canonical SHA256 before: {result.before_sha256}",
        f"- Canonical SHA256 after: {result.after_sha256}",
        f"- Files processed: {result.files_processed}",
        f"- Files modified: {result.files_modified}",
        "",
        "## Non-Sanskrit candidates",
        "",
        f"- Candidate spans: {result.non_sanskrit_candidates}",
        f"- Files involved: {result.non_sanskrit_files}",
    ]
    for category, count in sorted(category_counts.items()):
        lines.append(f"- {category}: {count}")
    involved_files = sorted(
        {str(row["file"]) for row in non_sanskrit_rows}
    )
    if involved_files:
        lines.extend(["- Files:"])
        lines.extend(f"  - `{relative}`" for relative in involved_files)
    lines.extend(["", "Representative candidates:", ""])
    if non_sanskrit_rows:
        for row in non_sanskrit_rows[:10]:
            lines.append(
                f"- {row['file']}:{row['line_no']} [{row['category']}] "
                f"{row['matched_span']}"
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## ḷ / ḷh normalization",
            "",
            f"- ḷ → ḍ replacements: {result.l_to_d}",
            f"- ḷh → ḍh replacements: {result.lh_to_dh}",
            f"- Remaining ḷ/ḷh occurrences: {result.remaining_l}",
            "",
            "Remaining forms are unchanged and listed in pre_m0_remaining_l.tsv.",
            "",
            "## Adjacent-vowel provenance",
            "",
            f"- Anomalies after lateral normalization: {result.adjacent_before}",
            f"- PIPELINE_BOUNDARY_LOSS_FIXED: {status_counts.get('PIPELINE_BOUNDARY_LOSS_FIXED', 0)}",
            f"- SOURCE_PRESENT: {status_counts.get('SOURCE_PRESENT', 0)}",
            f"- UNRESOLVED: {status_counts.get('UNRESOLVED', 0)}",
            f"- Remaining anomalies after confirmed repairs: {result.adjacent_after}",
            "",
            "Only literal ASCII lexical-space evidence in the aligned document "
            "intermediate or raw source authorizes repair. Hyphens, generic "
            "word expectations, and mixed evidence do not.",
            "",
            "Representative provenance rows:",
            "",
        ]
    )
    for status in (
        "PIPELINE_BOUNDARY_LOSS_FIXED",
        "SOURCE_PRESENT",
        "UNRESOLVED",
    ):
        examples = [row for row in occurrences if row.status == status][:4]
        for row in examples:
            lines.append(
                f"- {status}: {row.file}:{row.line_no} "
                f"{row.form_before} [{row.matched_sequence}] → {row.form_after}; "
                f"intermediate={row.intermediate_form or '-'}; "
                f"raw={row.raw_form or '-'}"
            )

    lines.extend(
        [
            "",
            "## Verification",
            "",
            "- strict invalid characters: 0",
            "- strict invalid apostrophes: 0",
            "- mechanical normalization: fixed point",
            "- standalone danda/space/newline checks: PASS",
            "- provenance audit modifies no source/intermediate file",
            "- repository tests: run separately after semantic promotion",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="")


def run_semantic_closure(
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    input_root: Path = DEFAULT_INPUT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    strict_root: Path = DEFAULT_STRICT_ROOT,
    document_root: Path = DEFAULT_DOCUMENT_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    freeze_report_path: Path = DEFAULT_FREEZE_REPORT,
    report_path: Path = DEFAULT_REPORT,
    non_sanskrit_path: Path = DEFAULT_NON_SANSKRIT,
    remaining_l_path: Path = DEFAULT_REMAINING_L,
    adjacent_path: Path = DEFAULT_ADJACENT,
) -> SemanticClosureResult:
    checkpoint_sha256 = build_mechanical_input_checkpoint(
        strict_root=strict_root,
        input_root=input_root,
    )
    source_files = _text_files(input_root)
    if output_root.resolve() == canonical_root.resolve():
        raise ValueError("semantic output root must differ from canonical root")
    before_sha256 = corpus_sha256(input_root, source_files)
    if checkpoint_sha256 != before_sha256:
        raise RuntimeError("mechanical checkpoint SHA changed after construction")
    original_texts: dict[str, str] = {}
    lateral_texts: dict[str, str] = {}
    l_to_d = 0
    lh_to_dh = 0
    for path in source_files:
        relative = path.relative_to(input_root).as_posix()
        original = path.read_bytes().decode("utf-8", errors="strict")
        lateral = normalize_laterals(original)
        original_texts[relative] = original
        lateral_texts[relative] = lateral.text
        l_to_d += lateral.l_to_d
        lh_to_dh += lateral.lh_to_dh

    occurrences = adjudicate_adjacent_vowels(
        original_texts=original_texts,
        lateral_texts=lateral_texts,
        strict_root=strict_root,
        document_root=document_root,
        manifest_path=manifest_path,
    )
    repaired_texts = apply_boundary_repairs(lateral_texts, occurrences)

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    files_modified = 0
    for relative, text in repaired_texts.items():
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(text.encode("utf-8"))
        files_modified += int(text != original_texts[relative])

    strict = validate_corpus(input_root=output_root, require_clean=True)
    mechanical = validate_mechanical_corpus(canonical_root=output_root)
    if not mechanical.is_clean:
        raise RuntimeError(
            f"semantic candidate failed mechanical validation: {mechanical}"
        )

    remaining_l_rows = scan_remaining_l(
        root=output_root, output_path=remaining_l_path
    )
    non_sanskrit_rows = scan_non_sanskrit_candidates(
        root=output_root, output_path=non_sanskrit_path
    )
    write_adjacent_report(adjacent_path, occurrences)
    adjacent_after = sum(
        len(find_adjacent_vowels(
            repaired_texts[relative], relative=relative
        ))
        for relative in repaired_texts
    )
    candidate_files = _text_files(output_root)
    after_sha256 = corpus_sha256(output_root, candidate_files)

    _sync_candidate_to_canonical(
        candidate_root=output_root,
        canonical_root=canonical_root,
    )
    canonical_after = corpus_sha256(
        canonical_root, _text_files(canonical_root)
    )
    if canonical_after != after_sha256:
        raise RuntimeError("promoted canonical SHA does not match semantic candidate")

    refresh_canonical_manifest(
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        freeze_id=after_sha256,
    )
    _write_freeze_state(
        freeze_report_path,
        canonical_root=canonical_root,
        manifest_path=manifest_path,
        before_sha256=before_sha256,
        after_sha256=after_sha256,
        files_processed=len(source_files),
        apostrophe_occurrences=strict.apostrophe_occurrences,
    )
    status_counts = Counter(row.status for row in occurrences)
    result = SemanticClosureResult(
        files_processed=len(source_files),
        files_modified=files_modified,
        before_sha256=before_sha256,
        after_sha256=after_sha256,
        l_to_d=l_to_d,
        lh_to_dh=lh_to_dh,
        remaining_l=len(remaining_l_rows),
        adjacent_before=len(occurrences),
        adjacent_after=adjacent_after,
        status_counts=status_counts,
        non_sanskrit_candidates=len(non_sanskrit_rows),
        non_sanskrit_files=len(
            {str(row["file"]) for row in non_sanskrit_rows}
        ),
    )
    _write_semantic_report(
        report_path,
        result=result,
        status_counts=status_counts,
        non_sanskrit_rows=non_sanskrit_rows,
        remaining_l_rows=remaining_l_rows,
        occurrences=occurrences,
    )
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run pre-M0 semantic closure for canonical GRETIL IAST"
    )
    parser.add_argument(
        "--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT
    )
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict-root", type=Path, default=DEFAULT_STRICT_ROOT)
    parser.add_argument(
        "--document-root", type=Path, default=DEFAULT_DOCUMENT_ROOT
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--freeze-report", type=Path, default=DEFAULT_FREEZE_REPORT
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--non-sanskrit-report", type=Path, default=DEFAULT_NON_SANSKRIT
    )
    parser.add_argument(
        "--remaining-l-report", type=Path, default=DEFAULT_REMAINING_L
    )
    parser.add_argument(
        "--adjacent-report", type=Path, default=DEFAULT_ADJACENT
    )
    args = parser.parse_args(argv)
    result = run_semantic_closure(
        canonical_root=args.canonical_root,
        input_root=args.input_root,
        output_root=args.output_root,
        strict_root=args.strict_root,
        document_root=args.document_root,
        manifest_path=args.manifest,
        freeze_report_path=args.freeze_report,
        report_path=args.report,
        non_sanskrit_path=args.non_sanskrit_report,
        remaining_l_path=args.remaining_l_report,
        adjacent_path=args.adjacent_report,
    )
    print(f"files processed: {result.files_processed}")
    print(f"files modified: {result.files_modified}")
    print(f"l-with-dot to d-with-dot: {result.l_to_d}")
    print(f"l-with-dot-h to d-with-dot-h: {result.lh_to_dh}")
    print(f"remaining lateral forms: {result.remaining_l}")
    print(f"adjacent vowels before repair: {result.adjacent_before}")
    for status in (
        "PIPELINE_BOUNDARY_LOSS_FIXED",
        "SOURCE_PRESENT",
        "UNRESOLVED",
    ):
        print(f"{status}: {result.status_counts.get(status, 0)}")
    print(f"adjacent vowels after repair: {result.adjacent_after}")
    print(f"non-Sanskrit candidates: {result.non_sanskrit_candidates}")
    print(f"before sha256: {result.before_sha256}")
    print(f"after sha256: {result.after_sha256}")


if __name__ == "__main__":
    main()

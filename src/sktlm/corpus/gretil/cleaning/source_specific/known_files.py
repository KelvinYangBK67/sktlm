"""Positive-match cleanup for the manually adjudicated pre-M0 file set.

This stage deliberately does not perform corpus-wide whitespace, blank-line,
or danda normalization.  It removes only documented source conventions and
rebuilds the one file whose body was lost upstream.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from sktlm.corpus.gretil.build import extract_gretil_body, normalize_canonical_iast
from sktlm.corpus.gretil.cleaning.editorial import clean_document as clean_editorial
from sktlm.corpus.gretil.cleaning.hyphens import normalize_document as normalize_hyphens
from sktlm.corpus.gretil.cleaning.mechanical import apply_pass1
from sktlm.corpus.gretil.cleaning.pluta import normalize_vedic_pluta
from sktlm.corpus.gretil.cleaning.separators import (
    normalize_document as normalize_separators,
)


IMPLEMENTATION = "gretil-known-file-cleanup-1"
DEFAULT_INPUT_ROOT = Path(
    "data/intermediate/gretil/pre_strict_canonical_checkpoint_gretil_iast"
)
DEFAULT_RAW_ROOT = Path("data/raw/gretil")
DEFAULT_OUTPUT_ROOT = Path(
    "data/intermediate/gretil/known_file_cleaned_gretil_iast"
)
DEFAULT_REPORT_DIR = Path("reports/cleaning/generated/known_files")

TARGET_PATHS = (
    "3_purana/sivap1_u.txt",
    "3_purana/sivap7_u.txt",
    "4_rellit/buddh/srabhu_u.txt",
    "4_rellit/buddh/udanav_u.txt",
    "4_rellit/buddh/vinsutru.txt",
    "4_rellit/buddh/vinv01_u.txt",
    "4_rellit/buddh/vinv02_u.txt",
    "4_rellit/buddh/vinv03_u.txt",
    "4_rellit/buddh/vinv04_u.txt",
    "4_rellit/buddh/vinv08_u.txt",
    "4_rellit/buddh/vinv11_u.txt",
    "4_rellit/vaisn/ss4_krsu.txt",
    "5_poetry/2_kavya/amaru_u.txt",
    "5_poetry/2_kavya/nkalivpu.txt",
    "5_poetry/2_kavya/ramodtpu.txt",
    "5_poetry/4_narr/brkas_pu.txt",
    "5_poetry/5_subhas/vidsrgpu.txt",
    "6_sastra/3_phil/saiva/pratyabu.txt",
    "6_sastra/3_phil/samkhya/isvskaru.txt",
    "6_sastra/4_dharma/sutra/apastd_u.txt",
    "6_sastra/4_dharma/sutra/vaikhd_u.txt",
    "6_sastra/4_dharma/sutra/vasist_u.txt",
    "6_sastra/5_artha/kautil_u.txt",
    "6_sastra/8_jyot/aryabh_u.txt",
    "6_sastra/8_jyot/brhajj_u.txt",
    "6_sastra/8_jyot/brhats_u.txt",
    "6_sastra/8_jyot/bijaganu.txt",
)
TARGET_SET = frozenset(TARGET_PATHS)

BRHAJJ_PATH = "6_sastra/8_jyot/brhajj_u.txt"
BRHAJJ_RAW_PATH = "6_sastra/8_jyot/brhajj_u.htm"

GRAMMAR_LABEL_RE = re.compile(
    r"(?i)(?<![a-z])(?:opt|caus|ppp|ger|des)(?![a-z])"
)
ISV_WITNESS_RE = re.compile(
    r"(?<!\w)(?:V[12]?|M|G|D|K|Y|J|S|B|T|F|A|E|C)(?!\w)"
)
SS4_EDITORIAL_RE = re.compile(
    r"(?i)\b(?:edition|adds?|addition|alternative|appears|earlier|ends?|"
    r"ending|omits?|omitted|page|published|reading|reads?|section|starting|"
    r"thakur|above|differs?|inserts?|endnote|sarva-saṃvādinī)\b"
)
SS4_BLOCK_START_RE = re.compile(
    r"\[(?=[^\n]*(?:vṛ|vr\.?|v\.?|b\.?|a\b|edition|section|the above))"
    r"(?=[^\n]*\b(?:edition|adds?|addition|reads?|inserts?|omits?|"
    r"replaces?|differs?|section)\b)",
    re.IGNORECASE,
)
SS4_BLOCK_END_RE = re.compile(
    r"(?i)(?:\bend(?:s)?\b|^\s*(?:vṛ\.?\s+)?(?:reading|addition)\.?\])"
)
KUTILA_ENGLISH_RE = re.compile(
    r"(?i)(?:^Prose sections\b|^\((?:Book|Chap|ṛecovery)\b|"
    r"^section\d+\b|^EEE\s*=End\b)"
)
VAikh_APPARATUS_RE = re.compile(
    r"\\(?:on the reading|cf\.?|reading uncertain|Cal reads?)[^)\n]*\)",
    re.IGNORECASE,
)
VAikh_SUPPLIED_RE = re.compile(r"\\([A-Za-zāīūṛṝḷḹṃḥṅñṭḍṇśṣ]+)\)")

WYLIE_WORDS = frozenset(
    {
        "bdag", "bśad", "bstan", "bya", "bźi", "chos", "daṅ", "dbus",
        "dge", "dman", "gaṅ", "gdams", "gnas", "gñis", "gtso", "gyur",
        "lta", "med", "mthun", "mya", "naṅ", "ṅan", "pa'i", "ba'i",
        "de'i", "rgyas", "rgyu", "rig", "rjes", "rkyen", "rnam", "rnams",
        "bskal", "bsdus", "bya", "cad", "graṅs", "gsum",
        "gyis", "jug", "kyi", "lus", "maḥi", "mdor",
        "byed", "ltar", "phyi", "rigs", "riṅ", "rñed",
        "rtog", "rtsa", "skal", "spyod",
        "skyes", "smras", "sgrib", "ste", "thams", "tshaṅ",
        "yod",
        "tshogs", "tshul", "yid", "yin", "yoṅs", "źe",
    }
)

EVIDENCE_NOTES = {
    "3_purana/sivap1_u.txt": "standalone Chapter labels in checkpoint/raw",
    "3_purana/sivap7_u.txt": "standalone Chapter labels in checkpoint/raw",
    "4_rellit/buddh/srabhu_u.txt": "Wylie Tibetan spans plus witness locator rows",
    "4_rellit/buddh/udanav_u.txt": "internal single danda is source segmentation",
    "4_rellit/buddh/vinsutru.txt": "outer single-danda wrapper and Tibetan header/footer",
    "4_rellit/buddh/vinv01_u.txt": "(Pravr-v II): ||| wrapper; .ṭ. m residue",
    "4_rellit/buddh/vinv02_u.txt": "Poṣ-v locators and line-leading edition labels",
    "4_rellit/buddh/vinv03_u.txt": "Pravā-v locator rows and lost-text notices",
    "4_rellit/buddh/vinv04_u.txt": "Var-v § locator prefix and a/b labels",
    "4_rellit/buddh/vinv08_u.txt": "Kaṭhina v numbered locator prefix",
    "4_rellit/buddh/vinv11_u.txt": "Pāṇḍ v § prefix and uppercase Ś source separator",
    "4_rellit/vaisn/ss4_krsu.txt": "edition-prose bracket units and endnote tail",
    "5_poetry/2_kavya/amaru_u.txt": "two explicit Text/Abbreviations/Main Text blocks",
    "5_poetry/2_kavya/nkalivpu.txt": "three complete *VAR apparatus rows",
    "5_poetry/2_kavya/ramodtpu.txt": "RmUD *n.a/c edition locators",
    "5_poetry/4_narr/brkas_pu.txt": "all square units are English metadata/placeholders",
    "5_poetry/5_subhas/vidsrgpu.txt": "opening abbreviation table",
    "6_sastra/3_phil/saiva/pratyabu.txt": "raw .=<BR>m split and NOTES tail",
    "6_sastra/3_phil/samkhya/isvskaru.txt": "witness rows and explicit word index",
    "6_sastra/4_dharma/sutra/apastd_u.txt": "nested grammatical units and source segmentation",
    "6_sastra/4_dharma/sutra/vaikhd_u.txt": "Vaikh locators and backslash apparatus",
    "6_sastra/4_dharma/sutra/vasist_u.txt": "Va locators; dot/caret morphological segmentation",
    "6_sastra/5_artha/kautil_u.txt": "English structure rows; internal pipe segmentation",
    "6_sastra/8_jyot/aryabh_u.txt": "short tokens adjudicated as body; no deletion",
    "6_sastra/8_jyot/brhajj_u.txt": "844 BJ_ body records lost by generic siglum stripping",
    "6_sastra/8_jyot/brhats_u.txt": "header declares every square unit a supplied variant",
    "6_sastra/8_jyot/bijaganu.txt": "two exact [prose] editorial labels",
}


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    line_number: int
    rule: str
    removed: str
    replacement: str
    line_before: str
    line_after: str


@dataclass(frozen=True, slots=True)
class CleanupResult:
    files_processed: int
    target_files: int
    files_changed: int
    occurrences: int
    input_chars: int
    output_chars: int
    rule_counts: Counter[str]


def _replacement_text(
    replacement: str | Callable[[re.Match[str]], str], match: re.Match[str]
) -> str:
    return replacement(match) if callable(replacement) else match.expand(replacement)


def _sub(
    line: str,
    pattern: re.Pattern[str],
    replacement: str | Callable[[re.Match[str]], str],
    *,
    path: str,
    line_number: int,
    rule: str,
    count: int = 0,
) -> tuple[str, list[Change]]:
    matches = list(pattern.finditer(line))
    if count:
        matches = matches[:count]
    if not matches:
        return line, []
    pieces: list[str] = []
    cursor = 0
    replacements: list[str] = []
    for match in matches:
        pieces.append(line[cursor : match.start()])
        value = _replacement_text(replacement, match)
        pieces.append(value)
        replacements.append(value)
        cursor = match.end()
    pieces.append(line[cursor:])
    output = "".join(pieces)
    return output, [
        Change(
            path=path,
            line_number=line_number,
            rule=rule,
            removed=match.group(0),
            replacement=value,
            line_before=line,
            line_after=output,
        )
        for match, value in zip(matches, replacements, strict=True)
    ]


def _blank(line: str, *, path: str, line_number: int, rule: str) -> tuple[str, list[Change]]:
    if not line:
        return line, []
    return "", [
        Change(path, line_number, rule, line, "", line, "")
    ]


def _looks_tibetan(text: str) -> bool:
    lowered = text.casefold()
    if "ź" in lowered or re.search(r"\bsmras\s+pa\b", lowered):
        return True
    tokens = re.findall(r"[a-zāīūṛṝḷḹṃḥṅñṭḍṇśṣź']+", lowered)
    score = sum(token.strip("'") in WYLIE_WORDS for token in tokens)
    non_avagraha = len(re.findall(r"(?:\b'|\w'\w)", lowered))
    return score >= 2 or (score >= 1 and non_avagraha >= 1)


def _is_srabhu_locator(line: str) -> bool:
    stripped = line.strip()
    if re.fullmatch(r"\(Śbh\s+[IVX]+\s+\d+\)", stripped):
        return True
    if re.fullmatch(
        r"(?:\(I\)-C-IIl-4-a-|-II-3-b-)\s+-i{1,2}'?", stripped
    ):
        return True
    witnesses = re.findall(r"(?<!\w)(?:Ms|Sh|W|P|D|N|Co|Ch)\.", stripped)
    return len(witnesses) >= 2 and bool(re.match(r"^[()|IVXA-]", stripped))


def _remove_units(
    text: str,
    *,
    path: str,
    predicate: Callable[[str], bool],
    rule: str,
) -> tuple[str, list[Change]]:
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for index, character in enumerate(text):
        if character == "[":
            stack.append(index)
        elif character == "]" and stack:
            spans.append((stack.pop(), index + 1))

    selected: list[tuple[int, int]] = []
    for unit_start, unit_end in sorted(spans, key=lambda span: (span[0], -span[1])):
        if any(
            outer_start <= unit_start and unit_end <= outer_end
            for outer_start, outer_end in selected
        ):
            continue
        if predicate(text[unit_start:unit_end]):
            selected.append((unit_start, unit_end))

    output: list[str] = []
    changes: list[Change] = []
    cursor = 0
    for unit_start, unit_end in sorted(selected):
        unit = text[unit_start:unit_end]
        output.append(text[cursor:unit_start])
        replacement = "\n" * unit.count("\n")
        output.append(replacement)
        line_number = text.count("\n", 0, unit_start) + 1
        changes.append(
            Change(
                path,
                line_number,
                rule,
                unit,
                replacement,
                unit.split("\n", 1)[0],
                replacement,
            )
        )
        cursor = unit_end
    if not changes:
        return text, []
    output.append(text[cursor:])
    return "".join(output), changes


def _remove_ss4_editorial_blocks(
    text: str, *, path: str
) -> tuple[str, list[Change]]:
    lines = text.split("\n")
    changes: list[Change] = []
    index = 0
    while index < len(lines):
        start_match = SS4_BLOCK_START_RE.search(lines[index])
        continuation = index + 1
        while continuation < len(lines) and not lines[continuation].strip():
            continuation += 1
        if (
            start_match is None
            and continuation < len(lines)
            and re.search(
                r"\[(?:vṛ|vr|v|b|a)\.?\s*$",
                lines[index],
                re.IGNORECASE,
            )
            and re.match(
                r"\s*(?:adds?|addition|reads?|inserts?|omits?|replaces?)\b",
                lines[continuation],
                re.IGNORECASE,
            )
        ):
            start_match = re.search(
                r"\[(?:vṛ|vr|v|b|a)\.?\s*$",
                lines[index],
                re.IGNORECASE,
            )
        if start_match is None:
            index += 1
            continue
        if (
            SS4_BLOCK_END_RE.search(lines[index])
            and lines[index].count("[") == lines[index].count("]")
        ):
            index += 1
            continue
        closing_seen = False
        end_index: int | None = None
        closing_column: int | None = None
        for candidate in range(index, min(len(lines), index + 1000)):
            end_match = SS4_BLOCK_END_RE.search(lines[candidate])
            if end_match is not None:
                closing_seen = True
                closing_search_start = end_match.start()
            else:
                closing_search_start = 0
            closing_column = (
                lines[candidate].find("]", closing_search_start)
                if closing_seen
                else -1
            )
            if closing_column >= 0:
                end_index = candidate
                break
        if end_index is None:
            index += 1
            continue
        assert closing_column is not None
        for line_index in range(index, end_index + 1):
            before = lines[line_index]
            if line_index == index and line_index == end_index:
                after = (
                    before[: start_match.start()]
                    + before[closing_column + 1 :]
                )
            elif line_index == index:
                after = before[: start_match.start()]
            elif line_index == end_index:
                after = before[closing_column + 1 :]
            else:
                after = ""
            if before == after:
                continue
            lines[line_index] = after
            changes.append(
                Change(
                    path,
                    line_index + 1,
                    "ss4_editorial_variant_block_removed",
                    before,
                    after,
                    before,
                    after,
                )
            )
        index = end_index + 1
    return "\n".join(lines), changes


def _remove_ss4_page_markers(
    text: str, *, path: str
) -> tuple[str, list[Change]]:
    pattern = re.compile(
        r"\(page(?:[ \t]*(?:\n[ \t]*)+\d+\))?", re.IGNORECASE
    )
    output: list[str] = []
    changes: list[Change] = []
    cursor = 0
    for match in pattern.finditer(text):
        unit = match.group(0)
        replacement = "\n" * unit.count("\n")
        output.append(text[cursor:match.start()])
        output.append(replacement)
        line_number = text.count("\n", 0, match.start()) + 1
        changes.append(
            Change(
                path,
                line_number,
                "ss4_page_marker_removed",
                unit,
                replacement,
                unit.split("\n", 1)[0],
                replacement,
            )
        )
        cursor = match.end()
    if not changes:
        return text, []
    output.append(text[cursor:])
    return "".join(output), changes


def _remove_tibetan_segments(
    line: str, *, path: str, line_number: int
) -> tuple[str, list[Change]]:
    pieces = re.split(r"(\|+)", line)
    changed: list[tuple[str, str]] = []
    for index in range(0, len(pieces), 2):
        segment = pieces[index]
        if segment.strip() and _looks_tibetan(segment):
            changed.append((segment, ""))
            pieces[index] = ""
    if not changed:
        return line, []
    output = "".join(pieces)
    if not any(character.isalpha() for character in output):
        output = ""
    return output, [
        Change(
            path,
            line_number,
            "tibetan_transcription_span_removed",
            before,
            after,
            line,
            output,
        )
        for before, after in changed
    ]


def _rebuild_brhajj(raw_root: Path) -> str:
    raw_path = raw_root.joinpath(*PurePosixPath(BRHAJJ_RAW_PATH).parts)
    raw_html = raw_path.read_text(encoding="utf-8")
    if len(re.findall(r"(?m)^\s*BJ_\d{2}\.\d{2}[ab]?/\.", raw_html)) < 800:
        raise RuntimeError("brhajj raw source no longer has the adjudicated BJ_ record family")
    text = normalize_canonical_iast(extract_gretil_body(raw_html)).text
    text = apply_pass1(text).text
    text = normalize_vedic_pluta(text, BRHAJJ_PATH).text
    text = clean_editorial(text, BRHAJJ_PATH).text
    text = normalize_separators(text, BRHAJJ_PATH).text
    text = normalize_hyphens(text, BRHAJJ_PATH).text
    if len(text) < 70_000 or sum(bool(line.strip()) for line in text.splitlines()) < 800:
        raise RuntimeError("replayed brhajj body is still unexpectedly small")
    return text


def _clean_line(line: str, *, path: str, line_number: int) -> tuple[str, list[Change]]:
    changes: list[Change] = []

    def apply(
        pattern: re.Pattern[str],
        replacement: str | Callable[[re.Match[str]], str],
        rule: str,
        *,
        count: int = 0,
    ) -> None:
        nonlocal line
        line, new_changes = _sub(
            line,
            pattern,
            replacement,
            path=path,
            line_number=line_number,
            rule=rule,
            count=count,
        )
        changes.extend(new_changes)

    stripped = line.strip()

    if path in {"3_purana/sivap1_u.txt", "3_purana/sivap7_u.txt"}:
        apply(re.compile(r"\bchapter\b", re.IGNORECASE), "", "chapter_label_removed")

    elif path == "4_rellit/buddh/srabhu_u.txt":
        if _is_srabhu_locator(line):
            return _blank(
                line,
                path=path,
                line_number=line_number,
                rule="edition_witness_locator_line_removed",
            )
        line, tibetan = _remove_tibetan_segments(
            line, path=path, line_number=line_number
        )
        changes.extend(tibetan)

    elif path == "4_rellit/buddh/udanav_u.txt":
        apply(
            re.compile(r"(?<!\|)\|(?!\|)(?=[^\n]*\S)"),
            " ",
            "internal_single_danda_segmentation_to_space",
        )

    elif path == "4_rellit/buddh/vinsutru.txt":
        if (
            stripped == "Revised reference system:"
            or re.match(r"^\*{0,2}\(?Vin n(?:[.,n()]|\s*=)", stripped)
            or stripped == "nn = fol. no."
            or stripped == "|| slob dpon yon tan 'od gyis mdzad pa'i 'dul ba mdo ba'i lags so | shri la"
            or stripped.startswith("gnur chos kyi grags pas bris pa")
            or stripped.startswith("(= gnur dharmakīrttinā")
            or stripped == "pratham mukhapatre ---"
            or stripped.startswith("gnur dha rma kir tis bris pa")
        ):
            return _blank(
                line,
                path=path,
                line_number=line_number,
                rule="vinsutru_header_footer_metadata_removed",
            )
        apply(
            re.compile(r"^a ka ras bris ga xiv\.1\s+"),
            "",
            "tibetan_title_prefix_removed",
        )
        had_tibetan_colophon = bool(
            re.match(r"^śī la a ka ra sa bris pa\s+\(=\s*", line)
        )
        apply(
            re.compile(r"^śī la a ka ra sa bris pa\s+\(=\s*"),
            "",
            "tibetan_colophon_prefix_removed",
        )
        if had_tibetan_colophon:
            apply(
                re.compile(r"\)\s*$"),
                "",
                "editorial_equation_delimiter_removed",
            )
        apply(
            re.compile(r"\bdebler sro po\b"),
            "",
            "tibetan_mixed_span_removed",
        )
        line, tibetan = _remove_tibetan_segments(
            line, path=path, line_number=line_number
        )
        changes.extend(tibetan)
        apply(
            re.compile(r"^\s*\|(?!\|)\s?"),
            "",
            "leading_single_danda_wrapper_removed",
            count=1,
        )
        apply(
            re.compile(r"[ \t]*(?<!\|)\|(?!\|)[ \t]*$"),
            "",
            "trailing_single_danda_wrapper_removed",
            count=1,
        )

    elif path == "4_rellit/buddh/vinv01_u.txt":
        apply(
            re.compile(r"^\(Pravr-v[^)]*\):\s*\|{3}\s*"),
            "",
            "pravr_line_wrapper_removed",
            count=1,
        )
        apply(re.compile(r"\.ṭ\.\s+m\s+"), "", "punctuated_apparatus_residue_removed")

    elif path == "4_rellit/buddh/vinv02_u.txt":
        apply(
            re.compile(
                r"\(?Poṣ-v(?:\s+\.?\d+(?:\.\d+)*(?:\.[a-z])?\.?)?\)?"
            ),
            "",
            "pos_locator_removed",
        )
        apply(
            re.compile(r"^\s*[a-e]\s*[.|]\s+"),
            "",
            "line_leading_edition_enumeration_removed",
            count=1,
        )

    elif path == "4_rellit/buddh/vinv03_u.txt":
        pravav_row = bool(re.match(r"^\(?Pravā-v(?:\b|$)", stripped))
        lost_notice = bool(
            re.search(
                r"(?i)\b(?:Sanskrit text|text in Tibetan|is lost|not extant)\b",
                stripped,
            )
        )
        if pravav_row or lost_notice:
            rule = (
                "pravav_structural_marker_line_removed"
                if pravav_row
                else "lost_text_notice_removed"
            )
            return _blank(line, path=path, line_number=line_number, rule=rule)
        apply(
            re.compile(r"\(Pravā-v\s+\d+\)"),
            "",
            "inline_pravav_locator_removed",
        )

    elif path == "4_rellit/buddh/vinv04_u.txt":
        had_prefix = bool(re.match(r"^Var-v\s+§", line))
        apply(
            re.compile(r"^Var-v\s+§(?:\s+(?:\d[\w.-]*|-))?\s*"),
            "",
            "varv_locator_prefix_removed",
            count=1,
        )
        if had_prefix:
            apply(
                re.compile(r"^[ab]\s+"),
                "",
                "varv_edition_enumeration_removed",
                count=1,
            )
        if line.strip() == "-":
            return _blank(
                line,
                path=path,
                line_number=line_number,
                rule="varv_empty_record_removed",
            )

    elif path == "4_rellit/buddh/vinv08_u.txt":
        apply(
            re.compile(r"^Kaṭhina v\s+\d+(?:[a-z]+)?\.\s*"),
            "",
            "kathina_numbered_locator_removed",
            count=1,
        )

    elif path == "4_rellit/buddh/vinv11_u.txt":
        apply(
            re.compile(r"^Pāṇḍ v(?:\s+§)?\s*"),
            "",
            "pandv_locator_prefix_removed",
            count=1,
        )
        apply(
            re.compile(r"(?<!\w)Ś(?!\w)"),
            "",
            "uppercase_source_separator_removed",
        )

    elif path == "5_poetry/2_kavya/nkalivpu.txt" and stripped.startswith("*VAR."):
        return _blank(
            line,
            path=path,
            line_number=line_number,
            rule="complete_variant_apparatus_line_removed",
        )

    elif path == "5_poetry/2_kavya/ramodtpu.txt":
        apply(
            re.compile(r"\s+RmUD\s+\*\d+\.[a-z]\s*"),
            " ",
            "rmud_edition_locator_removed",
        )

    elif path == "6_sastra/4_dharma/sutra/apastd_u.txt":
        apply(
            re.compile(r"^Ap\d[\d.-]*\|?\s*"),
            "",
            "apast_record_locator_removed",
            count=1,
        )
        apply(
            re.compile(r"(?<!\|)\|(?!\|)(?=[^\n]*\S)"),
            " ",
            "internal_single_danda_segmentation_to_space",
        )

    elif path == "6_sastra/4_dharma/sutra/vaikhd_u.txt":
        apply(
            re.compile(r"^Vaikh\s+\d\S*\s*"),
            "",
            "vaikh_record_locator_removed",
            count=1,
        )
        apply(VAikh_APPARATUS_RE, "", "vaikh_english_apparatus_unit_removed")
        apply(
            VAikh_SUPPLIED_RE,
            lambda match: match.group(1),
            "vaikh_supplied_form_delimiters_removed",
        )
        apply(re.compile(r"\s*End of the text\.\s*$"), "", "end_notice_removed")

    elif path == "6_sastra/4_dharma/sutra/vasist_u.txt":
        apply(
            re.compile(r"^Va\.\d+(?:\.\d+)*\s+"),
            "",
            "vasist_record_locator_removed",
            count=1,
        )
        apply(re.compile(r"[\^.]"), " ", "vasist_source_segmentation_to_space")

    elif path == "6_sastra/5_artha/kautil_u.txt":
        if KUTILA_ENGLISH_RE.search(stripped):
            return _blank(
                line,
                path=path,
                line_number=line_number,
                rule="kautil_english_structure_line_removed",
            )
        apply(
            re.compile(r"(?<!\|)\|(?!\|)(?=[^\n]*\S)"),
            " ",
            "internal_single_danda_segmentation_to_space",
        )

    elif path == "6_sastra/8_jyot/bijaganu.txt":
        apply(re.compile(r"\[prose\]", re.IGNORECASE), "", "prose_label_removed")

    return line, changes


def clean_document(text: str, *, path: str) -> tuple[str, list[Change]]:
    changes: list[Change] = []
    ss4_tail_line: int | None = None
    if path == "4_rellit/buddh/vinsutru.txt":
        text, unit_changes = _remove_units(
            text,
            path=path,
            predicate=lambda unit: bool(
                re.search(r"(?i)\b(?:chapter|line|omits?|section)\b", unit)
            ),
            rule="vinsutru_english_editorial_unit_removed",
        )
        changes.extend(unit_changes)
    elif path == "4_rellit/vaisn/ss4_krsu.txt":
        text, page_changes = _remove_ss4_page_markers(text, path=path)
        changes.extend(page_changes)
        text, block_changes = _remove_ss4_editorial_blocks(text, path=path)
        changes.extend(block_changes)
        colophon = text.rfind("samāpto'yaṃ śrī-kṛṣṇa-sandarbhaḥ ||")
        if colophon >= 0:
            tail = text.find("[*ENDNOTE #1]", colophon)
            if tail >= 0:
                ss4_tail_line = text.count("\n", 0, tail) + 1
        text, unit_changes = _remove_units(
            text,
            path=path,
            predicate=lambda unit: bool(SS4_EDITORIAL_RE.search(unit)),
            rule="ss4_editorial_bracket_unit_removed",
        )
        changes.extend(unit_changes)
    elif path == "4_rellit/buddh/srabhu_u.txt":
        text, unit_changes = _remove_units(
            text,
            path=path,
            predicate=_looks_tibetan,
            rule="tibetan_bracket_unit_removed",
        )
        changes.extend(unit_changes)
    elif path == "5_poetry/4_narr/brkas_pu.txt":
        text, unit_changes = _remove_units(
            text,
            path=path,
            predicate=lambda _unit: True,
            rule="brkas_english_editorial_unit_removed",
        )
        changes.extend(unit_changes)
    elif path == "6_sastra/4_dharma/sutra/apastd_u.txt":
        text, unit_changes = _remove_units(
            text,
            path=path,
            predicate=lambda unit: bool(GRAMMAR_LABEL_RE.search(unit)),
            rule="grammatical_annotation_unit_removed",
        )
        changes.extend(unit_changes)
    elif path == "6_sastra/8_jyot/brhats_u.txt":
        text, unit_changes = _remove_units(
            text,
            path=path,
            predicate=lambda _unit: True,
            rule="brhats_declared_variant_unit_removed",
        )
        changes.extend(unit_changes)

    lines = text.split("\n")

    # The raw source uses .=<BR>m and =<BR>a for soft line wrapping.
    if path == "6_sastra/3_phil/saiva/pratyabu.txt":
        for index, current in enumerate(lines):
            if not re.fullmatch(r"[a-zāīūṛṝḷḹṃḥṅñṭḍṇśṣ]", current.strip()):
                continue
            previous = index - 1
            while previous >= 0 and not lines[previous].strip():
                previous -= 1
            if previous < 0 or not lines[previous].endswith("="):
                continue
            before = lines[previous]
            stem = before[:-1]
            if stem.endswith("."):
                stem = stem[:-1]
            after = stem + current.strip()
            lines[previous] = after
            lines[index] = ""
            changes.append(
                Change(
                    path,
                    previous + 1,
                    "quoted_printable_split_letter_rejoined",
                    before + "\\n…\\n" + current,
                    after,
                    before,
                    after,
                )
            )

    output: list[str] = []
    amaru_metadata = False
    vids_abbreviations = False
    praty_notes = False
    isv_index = False
    brhats_header = path == "6_sastra/8_jyot/brhats_u.txt"

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()

        if path == "5_poetry/2_kavya/amaru_u.txt":
            if stripped == "Verses found in Arjunavarmadeva's version not found here":
                cleaned, line_changes = _blank(
                    line,
                    path=path,
                    line_number=line_number,
                    rule="amaru_english_explanation_removed",
                )
                output.append(cleaned)
                changes.extend(line_changes)
                continue
            if stripped == "Text":
                amaru_metadata = True
            if amaru_metadata:
                cleaned, line_changes = _blank(
                    line,
                    path=path,
                    line_number=line_number,
                    rule="amaru_edition_explanation_or_table_row_removed",
                )
                output.append(cleaned)
                changes.extend(line_changes)
                if stripped == "Main Text":
                    amaru_metadata = False
                continue

        if (
            path == "5_poetry/4_narr/brkas_pu.txt"
            and stripped in {"Input by Andreas Bigger", "PLAIN TEXT VERSION", "###"}
        ):
            cleaned, line_changes = _blank(
                line,
                path=path,
                line_number=line_number,
                rule="brkas_english_header_removed",
            )
            output.append(cleaned)
            changes.extend(line_changes)
            continue

        if path == "5_poetry/5_subhas/vidsrgpu.txt":
            if stripped == "Abbreviations used.":
                vids_abbreviations = True
            if vids_abbreviations and stripped != "vidyākara-saṃkalitaḥ":
                cleaned, line_changes = _blank(
                    line,
                    path=path,
                    line_number=line_number,
                    rule="vidsrg_abbreviation_table_row_removed",
                )
                output.append(cleaned)
                changes.extend(line_changes)
                continue
            if stripped == "vidyākara-saṃkalitaḥ":
                vids_abbreviations = False

        if path == "6_sastra/3_phil/saiva/pratyabu.txt":
            if stripped == "NOTES":
                praty_notes = True
            if praty_notes:
                cleaned, line_changes = _blank(
                    line,
                    path=path,
                    line_number=line_number,
                    rule="pratyabu_notes_tail_removed",
                )
                output.append(cleaned)
                changes.extend(line_changes)
                continue

        if path == "6_sastra/3_phil/samkhya/isvskaru.txt":
            if stripped == "The words of the Sāṃkhya-kārikā":
                isv_index = True
            if isv_index:
                cleaned, line_changes = _blank(
                    line,
                    path=path,
                    line_number=line_number,
                    rule="isvskaru_word_index_removed",
                )
                output.append(cleaned)
                changes.extend(line_changes)
                continue
            if stripped and ISV_WITNESS_RE.search(line):
                cleaned, line_changes = _blank(
                    line,
                    path=path,
                    line_number=line_number,
                    rule="isvskaru_witness_apparatus_line_removed",
                )
                output.append(cleaned)
                changes.extend(line_changes)
                continue

        if path == "6_sastra/8_jyot/brhats_u.txt" and brhats_header:
            if stripped == "upanayanādhyāyaḥ":
                brhats_header = False
            else:
                cleaned, line_changes = _blank(
                    line,
                    path=path,
                    line_number=line_number,
                    rule="brhats_english_convention_header_removed",
                )
                output.append(cleaned)
                changes.extend(line_changes)
                continue

        if (
            path == "4_rellit/vaisn/ss4_krsu.txt"
            and ss4_tail_line is not None
            and line_number >= ss4_tail_line
        ):
            cleaned, line_changes = _blank(
                line,
                path=path,
                line_number=line_number,
                rule="ss4_endnote_tail_removed",
            )
            output.append(cleaned)
            changes.extend(line_changes)
            continue

        cleaned, line_changes = _clean_line(
            line, path=path, line_number=line_number
        )
        output.append(cleaned)
        changes.extend(line_changes)

    return "\n".join(output), changes


def _write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_cleanup(
    *,
    input_root: Path,
    raw_root: Path,
    output_root: Path,
    report_dir: Path,
    require_all_targets: bool = True,
) -> CleanupResult:
    if not input_root.is_dir():
        raise FileNotFoundError(f"known-file input root does not exist: {input_root}")
    if not raw_root.is_dir():
        raise FileNotFoundError(f"GRETIL raw root does not exist: {raw_root}")
    if input_root.resolve() == output_root.resolve():
        raise ValueError("known-file input and output roots must differ")
    if output_root.exists():
        raise FileExistsError(f"known-file output root already exists: {output_root}")

    files = tuple(sorted(path for path in input_root.rglob("*.txt") if path.is_file()))
    present = {path.relative_to(input_root).as_posix() for path in files}
    missing = sorted(TARGET_SET - present)
    if require_all_targets and missing:
        raise RuntimeError("missing known-file targets: " + ", ".join(missing))

    output_root.mkdir(parents=True)
    diff_root = report_dir / "diffs"
    file_rows: list[dict[str, Any]] = []
    occurrence_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    files_changed = 0
    input_chars = 0
    output_chars = 0

    for source in files:
        relative = source.relative_to(input_root).as_posix()
        destination = output_root.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        input_chars += len(text)

        if relative == BRHAJJ_PATH:
            cleaned = _rebuild_brhajj(raw_root)
            changes = [
                Change(
                    relative,
                    1,
                    "brhajj_upstream_body_reextracted",
                    f"checkpoint chars={len(text)}",
                    f"replayed chars={len(cleaned)}",
                    text.split("\n", 1)[0],
                    cleaned.split("\n", 1)[0],
                )
            ]
        elif relative in TARGET_SET:
            cleaned, changes = clean_document(text, path=relative)
        else:
            cleaned, changes = text, []

        if cleaned != text:
            files_changed += 1
            destination.write_text(cleaned, encoding="utf-8", newline="")
            diff = "".join(
                difflib.unified_diff(
                    text.splitlines(keepends=True),
                    cleaned.splitlines(keepends=True),
                    fromfile=f"checkpoint/{relative}",
                    tofile=f"known-file/{relative}",
                )
            )
            diff_path = diff_root.joinpath(
                *PurePosixPath(relative + ".diff").parts
            )
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text(diff, encoding="utf-8", newline="")
        else:
            shutil.copy2(source, destination)

        output_chars += len(cleaned)
        counts = Counter(change.rule for change in changes)
        totals.update(counts)
        file_rows.append(
            {
                "path": relative,
                "target": int(relative in TARGET_SET),
                "changed": int(cleaned != text),
                "occurrences": len(changes),
                "input_chars": len(text),
                "output_chars": len(cleaned),
                "char_delta": len(cleaned) - len(text),
            }
        )
        occurrence_rows.extend(
            {
                "path": change.path,
                "line_number": change.line_number,
                "rule": change.rule,
                "removed": change.removed,
                "replacement": change.replacement,
                "line_before": change.line_before,
                "line_after": change.line_after,
            }
            for change in changes
        )

        if relative in TARGET_SET:
            raw_relative = str(PurePosixPath(relative).with_suffix(".htm"))
            raw_path = raw_root.joinpath(*PurePosixPath(raw_relative).parts)
            evidence_rows.append(
                {
                    "path": relative,
                    "checkpoint_sha256": _sha256(source),
                    "raw_path": raw_relative,
                    "raw_sha256": _sha256(raw_path) if raw_path.is_file() else "",
                    "evidence": EVIDENCE_NOTES[relative],
                    "rule_occurrences": len(changes),
                    "changed": int(cleaned != text),
                }
            )

    file_rows.sort(key=lambda row: str(row["path"]))
    evidence_rows.sort(key=lambda row: str(row["path"]))
    occurrence_rows.sort(
        key=lambda row: (
            str(row["path"]),
            int(row["line_number"]),
            str(row["rule"]),
        )
    )
    _write_csv(
        report_dir / "known_file_cleanup_files.csv",
        (
            "path",
            "target",
            "changed",
            "occurrences",
            "input_chars",
            "output_chars",
            "char_delta",
        ),
        file_rows,
    )
    _write_csv(
        report_dir / "known_file_cleanup_occurrences.csv",
        (
            "path",
            "line_number",
            "rule",
            "removed",
            "replacement",
            "line_before",
            "line_after",
        ),
        occurrence_rows,
    )
    _write_csv(
        report_dir / "known_file_cleanup_evidence.csv",
        (
            "path",
            "checkpoint_sha256",
            "raw_path",
            "raw_sha256",
            "evidence",
            "rule_occurrences",
            "changed",
        ),
        evidence_rows,
    )
    summary = [
        "Formal GRETIL known-file cleanup",
        "================================",
        f"implementation: {IMPLEMENTATION}",
        f"input_root: {input_root}",
        f"raw_root: {raw_root}",
        f"output_root: {output_root}",
        f"files_processed: {len(files)}",
        f"target_files: {len(evidence_rows)}",
        f"files_changed: {files_changed}",
        f"occurrences: {len(occurrence_rows)}",
        f"input_chars: {input_chars}",
        f"output_chars: {output_chars}",
        f"char_delta: {output_chars - input_chars}",
        "",
        "rule totals:",
        *(f"  {rule}: {count}" for rule, count in sorted(totals.items())),
        "",
        "scope exclusions:",
        "  no corpus-wide whitespace or blank-line normalization",
        "  no corpus-wide line-start, line-end, standalone, or double-danda rewrite",
        "  no adjacent-vowel or isolated-letter deletion",
        "  aryabh_u short tokens are retained as textual data",
        "  every mutation is path-scoped and recorded with a per-file diff",
        "",
        "The input checkpoint was not modified.",
        "",
    ]
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "known_file_cleanup_summary.txt").write_text(
        "\n".join(summary), encoding="utf-8", newline=""
    )
    return CleanupResult(
        files_processed=len(files),
        target_files=len(evidence_rows),
        files_changed=files_changed,
        occurrences=len(occurrence_rows),
        input_chars=input_chars,
        output_chars=output_chars,
        rule_counts=totals,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Clean the manually adjudicated pre-M0 GRETIL file set"
    )
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--allow-missing-targets", action="store_true")
    args = parser.parse_args(argv)
    result = build_cleanup(
        input_root=args.input_root,
        raw_root=args.raw_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
        require_all_targets=not args.allow_missing_targets,
    )
    print(f"files processed: {result.files_processed}")
    print(f"target files: {result.target_files}")
    print(f"files changed: {result.files_changed}")
    print(f"occurrences: {result.occurrences}")
    print(f"character delta: {result.output_chars - result.input_chars}")


if __name__ == "__main__":
    main()

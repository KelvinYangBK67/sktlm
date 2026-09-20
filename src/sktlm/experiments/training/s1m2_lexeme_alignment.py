"""DCS-structural, model-string-independent held-out target alignment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from sktlm.latent.frontend import ObservedSegment
from sktlm.latent.phonology import normalize_iast
from sktlm.pieces.composed import ComposedAnalysisPosterior


DCS_SOURCE_ROOT = Path("data/external/dcs-source/dcs/data/conllu/files")


@dataclass(frozen=True, slots=True)
class GoldLocation:
    segment_index: int
    token_index: int
    source_start: int
    source_end: int
    dcs_id: int | None
    occ_id: str | None
    component_index: int
    component_count: int
    method: str


@dataclass(frozen=True, slots=True)
class _DcsAtom:
    ids: tuple[int, ...]
    form: str


def _source_block(path: Path, sent_id: str, text: str) -> tuple[list[str] | None, str | None]:
    matches: list[list[str]] = []
    block: list[str] = []

    def consider() -> None:
        metadata = {
            key.strip(): value.strip()
            for line in block
            if line.startswith("# ") and " = " in line
            for key, value in [line[2:].split(" = ", 1)]
        }
        if metadata.get("sent_id") == sent_id and (
            normalize_iast(metadata.get("text", "").strip())
            == normalize_iast(text.strip())
        ):
            matches.append(block.copy())

    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            if line:
                block.append(line)
            elif block:
                consider()
                block.clear()
    if block:
        consider()
    if not matches:
        return None, "dcs_sentence_not_found"
    if len(matches) != 1:
        return None, "dcs_sentence_not_unique"
    return matches[0], None


def _dcs_atoms(
    block: list[str],
) -> tuple[list[_DcsAtom], dict[int, str | None], str | None]:
    tokens: dict[int, tuple[str, str | None]] = {}
    ranges: dict[int, tuple[int, str]] = {}
    for line in block:
        if line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) < 10:
            continue
        identifier = columns[0]
        if identifier.isdigit():
            token_id = int(identifier)
            misc = dict(
                item.split("=", 1)
                for item in columns[9].split("|")
                if "=" in item
            )
            if token_id in tokens:
                return [], {}, "dcs_duplicate_token_id"
            tokens[token_id] = (columns[1], misc.get("OccId"))
        elif "-" in identifier:
            left, _, right = identifier.partition("-")
            if left.isdigit() and right.isdigit():
                start, end = int(left), int(right)
                if start >= end or start in ranges:
                    return [], {}, "dcs_invalid_multiword_range"
                ranges[start] = (end, columns[1])
    if not tokens:
        return [], {}, "dcs_no_tokens"
    atoms: list[_DcsAtom] = []
    covered: set[int] = set()
    for token_id in sorted(tokens):
        if token_id in covered:
            continue
        if token_id in ranges:
            end, form = ranges[token_id]
            members = tuple(range(token_id, end + 1))
            if any(member not in tokens or member in covered for member in members):
                return [], {}, "dcs_invalid_multiword_range"
            atoms.append(_DcsAtom(members, form))
            covered.update(members)
        else:
            if any(start < token_id <= end for start, (end, _) in ranges.items()):
                return [], {}, "dcs_invalid_multiword_range"
            atoms.append(_DcsAtom((token_id,), tokens[token_id][0]))
    return atoms, {key: value[1] for key, value in tokens.items()}, None


def locate_dcs_occurrences(
    row: dict[str, Any],
    segments: tuple[ObservedSegment, ...],
    *,
    dcs_root: Path = DCS_SOURCE_ROOT,
) -> tuple[
    dict[int, GoldLocation], dict[int, str | None], dict[int, str], str | None
]:
    """Map CoNLL-U token IDs to observed source spans, never model strings."""

    source_file = row.get("source_file")
    sent_id = row.get("sent_id")
    if not isinstance(source_file, str) or not isinstance(sent_id, str):
        return {}, {}, {}, "dcs_source_metadata_missing"
    root = dcs_root.resolve()
    path = (root / source_file.replace("\\", "/")).resolve()
    if not path.is_relative_to(root):
        return {}, {}, {}, "dcs_source_path_outside_root"
    if not path.is_file():
        return {}, {}, {}, "dcs_source_file_missing"
    block, error = _source_block(path, sent_id, row["text"])
    if block is None:
        return {}, {}, {}, error
    atoms, occ_ids, error = _dcs_atoms(block)
    if error is not None:
        return {}, occ_ids, {}, error
    # CoNLL-U range rows are one surface atom; ordinary integer IDs are one
    # atom each. DCS # text also retains literal '_' placeholders which the
    # Sanskrit frontend (correctly) has no phonological token for. Therefore
    # align atoms to *all* whitespace-delimited source spans first, then map
    # each span to a frontend token. FORM spelling is not an alignment key:
    # parsed DCS files may have a different sandhi rendering from # text.
    surface_spans = [
        (match.start(), match.end())
        for match in re.finditer(r"\S+", normalize_iast(row["text"]))
    ]
    if len(atoms) != len(surface_spans):
        return {}, occ_ids, {}, "dcs_surface_atom_count_mismatch"
    observed = [
        (segment_index, token_index, token)
        for segment_index, segment in enumerate(segments)
        for token_index, token in enumerate(segment.tokens)
    ]
    locations: dict[int, GoldLocation] = {}
    location_errors: dict[int, str] = {}
    for atom, (span_start, span_end) in zip(atoms, surface_spans):
        candidates = [
            (segment_index, token_index, token)
            for segment_index, token_index, token in observed
            if span_start <= token.source_start and token.source_end <= span_end
        ]
        if len(candidates) != 1:
            reason = (
                "dcs_surface_placeholder_no_phonological_token"
                if not candidates else "dcs_surface_atom_contains_multiple_tokens"
            )
            location_errors.update((token_id, reason) for token_id in atom.ids)
            continue
        segment_index, token_index, token = candidates[0]
        for component_index, token_id in enumerate(atom.ids):
            locations[token_id] = GoldLocation(
                segment_index=segment_index,
                token_index=token_index,
                source_start=token.source_start,
                source_end=token.source_end,
                dcs_id=token_id,
                occ_id=occ_ids[token_id],
                component_index=component_index,
                component_count=len(atom.ids),
                method="dcs_multiword_range" if len(atom.ids) > 1 else "dcs_token_order",
            )
    return locations, occ_ids, location_errors, None


def fallback_unique_surface_location(
    match: dict[str, Any],
    segments: tuple[ObservedSegment, ...],
) -> tuple[GoldLocation | None, str | None]:
    """Legacy metadata-free fixture: exact, unique observed FORM only."""

    form = match.get("form")
    if not isinstance(form, str) or not form or form == "_":
        return None, "dcs_source_metadata_missing"
    candidates = [
        (segment_index, token_index, token)
        for segment_index, segment in enumerate(segments)
        for token_index, token in enumerate(segment.tokens)
        if normalize_iast(token.written) == normalize_iast(form)
    ]
    if len(candidates) != 1:
        return None, "surface_form_not_unique_without_dcs_structure"
    segment_index, token_index, token = candidates[0]
    return GoldLocation(
        segment_index=segment_index,
        token_index=token_index,
        source_start=token.source_start,
        source_end=token.source_end,
        dcs_id=None,
        occ_id=None,
        component_index=0,
        component_count=1,
        method="unique_observed_form_fallback",
    ), None


def top_factor_groups(
    segment: ObservedSegment,
    analysis: ComposedAnalysisPosterior,
) -> tuple[tuple[tuple[int, ...], ...] | None, str | None]:
    """Partition top lexical factors at validated visible source boundaries."""

    if len(analysis.boundaries) != len(analysis.words) - 1:
        return None, "top_boundary_word_count_mismatch"
    groups: list[tuple[int, ...]] = []
    start = 0
    for factor_index, boundary in enumerate(analysis.boundaries):
        if boundary.cue_kind != "space":
            continue
        boundary_index = len(groups)
        if boundary_index + 1 >= len(segment.tokens):
            return None, "top_visible_boundary_count_mismatch"
        left, right = segment.tokens[boundary_index : boundary_index + 2]
        if (
            boundary.source_start != left.source_end
            or boundary.source_end != right.source_start
        ):
            return None, "top_visible_boundary_span_mismatch"
        groups.append(tuple(range(start, factor_index + 1)))
        start = factor_index + 1
    groups.append(tuple(range(start, len(analysis.words))))
    if len(groups) != len(segment.tokens) or any(not group for group in groups):
        return None, "top_visible_boundary_count_mismatch"
    for token, group in zip(segment.tokens, groups):
        for factor_index in group[:-1]:
            boundary = analysis.boundaries[factor_index]
            if not (
                token.source_start
                <= boundary.source_start
                <= boundary.source_end
                <= token.source_end
            ):
                return None, "top_internal_boundary_span_mismatch"
    return tuple(groups), None

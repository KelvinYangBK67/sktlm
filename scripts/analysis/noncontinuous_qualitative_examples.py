#!/usr/bin/env python3
"""Select bounded, deterministic DEV surface-vs-legacy qualitative examples."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping


VISIBLE_WHITESPACE_RE = re.compile(r"\s+")


class SelectionError(RuntimeError):
    """Raised when an input violates the deterministic merge contract."""


class BoundedJsonlReader:
    def __init__(self, path: Path, *, max_records: int, max_bytes: int) -> None:
        self.path = path
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.records_read = 0
        self.bytes_read = 0
        self.stop_reason: str | None = None
        self._previous_segment_id: str | None = None
        self._handle: BinaryIO | None = None

    def __enter__(self) -> "BoundedJsonlReader":
        self._handle = self.path.open("rb")
        return self

    def __exit__(self, *_args: object) -> None:
        if self._handle is not None:
            self._handle.close()

    def read(self) -> dict[str, Any] | None:
        if self.stop_reason is not None:
            return None
        if self.records_read >= self.max_records:
            self.stop_reason = "max_records"
            return None
        remaining = self.max_bytes - self.bytes_read
        if remaining <= 0:
            self.stop_reason = "max_bytes"
            return None
        assert self._handle is not None
        raw = self._handle.readline(remaining + 1)
        if not raw:
            self.stop_reason = "eof"
            return None
        if len(raw) > remaining:
            self.stop_reason = "max_bytes"
            return None
        self.bytes_read += len(raw)
        self.records_read += 1
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SelectionError(
                f"invalid JSONL record {self.records_read} in {self.path}"
            ) from exc
        if not isinstance(record, dict):
            raise SelectionError(
                f"record {self.records_read} in {self.path} is not an object"
            )
        segment_id = record.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id:
            raise SelectionError(
                f"record {self.records_read} in {self.path} lacks segment_id"
            )
        if self._previous_segment_id is not None and segment_id <= self._previous_segment_id:
            raise SelectionError(
                f"segment_id order is not strictly increasing in {self.path}: "
                f"{segment_id!r} after {self._previous_segment_id!r}"
            )
        self._previous_segment_id = segment_id
        return record

    def stats(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "records_read": self.records_read,
            "bytes_read": self.bytes_read,
            "stop_reason": self.stop_reason,
        }


def visible_boundary_count(surface: str) -> int:
    return len(VISIBLE_WHITESPACE_RE.findall(surface.strip()))


def _top_analyses(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = record.get("top_analyses")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _latent_unit_count(analysis: Mapping[str, Any]) -> int:
    units = analysis.get("latent_units")
    return len(units) if isinstance(units, list) else 0


def _finite_number(value: Any, field: str, segment_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SelectionError(f"{field} is not numeric for {segment_id}")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise SelectionError(f"{field} is not finite for {segment_id}")
    return number


def _serialize_analysis(analysis: Mapping[str, Any]) -> dict[str, Any]:
    rule_ids = analysis.get("rule_ids")
    return {
        "posterior": analysis.get("posterior"),
        "analysis": analysis.get("debug_serialization"),
        "latent_unit_count": _latent_unit_count(analysis),
        "rule_ids": list(rule_ids) if isinstance(rule_ids, list) else [],
    }


def _side_payload(record: Mapping[str, Any], surface: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "identity_mass": record.get("identity_mass"),
        "latent_mass": record.get("latent_mass"),
        "entropy": record.get("entropy"),
        "top_analyses": [
            _serialize_analysis(row) for row in _top_analyses(record)[:3]
        ],
    }


def qualify_pair(
    surface_record: Mapping[str, Any],
    legacy_record: Mapping[str, Any],
    *,
    max_surface_chars: int,
    excluded_segment_ids: set[str],
) -> dict[str, Any] | None:
    segment_id = str(surface_record["segment_id"])
    if segment_id in excluded_segment_ids:
        return None
    surface_text = surface_record.get("surface")
    legacy_text = legacy_record.get("surface")
    if not isinstance(surface_text, str) or not isinstance(legacy_text, str):
        return None
    if surface_text == legacy_text or len(surface_text) > max_surface_chars:
        return None
    if visible_boundary_count(surface_text) <= visible_boundary_count(legacy_text):
        return None
    surface_top = _top_analyses(surface_record)
    legacy_top = _top_analyses(legacy_record)
    if not surface_top or not legacy_top:
        return None
    surface_unit_count = _latent_unit_count(surface_top[0])
    legacy_unit_count = _latent_unit_count(legacy_top[0])
    if legacy_unit_count >= surface_unit_count:
        return None
    surface_identity = _finite_number(
        surface_record.get("identity_mass"), "surface identity_mass", segment_id
    )
    legacy_identity = _finite_number(
        legacy_record.get("identity_mass"), "legacy identity_mass", segment_id
    )
    if legacy_identity <= surface_identity:
        return None
    return {
        "segment_id": segment_id,
        "document": surface_record.get("document"),
        "line_number": surface_record.get("line_number"),
        "identity_mass_delta": legacy_identity - surface_identity,
        "top1_latent_unit_reduction": surface_unit_count - legacy_unit_count,
        "surface_word": _side_payload(surface_record, surface_text),
        "legacy_joined": _side_payload(legacy_record, legacy_text),
    }


def select_examples(
    surface_path: Path,
    legacy_path: Path,
    *,
    select_count: int,
    max_records: int,
    max_bytes_per_input: int,
    stop_after_qualified: int,
    max_surface_chars: int,
    excluded_segment_ids: Iterable[str] = (),
) -> dict[str, Any]:
    if min(
        select_count,
        max_records,
        max_bytes_per_input,
        stop_after_qualified,
        max_surface_chars,
    ) <= 0:
        raise ValueError("all numeric bounds must be positive")
    if stop_after_qualified < select_count:
        raise ValueError("stop_after_qualified must be at least select_count")

    excluded = set(excluded_segment_ids)
    candidates: list[dict[str, Any]] = []
    seen_surface_pairs: set[tuple[str, str]] = set()
    matched_segments = 0
    stop_reason: str | None = None
    with BoundedJsonlReader(
        surface_path, max_records=max_records, max_bytes=max_bytes_per_input
    ) as surface_reader, BoundedJsonlReader(
        legacy_path, max_records=max_records, max_bytes=max_bytes_per_input
    ) as legacy_reader:
        surface_record = surface_reader.read()
        legacy_record = legacy_reader.read()
        while surface_record is not None and legacy_record is not None:
            surface_id = str(surface_record["segment_id"])
            legacy_id = str(legacy_record["segment_id"])
            if surface_id < legacy_id:
                surface_record = surface_reader.read()
                continue
            if legacy_id < surface_id:
                legacy_record = legacy_reader.read()
                continue
            matched_segments += 1
            candidate = qualify_pair(
                surface_record,
                legacy_record,
                max_surface_chars=max_surface_chars,
                excluded_segment_ids=excluded,
            )
            if candidate is not None:
                surface_pair = (
                    str(candidate["surface_word"]["surface"]),
                    str(candidate["legacy_joined"]["surface"]),
                )
                if surface_pair not in seen_surface_pairs:
                    seen_surface_pairs.add(surface_pair)
                    candidates.append(candidate)
                    if len(candidates) >= stop_after_qualified:
                        stop_reason = "qualified_limit"
                        break
            surface_record = surface_reader.read()
            legacy_record = legacy_reader.read()

        if stop_reason is None:
            stop_reason = (
                f"surface:{surface_reader.stop_reason or 'merge_exhausted'};"
                f"legacy:{legacy_reader.stop_reason or 'merge_exhausted'}"
            )
        surface_stats = surface_reader.stats()
        legacy_stats = legacy_reader.stats()

    candidates.sort(
        key=lambda row: (
            -float(row["identity_mass_delta"]),
            -int(row["top1_latent_unit_reduction"]),
            str(row["segment_id"]),
        )
    )
    selected = candidates[:select_count]
    for rank, row in enumerate(selected, start=1):
        row["selection_rank"] = rank

    return {
        "schema_version": 1,
        "method": {
            "join": "streaming merge-join by strictly increasing segment_id",
            "ranking": (
                "legacy identity_mass minus surface identity_mass DESC, "
                "top1 latent-unit reduction DESC, segment_id ASC"
            ),
            "select_count": select_count,
            "stop_after_qualified": stop_after_qualified,
            "max_records_per_input": max_records,
            "max_bytes_per_input": max_bytes_per_input,
            "max_surface_chars": max_surface_chars,
            "excluded_segment_ids": sorted(excluded),
            "deduplication": "first segment for each distinct surface-text pair",
        },
        "scan": {
            "stop_reason": stop_reason,
            "matched_segments": matched_segments,
            "qualified_candidates": len(candidates),
            "surface_word": surface_stats,
            "legacy_joined": legacy_stats,
        },
        "complete": len(selected) == select_count,
        "selected": selected,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-jsonl", required=True, type=Path)
    parser.add_argument("--legacy-jsonl", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--select-count", type=int, default=4)
    parser.add_argument("--max-records", type=int, default=50_000)
    parser.add_argument("--max-bytes-per-input", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--stop-after-qualified", type=int, default=64)
    parser.add_argument("--max-surface-chars", type=int, default=120)
    parser.add_argument("--exclude-segment-id", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = select_examples(
        args.surface_jsonl,
        args.legacy_jsonl,
        select_count=args.select_count,
        max_records=args.max_records,
        max_bytes_per_input=args.max_bytes_per_input,
        stop_after_qualified=args.stop_after_qualified,
        max_surface_chars=args.max_surface_chars,
        excluded_segment_ids=args.exclude_segment_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(
        json.dumps(
            {
                "complete": result["complete"],
                "qualified_candidates": result["scan"]["qualified_candidates"],
                "selected": len(result["selected"]),
                "stop_reason": result["scan"]["stop_reason"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
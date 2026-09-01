from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).parents[2]
    / "scripts/analysis/noncontinuous_qualitative_examples.py"
)
SPEC = importlib.util.spec_from_file_location(
    "noncontinuous_qualitative_examples_for_tests", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
selector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = selector
SPEC.loader.exec_module(selector)


def analysis(units: int, label: str, posterior: float = 0.8) -> dict[str, object]:
    return {
        "debug_serialization": label,
        "posterior": posterior,
        "rule_ids": ["EXT_0001"],
        "latent_units": [{"form_key": f"unit-{index}"} for index in range(units)],
    }


def record(
    segment_id: str,
    surface: str,
    identity_mass: float,
    units: int,
) -> dict[str, object]:
    return {
        "segment_id": segment_id,
        "document": "fixture.txt",
        "line_number": int(segment_id[-1]),
        "surface": surface,
        "identity_mass": identity_mass,
        "latent_mass": 1.0 - identity_mass,
        "entropy": 0.5,
        "top_analyses": [
            analysis(units, f"{segment_id}-top1"),
            analysis(units + 1, f"{segment_id}-top2", 0.1),
            analysis(units + 2, f"{segment_id}-top3", 0.05),
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_bounded_merge_selection_is_deterministic_and_applies_contract(
    tmp_path: Path,
) -> None:
    surface_path = tmp_path / "surface.jsonl"
    legacy_path = tmp_path / "legacy.jsonl"
    write_jsonl(
        surface_path,
        [
            record("segment-1", "अ ब क", 0.1, 4),
            record("segment-2", "ग घ ङ", 0.2, 4),
            record("segment-3", "च छ ज", 0.1, 5),
            record("segment-4", "same", 0.1, 3),
        ],
    )
    write_jsonl(
        legacy_path,
        [
            record("segment-1", "अब क", 0.9, 2),
            record("segment-2", "गघ ङ", 0.7, 3),
            record("segment-3", "चछ ज", 0.8, 3),
            record("segment-4", "same", 0.9, 1),
        ],
    )

    kwargs = {
        "select_count": 2,
        "max_records": 20,
        "max_bytes_per_input": 100_000,
        "stop_after_qualified": 2,
        "max_surface_chars": 120,
        "excluded_segment_ids": {"segment-1"},
    }
    first = selector.select_examples(surface_path, legacy_path, **kwargs)
    second = selector.select_examples(surface_path, legacy_path, **kwargs)

    assert first == second
    assert first["complete"] is True
    assert first["scan"]["stop_reason"] == "qualified_limit"
    assert [row["segment_id"] for row in first["selected"]] == [
        "segment-3",
        "segment-2",
    ]
    assert first["selected"][0]["surface_word"]["top_analyses"][0] == {
        "posterior": 0.8,
        "analysis": "segment-3-top1",
        "latent_unit_count": 5,
        "rule_ids": ["EXT_0001"],
    }


def test_selector_keeps_distinct_surface_pairs(tmp_path: Path) -> None:
    surface_path = tmp_path / "surface.jsonl"
    legacy_path = tmp_path / "legacy.jsonl"
    write_jsonl(
        surface_path,
        [
            record("segment-1", "अ ब", 0.1, 3),
            record("segment-2", "अ ब", 0.05, 4),
            record("segment-3", "क ख", 0.2, 3),
        ],
    )
    write_jsonl(
        legacy_path,
        [
            record("segment-1", "अब", 0.8, 2),
            record("segment-2", "अब", 0.99, 1),
            record("segment-3", "कख", 0.7, 2),
        ],
    )

    result = selector.select_examples(
        surface_path,
        legacy_path,
        select_count=2,
        max_records=10,
        max_bytes_per_input=100_000,
        stop_after_qualified=2,
        max_surface_chars=120,
    )

    assert result["complete"] is True
    assert result["scan"]["qualified_candidates"] == 2
    assert {row["segment_id"] for row in result["selected"]} == {
        "segment-1",
        "segment-3",
    }

def test_selector_reports_a_bounded_incomplete_scan(tmp_path: Path) -> None:
    surface_path = tmp_path / "surface.jsonl"
    legacy_path = tmp_path / "legacy.jsonl"
    write_jsonl(surface_path, [record("segment-1", "अ ब", 0.1, 3)])
    write_jsonl(legacy_path, [record("segment-1", "अब", 0.9, 2)])

    result = selector.select_examples(
        surface_path,
        legacy_path,
        select_count=2,
        max_records=1,
        max_bytes_per_input=100_000,
        stop_after_qualified=2,
        max_surface_chars=120,
    )

    assert result["complete"] is False
    assert len(result["selected"]) == 1
    assert "max_records" in result["scan"]["stop_reason"]
    assert result["scan"]["surface_word"]["records_read"] == 1


def test_selector_rejects_non_monotonic_segment_ids(tmp_path: Path) -> None:
    surface_path = tmp_path / "surface.jsonl"
    legacy_path = tmp_path / "legacy.jsonl"
    write_jsonl(
        surface_path,
        [
            record("segment-2", "अ ब", 0.1, 3),
            record("segment-1", "क ख", 0.1, 3),
        ],
    )
    write_jsonl(
        legacy_path,
        [
            record("segment-2", "अब", 0.9, 2),
            record("segment-3", "कख", 0.9, 2),
        ],
    )

    with pytest.raises(selector.SelectionError, match="strictly increasing"):
        selector.select_examples(
            surface_path,
            legacy_path,
            select_count=2,
            max_records=10,
            max_bytes_per_input=100_000,
            stop_after_qualified=2,
            max_surface_chars=120,
        )
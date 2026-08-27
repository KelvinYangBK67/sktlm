"""Tests that text identity and splits are fixed before representation/tokenization."""

import csv

from sktlm.data.dataset import (
    assert_same_segment_ids,
    load_canonical_segments,
    represent_segments,
    segment_ids_by_split,
)
from sktlm.data.representations.script import RepresentationConfig


def build_manifest(tmp_path):
    rows = []
    for split, text in (
        ("train", "devaś ca\nrāmaś ca"),
        ("dev", "sītā paṭhati"),
        ("test", "bālaḥ gacchati"),
    ):
        corpus_path = tmp_path / f"{split}.txt"
        corpus_path.write_text(text, encoding="utf-8")
        rows.append(
            {
                "path": str(corpus_path),
                "canonical_path": str(corpus_path),
                "canonical_script": "iast",
                "source": "fixture",
                "layer": "test",
                "document_id": f"doc_{split}",
                "split": split,
            }
        )
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def test_manifest_segments_keep_preassigned_splits(tmp_path) -> None:
    segments = load_canonical_segments(build_manifest(tmp_path))
    grouped = segment_ids_by_split(segments)
    assert {name: len(ids) for name, ids in grouped.items()} == {"train": 2, "dev": 1, "test": 1}


def test_same_split_segment_ids_across_all_conditions(tmp_path) -> None:
    canonical = load_canonical_segments(build_manifest(tmp_path))
    conditions = [
        RepresentationConfig("iast", "observed"),
        RepresentationConfig("iast", "continuous"),
        RepresentationConfig("devanagari", "observed"),
        RepresentationConfig("devanagari", "continuous"),
        RepresentationConfig("devanagari", "legacy_joined"),
    ]
    represented = [represent_segments(canonical, condition) for condition in conditions]
    for condition_segments in represented:
        assert_same_segment_ids(canonical, condition_segments)
        assert segment_ids_by_split(condition_segments) == segment_ids_by_split(canonical)

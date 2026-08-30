from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.residual import Hit
from sktlm.corpus.gretil.cleaning.triage import (
    FAMILY_APPARATUS_EDITORIAL,
    MECHANICAL_STRUCTURAL,
    MIXED_LANGUAGE_SERIOUS_ANOMALY,
    SOURCE_SPECIFIC_CONTAMINATION,
    build_triage,
    classify_hit,
    source_family,
)


def make_hit(path: str, category: str) -> Hit:
    return Hit(path, category, "x", "U+0078", 1, 1, "x")


def test_classification_is_exclusive_and_precedence_is_conservative() -> None:
    source_path = "2_epic/mbh/ext/hv_apppu.txt"
    assert classify_hit(make_hit(source_path, "NON_IAST_LATIN")) == MIXED_LANGUAGE_SERIOUS_ANOMALY
    assert classify_hit(make_hit(source_path, "ANGLE")) == MECHANICAL_STRUCTURAL
    assert classify_hit(make_hit(source_path, "DIGIT")) == SOURCE_SPECIFIC_CONTAMINATION
    assert classify_hit(make_hit("1_veda/text.txt", "DIGIT")) == FAMILY_APPARATUS_EDITORIAL


def test_source_family_groups_explicit_hv_family() -> None:
    assert source_family("2_epic/mbh/ext/hv_apppu.txt") == "2_epic/mbh/ext/hv"
    assert source_family("4_rellit/buddh/example.txt") == "4_rellit/buddh"


def test_build_triage_writes_deterministic_reports(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    report_dir = tmp_path / "reports"
    (input_root / "2_epic/mbh/ext").mkdir(parents=True)
    (input_root / "1_veda").mkdir(parents=True)
    (input_root / "2_epic/mbh/ext/hv_test.txt").write_text("a1q<", encoding="utf-8")
    (input_root / "1_veda/plain.txt").write_text("a,", encoding="utf-8")

    result = build_triage(input_root=input_root, report_dir=report_dir)

    assert result.files_processed == 2
    assert result.flagged_files == 2
    assert result.flagged_occurrences == 4
    assert result.families == 2

    with (report_dir / "residual_triage_files.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    hv = next(row for row in rows if row["path"].endswith("hv_test.txt"))
    assert int(hv[SOURCE_SPECIFIC_CONTAMINATION]) == 1
    assert int(hv[MIXED_LANGUAGE_SERIOUS_ANOMALY]) == 1
    assert int(hv[MECHANICAL_STRUCTURAL]) == 1

    summary = (report_dir / "residual_triage_summary.txt").read_text(encoding="utf-8")
    assert "strict flagged_files=0 is not a cleanup objective" in summary
    assert "The triaged corpus was not modified." in summary

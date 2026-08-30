from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.source_specific.vakobhau import (
    TARGET_PATH,
    build_cleanup,
    clean_document,
    clean_line,
)


def test_removes_only_exact_standalone_locator() -> None:
    assert clean_line("[001|03-001|07]", path=TARGET_PATH) == ("", True)
    assert clean_line("[004|23]", path=TARGET_PATH) == ("", True)
    assert clean_line(" [004|23]", path=TARGET_PATH) == (" [004|23]", False)
    assert clean_line("[010|12=01012]", path=TARGET_PATH) == ("[010|12=01012]", False)
    assert clean_line("text [004|23]", path=TARGET_PATH) == ("text [004|23]", False)
    assert clean_line("[004|23]", path="other.txt") == ("[004|23]", False)


def test_document_preserves_layout_and_nonmatching_editorial_text() -> None:
    text = "praj\u00f1\u0101 'mal\u0101 (1-2a)\n\n[002|04]\n\n[bad locator]\n"
    output, changes = clean_document(text, path=TARGET_PATH)
    assert output == "praj\u00f1\u0101 'mal\u0101 (1-2a)\n\n\n\n[bad locator]\n"
    assert changes == [(3, "[002|04]")]


def test_builder_emits_positive_match_audit(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"
    target = input_root / TARGET_PATH
    other = input_root / "1_veda/other.txt"
    target.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    target.write_text("text\n[001|03-001|07]\n[bad]\n", encoding="utf-8", newline="")
    other.write_text("[001|03]\n", encoding="utf-8", newline="")
    other_bytes = other.read_bytes()

    result = build_cleanup(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 2
    assert result.files_changed == 1
    assert result.locator_lines_removed == 1
    assert (output_root / "1_veda/other.txt").read_bytes() == other_bytes
    assert "[bad]" in (output_root / TARGET_PATH).read_text(encoding="utf-8")

    with (report_dir / "vakobhau_cleanup_occurrences.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["removed"] == "[001|03-001|07]"
    summary = (report_dir / "vakobhau_cleanup_summary.txt").read_text(encoding="utf-8")
    assert "malformed locator-like lines" in summary
    assert "The input corpus was not modified." in summary

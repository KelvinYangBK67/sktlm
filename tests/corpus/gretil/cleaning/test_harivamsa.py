from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sktlm.corpus.gretil.cleaning.source_specific.harivamsa import (
    APPENDIX_PATH,
    CRITICAL_PATH,
    build_cleanup,
    clean_document,
    clean_line,
)


def test_removes_only_complete_supported_line_final_locators() -> None:
    appendix = "devo gacchati || HV App.I,1.1 ||"
    critical = "devo gacchati | *HV 1.0*1:1 |"
    assert clean_line(appendix, path=APPENDIX_PATH)[0] == "devo gacchati ||"
    assert clean_line(critical, path=CRITICAL_PATH)[0] == "devo gacchati |"


def test_leaves_wrong_scope_embedded_and_unapproved_marker_styles_untouched() -> None:
    line = "devo gacchati || HV App.I,1.1 ||"
    assert clean_line(line, path="2_epic/mbh/other.txt")[0] == line
    embedded = "HV App.I,1.1 appears inside Sanskrit text"
    assert clean_line(embedded, path=APPENDIX_PATH)[0] == embedded
    bold = "devo gacchati @ **HV App.I,1.1**1:1 @"
    assert clean_line(bold, path=APPENDIX_PATH)[0] == bold


def test_document_preserves_speaker_and_variant_material() -> None:
    text = (
        "{s\u016bta uv\u0101ca}\n"
        "putr\u0101(\u015b c\u0101)[vai c\u0101]k\u1e63u\u1e63\u0101 | *HV 7.46ab*137:1 |\n"
    )
    output, changes = clean_document(text, path=CRITICAL_PATH)
    assert output == "{s\u016bta uv\u0101ca}\nputr\u0101(\u015b c\u0101)[vai c\u0101]k\u1e63u\u1e63\u0101 |\n"
    assert len(changes) == 1


def test_builder_copies_non_target_and_emits_audit(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"
    appendix = input_root / APPENDIX_PATH
    critical = input_root / CRITICAL_PATH
    other = input_root / "1_veda/other.txt"
    for path in (appendix, critical, other):
        path.parent.mkdir(parents=True, exist_ok=True)
    appendix.write_text("a\u1e25 || HV App.I,1.1 ||\n", encoding="utf-8", newline="")
    critical.write_text("bhi\u1e25 | *HV 1.0*1:1 |\n", encoding="utf-8", newline="")
    other.write_text("unchanged [1]\n", encoding="utf-8", newline="")
    original_other = other.read_bytes()

    result = build_cleanup(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 3
    assert result.files_changed == 2
    assert result.occurrences_removed == 2
    assert (output_root / "1_veda/other.txt").read_bytes() == original_other
    assert other.read_bytes() == original_other

    with (report_dir / "harivamsa_cleanup_occurrences.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert {row["path"] for row in rows} == {APPENDIX_PATH, CRITICAL_PATH}
    summary = (report_dir / "harivamsa_cleanup_summary.txt").read_text(encoding="utf-8")
    assert "variants, speaker labels, brackets" in summary
    assert "The input corpus was not modified." in summary


def test_builder_refuses_existing_output(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    output_root.mkdir()
    with pytest.raises(FileExistsError):
        build_cleanup(
            input_root=input_root,
            output_root=output_root,
            report_dir=tmp_path / "reports",
            require_all_targets=False,
        )

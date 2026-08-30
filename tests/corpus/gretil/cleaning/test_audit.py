"""Tests for the read-only formal GRETIL canonical IAST anomaly audit."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.audit import (
    FLAG_TYPES,
    audit_corpus,
    classify_character,
    scan_file,
    write_reports,
)


def _write_canonical(
    path: Path,
    text: str,
) -> None:
    """Write a canonical fixture exactly as the formal builder writes output."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(
        text.encode("utf-8")
    )


def test_plain_lowercase_sanskrit_iast_is_allowed() -> None:
    text = (
        "vṛttaṃ samam ardhasamaṃ viṣamaṃ ca |\n"
        "devo'pi rāmaḥ gacchati ||\n"
        "ḷ ḹ ṛ ṝ ś ṣ ṭ ḍ ṇ ñ ṅ ṃ ḥ\n"
    )

    assert all(
        classify_character(character) is None
        for character in text
    )


def test_source_accents_are_allowed() -> None:
    # Precomposed acute vowel retained by the formal builder.
    assert classify_character("á") is None

    # Combining acute and grave marks retained by the formal builder.
    assert classify_character("\u0301") is None
    assert classify_character("\u0300") is None


def test_uppercase_is_flagged() -> None:
    for character in "AJVĀṚŚ":
        assert classify_character(character) == "UPPERCASE"


def test_non_iast_ascii_letters_are_flagged() -> None:
    for character in "qwfzx":
        assert (
            classify_character(character)
            == "NON_IAST_LATIN"
        )


def test_other_lowercase_latin_letters_are_flagged() -> None:
    assert (
        classify_character("ü")
        == "NON_IAST_LATIN"
    )


def test_brackets_are_flagged() -> None:
    assert (
        classify_character("<")
        == "ANGLE_BRACKET"
    )

    assert (
        classify_character(">")
        == "ANGLE_BRACKET"
    )

    assert (
        classify_character("[")
        == "SQUARE_BRACKET"
    )

    assert (
        classify_character("]")
        == "SQUARE_BRACKET"
    )

    assert (
        classify_character("{")
        == "CURLY_BRACKET"
    )

    assert (
        classify_character("}")
        == "CURLY_BRACKET"
    )

    assert (
        classify_character("(")
        == "ROUND_BRACKET"
    )

    assert (
        classify_character(")")
        == "ROUND_BRACKET"
    )


def test_dot_and_comma_are_flagged() -> None:
    assert classify_character(".") == "DOT"
    assert classify_character(",") == "COMMA"


def test_digits_are_flagged() -> None:
    assert classify_character("0") == "DIGIT"
    assert classify_character("7") == "DIGIT"

    # Unicode digits should also be surfaced.
    assert classify_character("३") == "DIGIT"


def test_underscore_is_flagged() -> None:
    assert classify_character("_") == "UNDERSCORE"


def test_hyphen_family_is_flagged() -> None:
    for character in "-‐-–—−":
        assert classify_character(character) == "HYPHEN"


def test_control_and_format_characters_are_flagged() -> None:
    assert (
        classify_character("\u0001")
        == "CONTROL_OR_FORMAT"
    )

    assert (
        classify_character("\u0015")
        == "CONTROL_OR_FORMAT"
    )

    assert (
        classify_character("\u007f")
        == "CONTROL_OR_FORMAT"
    )

    assert (
        classify_character("\u200d")
        == "CONTROL_OR_FORMAT"
    )

    assert (
        classify_character("\t")
        == "CONTROL_OR_FORMAT"
    )

    assert (
        classify_character("\r")
        == "CONTROL_OR_FORMAT"
    )


def test_other_noncanonical_punctuation_is_flagged() -> None:
    assert (
        classify_character(":")
        == "OTHER_NONCANONICAL"
    )

    assert (
        classify_character(";")
        == "OTHER_NONCANONICAL"
    )

    assert (
        classify_character('"')
        == "OTHER_NONCANONICAL"
    )


def test_known_jvrtms_style_residue_is_detected(
    tmp_path: Path,
) -> None:
    canonical_root = tmp_path / "gretil_iast"

    path = (
        canonical_root
        / "5_poetry"
        / "1_chandas"
        / "jvrtmspu.txt"
    )

    original = (
        "trividhaṃ parārthavidhaye samāsato "
        "vyāsato 'nantam || JVms_1 ||\n"
        "dhī-gī[ḥ]- |\n"
    )

    _write_canonical(
        path,
        original,
    )

    (
        character_counts,
        flag_counts,
        flagged_lines,
    ) = scan_file(
        path,
        canonical_root,
    )

    assert character_counts["J"] == 1

    assert flag_counts["UPPERCASE"] > 0
    assert flag_counts["DIGIT"] > 0
    assert flag_counts["UNDERSCORE"] > 0
    assert flag_counts["SQUARE_BRACKET"] > 0
    assert flag_counts["HYPHEN"] > 0

    assert flagged_lines

    # Read-only invariant.
    assert (
        path.read_bytes().decode("utf-8")
        == original
    )


def test_line_level_grouping_does_not_emit_one_row_per_character(
    tmp_path: Path,
) -> None:
    canonical_root = tmp_path / "gretil_iast"

    path = canonical_root / "example.txt"

    _write_canonical(
        path,
        "JVMS_123 ||\n",
    )

    _, _, flagged_lines = scan_file(
        path,
        canonical_root,
    )

    uppercase_rows = [
        row
        for row in flagged_lines
        if row.flag_type == "UPPERCASE"
    ]

    digit_rows = [
        row
        for row in flagged_lines
        if row.flag_type == "DIGIT"
    ]

    assert len(uppercase_rows) == 1
    assert uppercase_rows[0].count == 4

    assert len(digit_rows) == 1
    assert digit_rows[0].count == 3


def test_control_characters_are_rendered_safely_in_context(
    tmp_path: Path,
) -> None:
    canonical_root = tmp_path / "gretil_iast"

    path = canonical_root / "control.txt"

    _write_canonical(
        path,
        "bharadvāja\u0015 uvāca |\n",
    )

    _, counts, flagged_lines = scan_file(
        path,
        canonical_root,
    )

    assert counts["CONTROL_OR_FORMAT"] == 1

    control_rows = [
        row
        for row in flagged_lines
        if row.flag_type == "CONTROL_OR_FORMAT"
    ]

    assert len(control_rows) == 1

    assert (
        "<U+0015>"
        in control_rows[0].line_text
    )


def test_crlf_is_flagged_as_control_or_format(
    tmp_path: Path,
) -> None:
    canonical_root = tmp_path / "gretil_iast"

    path = canonical_root / "crlf.txt"

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(
        b"rama\r\n"
    )

    _, counts, flagged_lines = scan_file(
        path,
        canonical_root,
    )

    assert counts["CONTROL_OR_FORMAT"] == 1

    control_rows = [
        row
        for row in flagged_lines
        if row.flag_type == "CONTROL_OR_FORMAT"
    ]

    assert len(control_rows) == 1
    assert "<CR>" in control_rows[0].line_text


def test_audit_recurses_through_preserved_directory_structure(
    tmp_path: Path,
) -> None:
    canonical_root = tmp_path / "gretil_iast"

    first = (
        canonical_root
        / "2_epic"
        / "mbh"
        / "mbh_01_u.txt"
    )

    second = (
        canonical_root
        / "5_poetry"
        / "1_chandas"
        / "jvrtmspu.txt"
    )

    _write_canonical(
        first,
        "rāmaḥ gacchati ||\n",
    )

    _write_canonical(
        second,
        "JVms_1 ||\n",
    )

    audit = audit_corpus(
        canonical_root,
    )

    assert len(audit.files) == 2

    paths = {
        str(row["path"])
        for row in audit.file_rows
    }

    assert (
        "2_epic/mbh/mbh_01_u.txt"
        in paths
    )

    assert (
        "5_poetry/1_chandas/jvrtmspu.txt"
        in paths
    )


def test_reports_are_written_without_modifying_corpus(
    tmp_path: Path,
) -> None:
    canonical_root = tmp_path / "gretil_iast"
    report_dir = tmp_path / "reports"

    clean_path = canonical_root / "clean.txt"
    dirty_path = canonical_root / "dirty.txt"

    clean_text = "rāmaḥ gacchati ||\n"
    dirty_text = "JVms_1 dhī-gī[ḥ]- |\n"

    _write_canonical(
        clean_path,
        clean_text,
    )

    _write_canonical(
        dirty_path,
        dirty_text,
    )

    before_clean = clean_path.read_bytes()
    before_dirty = dirty_path.read_bytes()

    audit = audit_corpus(
        canonical_root,
    )

    write_reports(
        audit,
        canonical_root=canonical_root,
        report_dir=report_dir,
    )

    expected = {
        "gretil_canonical_anomaly_summary.txt",
        "gretil_canonical_character_inventory.csv",
        "gretil_canonical_flagged_files.csv",
        "gretil_canonical_flagged_occurrences.csv",
    }

    assert {
        path.name
        for path in report_dir.iterdir()
    } == expected

    assert clean_path.read_bytes() == before_clean
    assert dirty_path.read_bytes() == before_dirty


def test_flagged_files_report_contains_only_flagged_documents(
    tmp_path: Path,
) -> None:
    canonical_root = tmp_path / "gretil_iast"
    report_dir = tmp_path / "reports"

    _write_canonical(
        canonical_root / "clean.txt",
        "rāmaḥ gacchati ||\n",
    )

    _write_canonical(
        canonical_root / "dirty.txt",
        "JVms_1 ||\n",
    )

    audit = audit_corpus(
        canonical_root,
    )

    write_reports(
        audit,
        canonical_root=canonical_root,
        report_dir=report_dir,
    )

    flagged_path = (
        report_dir
        / "gretil_canonical_flagged_files.csv"
    )

    with flagged_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert len(rows) == 1
    assert rows[0]["path"] == "dirty.txt"
    assert int(rows[0]["total_flags"]) > 0

    for flag_type in FLAG_TYPES:
        assert flag_type in rows[0]

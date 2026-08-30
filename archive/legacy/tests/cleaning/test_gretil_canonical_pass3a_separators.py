"""Tests for Pass 3A source-separator normalization."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.data.gretil_canonical_pass3a_separators import (
    build_pass3a_candidate,
    classify_separator,
    normalize_document,
    normalize_line,
)


DOT_FILE = "1_veda/2_bra/kausibru.txt"
NON_TARGET = "5_poetry/example.txt"


def _write(
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_bytes(
        text.encode("utf-8")
    )


def test_dot_between_lexical_material_becomes_space() -> None:
    result = normalize_document(
        "asmin.vai.loka.ubhaye |\n",
        DOT_FILE,
    )

    assert result.text == (
        "asmin vai loka ubhaye |\n"
    )
    assert len(result.auto) == 3
    assert not result.review


def test_dot_boundary_does_not_claim_linguistic_repair() -> None:
    result = normalize_document(
        "viris.yate dakṣ.iṇāgniṃ |\n",
        DOT_FILE,
    )

    assert result.text == (
        "viris yate dakṣ iṇāgniṃ |\n"
    )
    assert len(result.auto) == 2


def test_dot_around_danda_becomes_space() -> None:
    result = normalize_document(
        "yājyā.|.viśve.devāḥ |\n",
        DOT_FILE,
    )

    assert result.text == (
        "yājyā | viśve devāḥ |\n"
    )
    assert len(result.auto) == 3


def test_numeric_dot_is_ignored() -> None:
    original = "1.2.3 iti |\n"

    result = normalize_document(
        original,
        DOT_FILE,
    )

    assert result.text == original
    assert not result.auto


def test_dot_inside_parentheses_is_ignored() -> None:
    original = (
        "agnim.na.svavṛktibhir "
        "(soma: sāvitra.graha.etc.) |\n"
    )

    result = normalize_document(
        original,
        DOT_FILE,
    )

    assert result.text == (
        "agnim na svavṛktibhir "
        "(soma: sāvitra.graha.etc.) |\n"
    )

    assert len(result.auto) == 2


def test_dot_inside_square_brackets_is_ignored() -> None:
    original = "agnim.na [ed. foo.bar] |\n"

    result = normalize_document(
        original,
        DOT_FILE,
    )

    assert result.text == (
        "agnim na [ed. foo.bar] |\n"
    )
    assert len(result.auto) == 1


def test_non_target_file_is_byte_semantically_untouched() -> None:
    original = "asmin.vai.loka kule-kule |\n"

    result = normalize_document(
        original,
        NON_TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert not result.review


def test_repeated_dot_is_not_auto() -> None:
    line = "agnim..indraṃ"

    cleaned, auto, review, ignored = normalize_line(
        line,
        path=DOT_FILE,
        line_number=1,
        dot_enabled=True,
        hyphen_enabled=False,
    )

    assert cleaned == line
    assert not auto
    assert not review
    assert sum(ignored.values()) == 2


def test_hyphen_engine_is_ready_when_enabled() -> None:
    line = "kule-kule anyo-'nyaḥ"

    cleaned, auto, review, ignored = normalize_line(
        line,
        path="synthetic.txt",
        line_number=1,
        dot_enabled=False,
        hyphen_enabled=True,
    )

    assert cleaned == "kule kule anyo 'nyaḥ"
    assert len(auto) == 2
    assert not review
    assert not ignored


def test_hyphen_numeric_range_is_ignored() -> None:
    line = "1901-1905"

    cleaned, auto, review, ignored = normalize_line(
        line,
        path="synthetic.txt",
        line_number=1,
        dot_enabled=False,
        hyphen_enabled=True,
    )

    assert cleaned == line
    assert not auto
    assert not review
    assert sum(ignored.values()) == 1


def test_classifier_requires_enabled_file_mode() -> None:
    line = "deva.rāja"
    index = line.index(".")

    result = classify_separator(
        line,
        index,
        separator=".",
        enabled=False,
    )

    assert result.decision == "IGNORE"
    assert (
        result.reason
        == "separator_not_enabled_for_file"
    )


def test_corpus_builder_preserves_non_targets_byte_identically(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    target = input_root / DOT_FILE
    non_target = input_root / NON_TARGET

    _write(
        target,
        "asmin.vai.loka |\n",
    )
    _write(
        non_target,
        "foo.bar kule-kule |\n",
    )

    non_target_before = non_target.read_bytes()

    result = build_pass3a_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 2
    assert result.target_files == 1
    assert result.files_changed == 1
    assert result.auto_dot == 2

    assert (
        output_root / DOT_FILE
    ).read_text(
        encoding="utf-8"
    ) == "asmin vai loka |\n"

    assert (
        output_root / NON_TARGET
    ).read_bytes() == non_target_before


def test_reports_are_written(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / DOT_FILE,
        "asmin.vai 1.2.3 foo. |\n",
    )

    build_pass3a_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    summary = (
        report_dir
        / "gretil_pass3a_separator_summary.txt"
    )
    file_audit = (
        report_dir
        / "gretil_pass3a_separator_file_audit.csv"
    )
    auto_file = (
        report_dir
        / "gretil_pass3a_separator_auto.csv"
    )
    review_file = (
        report_dir
        / "gretil_pass3a_separator_review.csv"
    )

    assert summary.is_file()
    assert file_audit.is_file()
    assert auto_file.is_file()
    assert review_file.is_file()

    with file_audit.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["path"] == DOT_FILE
    assert int(rows[0]["auto_dot"]) == 1

    with review_file.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        review_rows = list(
            csv.DictReader(handle)
        )

    assert any(
        row["reason"] == "adjacent_whitespace"
        for row in review_rows
    )

"""Tests for the GRETIL pluta document filter."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.pluta_filter import (
    find_pluta_occurrences,
    filter_pluta_documents,
)


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


def test_plain_pluta_is_detected() -> None:
    occurrences = find_pluta_occurrences(
        "utsṛjyā3ṃ notsṛjyā3m iti |\n",
        "example.txt",
    )

    assert len(occurrences) == 2

    assert {
        occurrence.match
        for occurrence in occurrences
    } == {"ā3"}


def test_o3m_is_detected() -> None:
    occurrences = find_pluta_occurrences(
        "o3m ity ācāryāḥ |\n",
        "example.txt",
    )

    assert len(occurrences) == 1
    assert occurrences[0].match == "o3"


def test_pluta_before_consonant_is_detected() -> None:
    occurrences = find_pluta_occurrences(
        "parā3ṅ arvā3ṅ ity āhuḥ |\n",
        "example.txt",
    )

    assert len(occurrences) == 2


def test_structural_numbers_are_not_pluta() -> None:
    text = (
        "1.2.3.\n"
        "||31||\n"
        "(18.15)\n"
        "HV App.I,3.14\n"
        "3050101athāto vapānāṃ homaḥ\n"
    )

    occurrences = find_pluta_occurrences(
        text,
        "example.txt",
    )

    assert occurrences == []


def test_pluta_document_is_excluded(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / "pluta.txt",
        "ayaṃ nū3 nā3 iti |\n",
    )

    _write(
        input_root / "clean.txt",
        "rāmaḥ gacchati |\n",
    )

    result = filter_pluta_documents(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_scanned == 2
    assert result.files_excluded == 1
    assert result.files_kept == 1

    assert not (
        output_root
        / "pluta.txt"
    ).exists()

    assert (
        output_root
        / "clean.txt"
    ).is_file()


def test_retained_file_is_byte_identical(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    source = (
        input_root
        / "nested"
        / "clean.txt"
    )

    original = (
        "rāmaḥ gacchati ||\n"
        "devo'pi tatra |\n"
    )

    _write(
        source,
        original,
    )

    before = source.read_bytes()

    filter_pluta_documents(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    destination = (
        output_root
        / "nested"
        / "clean.txt"
    )

    assert destination.read_bytes() == before
    assert source.read_bytes() == before


def test_reports_are_written(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / "pluta.txt",
        "ekā3 dvā3 u trayā3 iti |\n",
    )

    filter_pluta_documents(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    summary = (
        report_dir
        / "gretil_pluta_filter_summary.txt"
    )

    excluded = (
        report_dir
        / "gretil_pluta_excluded_files.csv"
    )

    occurrences = (
        report_dir
        / "gretil_pluta_occurrences.csv"
    )

    assert summary.is_file()
    assert excluded.is_file()
    assert occurrences.is_file()

    with excluded.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert len(rows) == 1
    assert rows[0]["path"] == "pluta.txt"
    assert int(
        rows[0]["pluta_occurrences"]
    ) == 3


def test_input_is_never_modified(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    source = input_root / "pluta.txt"

    _write(
        source,
        "nā3 iti |\n",
    )

    before = source.read_bytes()

    filter_pluta_documents(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert source.read_bytes() == before

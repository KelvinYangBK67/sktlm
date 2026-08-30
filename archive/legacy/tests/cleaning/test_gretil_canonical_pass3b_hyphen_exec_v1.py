"""Tests for Pass 3B hyphen normalization executor."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.data.gretil_canonical_pass3b_hyphen_exec_v1 import (
    HYPHEN_BOUNDARY_FILES,
    IMPLEMENTATION,
    build_pass3b_candidate,
    normalize_document,
    normalize_line,
)


TARGET = "5_poetry/2_kavya/bhattiku.txt"
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


def test_signature_and_whitelist_size() -> None:
    assert (
        IMPLEMENTATION
        == "hyphen-executor-v1"
    )
    assert len(
        HYPHEN_BOUNDARY_FILES
    ) == 32


def test_lexical_separator_becomes_space() -> None:
    result = normalize_document(
        "kule-kule pañca-pañca |\n",
        TARGET,
    )

    assert result.text == (
        "kule kule pañca pañca |\n"
    )
    assert len(result.auto) == 2
    assert not result.review
    assert not result.non_separator


def test_avagraha_separator_becomes_space() -> None:
    result = normalize_document(
        "anyo-'nyaḥ adho-'dho |\n",
        TARGET,
    )

    assert result.text == (
        "anyo 'nyaḥ adho 'dho |\n"
    )
    assert len(result.auto) == 2


def test_numeric_range_is_preserved() -> None:
    original = "1901-1905 |\n"

    result = normalize_document(
        original,
        TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert len(
        result.non_separator
    ) == 1


def test_double_hyphen_is_preserved() -> None:
    original = "foo--bar |\n"

    result = normalize_document(
        original,
        TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert len(
        result.non_separator
    ) == 2


def test_hyphen_inside_protected_span_is_preserved() -> None:
    original = (
        "deva (foo-bar) gacchati |\n"
    )

    result = normalize_document(
        original,
        TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert len(
        result.non_separator
    ) == 1


def test_adjacent_whitespace_is_review_only() -> None:
    original = "foo - bar |\n"

    result = normalize_document(
        original,
        TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert len(result.review) == 1


def test_non_target_document_is_untouched() -> None:
    original = (
        "kule-kule anyo-'nyaḥ |\n"
    )

    result = normalize_document(
        original,
        NON_TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert not result.review
    assert not result.non_separator


def test_normalize_line_mixed_decisions() -> None:
    (
        cleaned,
        auto,
        review,
        non_separator,
    ) = normalize_line(
        "kule-kule 1901-1905 foo - bar",
        path=TARGET,
        line_number=1,
    )

    assert cleaned == (
        "kule kule 1901-1905 foo - bar"
    )
    assert len(auto) == 1
    assert len(review) == 1
    assert len(non_separator) == 1


def test_corpus_builder_preserves_non_targets_byte_identically(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / TARGET,
        "kule-kule 1901-1905 |\n",
    )
    _write(
        input_root / NON_TARGET,
        "foo-bar |\n",
    )

    non_target_before = (
        input_root / NON_TARGET
    ).read_bytes()

    result = build_pass3b_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 2
    assert result.present_whitelist_files == 1
    assert result.auto_replacements == 1

    assert (
        output_root / TARGET
    ).read_text(
        encoding="utf-8"
    ) == (
        "kule kule 1901-1905 |\n"
    )

    assert (
        output_root / NON_TARGET
    ).read_bytes() == (
        non_target_before
    )


def test_reports_are_written(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / TARGET,
        "kule-kule foo - bar 1901-1905 |\n",
    )

    build_pass3b_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    summary = (
        report_dir
        / "gretil_pass3b_hyphen_summary.txt"
    )
    audit = (
        report_dir
        / "gretil_pass3b_hyphen_file_audit.csv"
    )
    auto_file = (
        report_dir
        / "gretil_pass3b_hyphen_auto.csv"
    )
    review_file = (
        report_dir
        / "gretil_pass3b_hyphen_review.csv"
    )
    nonseparator_file = (
        report_dir
        / "gretil_pass3b_hyphen_nonseparator.csv"
    )

    assert summary.is_file()
    assert audit.is_file()
    assert auto_file.is_file()
    assert review_file.is_file()
    assert nonseparator_file.is_file()

    with audit.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert len(rows) == 1
    assert rows[0]["path"] == TARGET
    assert int(rows[0]["auto"]) == 1
    assert int(rows[0]["review"]) == 1
    assert int(
        rows[0]["non_separator"]
    ) == 1

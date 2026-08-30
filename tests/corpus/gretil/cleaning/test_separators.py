"""Tests for Pass 3A v2 opaque-protected separator normalization."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.separators import (
    PASS3A_IMPLEMENTATION,
    build_pass3a_candidate,
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


def test_version_signature() -> None:
    assert (
        PASS3A_IMPLEMENTATION
        == "opaque-protected-v2"
    )


def test_basic_dot_boundaries() -> None:
    result = normalize_document(
        "asmin.vai.loka.ubhaye |\n",
        DOT_FILE,
    )

    assert result.text == (
        "asmin vai loka ubhaye |\n"
    )
    assert len(result.auto) == 3


def test_opaque_parenthesis_on_both_sides() -> None:
    result = normalize_document(
        "anitam.(?).bhavati |\n",
        DOT_FILE,
    )

    assert result.text == (
        "anitam (?) bhavati |\n"
    )
    assert len(result.auto) == 2
    assert not result.review


def test_inner_dots_of_protected_span_are_untouched() -> None:
    result = normalize_document(
        "śraddhād.(.eva.asya.).satya |\n",
        DOT_FILE,
    )

    assert result.text == (
        "śraddhād (.eva.asya.) satya |\n"
    )

    assert len(result.auto) == 2

    # The three dots inside the parentheses remain unchanged.
    assert "(.eva.asya.)" in result.text


def test_other_protected_span_types_are_opaque() -> None:
    result = normalize_document(
        (
            "deva.[foo.bar].gacchati "
            "rāma.{x.y}.vadati "
            "indra.<a.b>.eti |\n"
        ),
        DOT_FILE,
    )

    assert result.text == (
        "deva [foo.bar] gacchati "
        "rāma {x.y} vadati "
        "indra <a.b> eti |\n"
    )


def test_leading_dot_is_removed() -> None:
    result = normalize_document(
        ".pra.vo.vājā |\n",
        DOT_FILE,
    )

    assert result.text == (
        "pra vo vājā |\n"
    )

    assert any(
        item.reason
        == "leading_edge_separator"
        for item in result.auto
    )


def test_trailing_lexical_dot_is_removed() -> None:
    result = normalize_document(
        "tvam.hy.agne.manotā.\n",
        DOT_FILE,
    )

    assert result.text == (
        "tvam hy agne manotā\n"
    )


def test_numeric_final_dot_is_not_removed() -> None:
    original = "ṛV 6.28.\n"

    result = normalize_document(
        original,
        DOT_FILE,
    )

    assert result.text == original
    assert not result.auto


def test_numeric_dots_are_ignored() -> None:
    original = "1.2.3 iti |\n"

    result = normalize_document(
        original,
        DOT_FILE,
    )

    assert result.text == original
    assert not result.auto


def test_dot_around_danda() -> None:
    result = normalize_document(
        "yājyā.|.viśve.devāḥ |\n",
        DOT_FILE,
    )

    assert result.text == (
        "yājyā | viśve devāḥ |\n"
    )


def test_dot_inside_parenthetical_metadata_remains() -> None:
    result = normalize_document(
        (
            "agnim.na "
            "(soma: sāvitra.graha.etc.) |\n"
        ),
        DOT_FILE,
    )

    assert result.text == (
        "agnim na "
        "(soma: sāvitra.graha.etc.) |\n"
    )


def test_non_target_is_untouched() -> None:
    original = (
        "asmin.vai kule-kule |\n"
    )

    result = normalize_document(
        original,
        NON_TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert not result.review


def test_hyphen_engine_still_works_when_enabled() -> None:
    (
        cleaned,
        auto,
        review,
        _,
    ) = normalize_line(
        "kule-kule anyo-'nyaḥ",
        path="synthetic.txt",
        line_number=1,
        dot_enabled=False,
        hyphen_enabled=True,
    )

    assert cleaned == (
        "kule kule anyo 'nyaḥ"
    )
    assert len(auto) == 2
    assert not review


def test_corpus_builder_and_summary_signature(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / DOT_FILE,
        "anitam.(?).bhavati |\n",
    )
    _write(
        input_root / NON_TARGET,
        "foo.bar |\n",
    )

    non_target_before = (
        input_root / NON_TARGET
    ).read_bytes()

    result = build_pass3a_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 2
    assert result.target_files == 1
    assert result.auto_dot == 2

    assert (
        output_root / DOT_FILE
    ).read_text(
        encoding="utf-8"
    ) == "anitam (?) bhavati |\n"

    assert (
        output_root / NON_TARGET
    ).read_bytes() == non_target_before

    summary = (
        report_dir
        / "gretil_pass3a_separator_summary.txt"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "implementation: opaque-protected-v2"
        in summary
    )


def test_reports_written(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / DOT_FILE,
        "foo. anitam.(?).bhavati |\n",
    )

    build_pass3a_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    auto_path = (
        report_dir
        / "gretil_pass3a_separator_auto.csv"
    )
    review_path = (
        report_dir
        / "gretil_pass3a_separator_review.csv"
    )

    assert auto_path.is_file()
    assert review_path.is_file()

    with auto_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        auto_rows = list(
            csv.DictReader(handle)
        )

    assert len(auto_rows) == 2

    with review_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        review_rows = list(
            csv.DictReader(handle)
        )

    assert len(review_rows) == 1
    assert (
        review_rows[0]["reason"]
        == "adjacent_whitespace"
    )

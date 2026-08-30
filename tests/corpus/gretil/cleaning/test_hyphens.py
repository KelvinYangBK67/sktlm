"""Tests for Pass 3B v3 final generic hyphen normalization."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from sktlm.corpus.gretil.cleaning.hyphens import (
    HYPHEN_BOUNDARY_FILES,
    IMPLEMENTATION,
    LAYOUT_REFINEMENT_FILES,
    build_pass3b_v3_candidate,
    normalize_document,
    normalize_line,
)


NORMAL_TARGET = "5_poetry/2_kavya/bhattiku.txt"
VAGAAH = "6_sastra/7_ayur/vagaah_u.txt"
VAIMP = "4_rellit/vaisn/vaimp__u.txt"
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


def test_signature_and_whitelist() -> None:
    assert (
        IMPLEMENTATION
        == "hyphen-executor-v3"
    )
    assert len(
        HYPHEN_BOUNDARY_FILES
    ) == 32
    assert (
        VAGAAH
        not in LAYOUT_REFINEMENT_FILES
    )
    assert (
        VAIMP
        not in LAYOUT_REFINEMENT_FILES
    )


def test_general_separator() -> None:
    result = normalize_document(
        "kule-kule anyo-'nyaḥ |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "kule kule anyo 'nyaḥ |\n"
    )


def test_redundant_hyphen_before_space() -> None:
    result = normalize_document(
        "pāda- śaucād |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "pāda śaucād |\n"
    )


def test_apostrophe_hyphen() -> None:
    result = normalize_document(
        "yo '-pūrva |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "yo 'pūrva |\n"
    )


def test_trailing_hyphen_at_line_end_removed() -> None:
    result = normalize_document(
        "indriyārtha-\n"
        "svarūpa-mahasaiva nipīta-bheda-\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "indriyārtha\n"
        "svarūpa mahasaiva nipīta bheda\n"
    )

    rules = Counter(
        item.rule
        for item in result.auto
    )

    assert (
        rules[
            "trailing_hyphen_at_line_end_removed"
        ]
        == 2
    )


def test_leading_line_edge_hyphen_is_untouched() -> None:
    original = (
        "-praveṇī-kuthakāstṛtam\n"
    )

    result = normalize_document(
        original,
        NORMAL_TARGET,
    )

    assert result.text == (
        "-praveṇī kuthakāstṛtam\n"
    )

    assert any(
        item.reason == "line_edge"
        for item in result.review
    )


def test_trailing_hyphen_not_removed_in_vagaah() -> None:
    original = "siddhāsanam-\n"

    result = normalize_document(
        original,
        VAGAAH,
    )

    assert result.text == original
    assert len(result.review) == 1


def test_trailing_hyphen_not_removed_in_vaimp() -> None:
    original = "deva-\n"

    result = normalize_document(
        original,
        VAIMP,
    )

    assert result.text == original
    assert len(result.review) == 1


def test_double_apostrophe_sequence() -> None:
    result = normalize_document(
        "yac cāpi yatnā-''dṛta-mantra-vṛttir |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "yac cāpi yatnā''dṛta mantra vṛttir |\n"
    )

    assert any(
        item.rule
        == "hyphen_before_apostrophe_sequence_removed"
        for item in result.auto
    )


def test_single_apostrophe_after_hyphen_is_already_general_separator() -> None:
    result = normalize_document(
        "anyo-'nyaḥ |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "anyo 'nyaḥ |\n"
    )

    assert (
        result.auto[0].rule
        == "general_separator_to_space"
    )


def test_numeric_and_double_hyphen_untouched() -> None:
    original = (
        "1901-1905 foo--bar |\n"
    )

    result = normalize_document(
        original,
        NORMAL_TARGET,
    )

    assert result.text == original
    assert len(
        result.non_separator
    ) == 3


def test_protected_hyphen_untouched() -> None:
    original = (
        "deva (foo-bar) gacchati |\n"
    )

    result = normalize_document(
        original,
        NORMAL_TARGET,
    )

    assert result.text == original
    assert len(
        result.non_separator
    ) == 1


def test_non_target_byte_semantics_untouched() -> None:
    original = (
        "kule-kule pada- śaucād "
        "yatnā-''dṛta |\n"
    )

    result = normalize_document(
        original,
        NON_TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert not result.review
    assert not result.non_separator


def test_mixed_line_rules() -> None:
    (
        cleaned,
        auto,
        review,
        non_separator,
    ) = normalize_line(
        (
            "kule-kule "
            "pāda- śaucād "
            "yo '-pūrva "
            "yatnā-''dṛta "
            "1901-1905"
        ),
        path=NORMAL_TARGET,
        line_number=1,
    )

    assert cleaned == (
        "kule kule "
        "pāda śaucād "
        "yo 'pūrva "
        "yatnā''dṛta "
        "1901-1905"
    )

    rules = Counter(
        item.rule
        for item in auto
    )

    assert (
        rules[
            "general_separator_to_space"
        ]
        == 1
    )
    assert (
        rules[
            "redundant_hyphen_before_space_removed"
        ]
        == 1
    )
    assert (
        rules[
            "apostrophe_hyphen_removed"
        ]
        == 1
    )
    assert (
        rules[
            "hyphen_before_apostrophe_sequence_removed"
        ]
        == 1
    )
    assert not review
    assert len(
        non_separator
    ) == 1


def test_builder_rebuilds_from_pass3a_input(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / NORMAL_TARGET,
        (
            "kule-kule\n"
            "indriyārtha-\n"
            "yatnā-''dṛta |\n"
        ),
    )
    _write(
        input_root / NON_TARGET,
        "foo-bar |\n",
    )

    non_target_before = (
        input_root / NON_TARGET
    ).read_bytes()

    result = build_pass3b_v3_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 2
    assert (
        result.present_whitelist_files
        == 1
    )

    assert (
        output_root / NORMAL_TARGET
    ).read_text(
        encoding="utf-8"
    ) == (
        "kule kule\n"
        "indriyārtha\n"
        "yatnā''dṛta |\n"
    )

    assert (
        output_root / NON_TARGET
    ).read_bytes() == (
        non_target_before
    )


def test_reports_written(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / NORMAL_TARGET,
        (
            "kule-kule\n"
            "indriyārtha-\n"
            "yatnā-''dṛta |\n"
        ),
    )

    build_pass3b_v3_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    summary = (
        report_dir
        / "gretil_pass3b_v3_hyphen_summary.txt"
    )
    audit = (
        report_dir
        / "gretil_pass3b_v3_hyphen_file_audit.csv"
    )
    auto_file = (
        report_dir
        / "gretil_pass3b_v3_hyphen_auto.csv"
    )
    review_file = (
        report_dir
        / "gretil_pass3b_v3_hyphen_review.csv"
    )
    nonseparator_file = (
        report_dir
        / "gretil_pass3b_v3_hyphen_nonseparator.csv"
    )

    assert summary.is_file()
    assert audit.is_file()
    assert auto_file.is_file()
    assert review_file.is_file()
    assert nonseparator_file.is_file()

    summary_text = summary.read_text(
        encoding="utf-8"
    )
    assert (
        "implementation: hyphen-executor-v3"
        in summary_text
    )

    with audit.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert len(rows) == 1
    assert (
        int(
            rows[0][
                "general_separator"
            ]
        )
        == 1
    )
    assert (
        int(
            rows[0][
                "trailing_edge"
            ]
        )
        == 1
    )
    assert (
        int(
            rows[0][
                "apostrophe_sequence"
            ]
        )
        == 1
    )

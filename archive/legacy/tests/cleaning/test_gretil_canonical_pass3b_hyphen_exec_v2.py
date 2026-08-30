"""Tests for Pass 3B v2 hyphen refinement executor."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from sktlm.data.gretil_canonical_pass3b_hyphen_exec_v2 import (
    HYPHEN_BOUNDARY_FILES,
    IMPLEMENTATION,
    REDUNDANT_HYPHEN_SPACE_FILES,
    build_pass3b_v2_candidate,
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
        == "hyphen-executor-v2"
    )
    assert len(
        HYPHEN_BOUNDARY_FILES
    ) == 32
    assert (
        VAGAAH
        not in REDUNDANT_HYPHEN_SPACE_FILES
    )
    assert (
        VAIMP
        not in REDUNDANT_HYPHEN_SPACE_FILES
    )


def test_general_separator_still_becomes_space() -> None:
    result = normalize_document(
        "kule-kule anyo-'nyaḥ |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "kule kule anyo 'nyaḥ |\n"
    )

    rules = [
        item.rule
        for item in result.auto
    ]

    assert rules == [
        "general_separator_to_space",
        "general_separator_to_space",
    ]


def test_redundant_hyphen_before_space_removed() -> None:
    result = normalize_document(
        "sva-yoga- māyā-balaṃ |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "sva yoga māyā balaṃ |\n"
    )

    assert any(
        item.rule
        == "redundant_hyphen_before_space_removed"
        for item in result.auto
    )


def test_existing_space_is_preserved_not_doubled() -> None:
    result = normalize_document(
        "pāda- śaucād |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "pāda śaucād |\n"
    )


def test_redundant_space_rule_does_not_fire_in_vagaah() -> None:
    original = (
        "sva-yoga- māyā-balaṃ |\n"
    )

    result = normalize_document(
        original,
        VAGAAH,
    )

    # Ordinary lexical hyphens still normalize; the residual "- " is kept.
    assert result.text == (
        "sva yoga- māyā balaṃ |\n"
    )

    assert any(
        item.reason
        == "adjacent_whitespace"
        for item in result.review
    )


def test_redundant_space_rule_does_not_fire_in_vaimp() -> None:
    original = (
        "deva- śabda |\n"
    )

    result = normalize_document(
        original,
        VAIMP,
    )

    assert result.text == original
    assert len(result.review) == 1


def test_apostrophe_hyphen_removed() -> None:
    result = normalize_document(
        "yo '-pūrva-vaidyāya |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "yo 'pūrva vaidyāya |\n"
    )

    assert any(
        item.rule
        == "apostrophe_hyphen_removed"
        for item in result.auto
    )


def test_apostrophe_hyphen_removed_without_space_before_apostrophe() -> None:
    result = normalize_document(
        "raraṃhā'-śvakuñjaram |\n",
        NORMAL_TARGET,
    )

    assert result.text == (
        "raraṃhā'śvakuñjaram |\n"
    )


def test_apostrophe_rule_is_allowed_in_vagaah() -> None:
    result = normalize_document(
        "yo '-pūrva |\n",
        VAGAAH,
    )

    assert result.text == (
        "yo 'pūrva |\n"
    )


def test_numeric_and_double_hyphens_remain() -> None:
    original = (
        "1901-1905 foo--bar |\n"
    )

    result = normalize_document(
        original,
        NORMAL_TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert len(
        result.non_separator
    ) == 3


def test_protected_hyphen_remains() -> None:
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


def test_line_edge_remains_review() -> None:
    original = (
        "atha siddhāsanam-\n"
    )

    result = normalize_document(
        original,
        NORMAL_TARGET,
    )

    assert result.text == original
    assert len(
        result.review
    ) == 1
    assert (
        result.review[0].reason
        == "line_edge"
    )


def test_non_target_remains_untouched() -> None:
    original = (
        "kule-kule yo '-pūrva "
        "pāda- śaucād |\n"
    )

    result = normalize_document(
        original,
        NON_TARGET,
    )

    assert result.text == original
    assert not result.auto
    assert not result.review
    assert not result.non_separator


def test_mixed_line_rule_counts() -> None:
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
            "1901-1905"
        ),
        path=NORMAL_TARGET,
        line_number=1,
    )

    assert cleaned == (
        "kule kule "
        "pāda śaucād "
        "yo 'pūrva "
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

    assert not review
    assert len(
        non_separator
    ) == 1


def test_complete_builder_rebuilds_from_pass3a_style_input(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"

    _write(
        input_root / NORMAL_TARGET,
        (
            "kule-kule "
            "pāda- śaucād "
            "yo '-pūrva |\n"
        ),
    )

    _write(
        input_root / NON_TARGET,
        "foo-bar |\n",
    )

    non_target_before = (
        input_root / NON_TARGET
    ).read_bytes()

    result = build_pass3b_v2_candidate(
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
        output_root
        / NORMAL_TARGET
    ).read_text(
        encoding="utf-8"
    ) == (
        "kule kule "
        "pāda śaucād "
        "yo 'pūrva |\n"
    )

    assert (
        output_root
        / NON_TARGET
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
        input_root / NORMAL_TARGET,
        (
            "kule-kule "
            "pāda- śaucād "
            "yo '-pūrva "
            "1901-1905 |\n"
        ),
    )

    build_pass3b_v2_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    summary = (
        report_dir
        / "gretil_pass3b_v2_hyphen_summary.txt"
    )
    audit = (
        report_dir
        / "gretil_pass3b_v2_hyphen_file_audit.csv"
    )
    auto_file = (
        report_dir
        / "gretil_pass3b_v2_hyphen_auto.csv"
    )
    review_file = (
        report_dir
        / "gretil_pass3b_v2_hyphen_review.csv"
    )
    nonseparator_file = (
        report_dir
        / "gretil_pass3b_v2_hyphen_nonseparator.csv"
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
                "redundant_space"
            ]
        )
        == 1
    )
    assert (
        int(
            rows[0][
                "apostrophe"
            ]
        )
        == 1
    )

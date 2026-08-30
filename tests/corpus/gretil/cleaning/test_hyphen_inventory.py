"""Tests for the hyphen inventory dry-run classifier."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.hyphen_inventory import (
    IMPLEMENTATION,
    build_inventory,
    classify_hyphen,
    inventory_document,
)


def _write(
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        text,
        encoding="utf-8",
    )


def test_signature() -> None:
    assert (
        IMPLEMENTATION
        == "hyphen-inventory-v1"
    )


def test_lexical_lexical_is_separator() -> None:
    line = "kule-kule"
    index = line.index("-")

    classification, left, right = (
        classify_hyphen(
            line,
            index,
        )
    )

    assert (
        classification.decision
        == "SEPARATOR"
    )
    assert (
        classification.reason
        == "lexical_to_lexical"
    )
    assert left.kind == "LEXICAL"
    assert right.kind == "LEXICAL"


def test_avagraha_context_is_separator() -> None:
    line = "anyo-'nyaḥ"
    index = line.index("-")

    classification, _, right = (
        classify_hyphen(
            line,
            index,
        )
    )

    assert (
        classification.decision
        == "SEPARATOR"
    )
    assert (
        classification.reason
        == "to_avagraha_lexical"
    )
    assert right.kind == "APOSTROPHE"


def test_numeric_range_is_non_separator() -> None:
    line = "1901-1905"
    index = line.index("-")

    classification, _, _ = (
        classify_hyphen(
            line,
            index,
        )
    )

    assert (
        classification.decision
        == "NON_SEPARATOR"
    )
    assert (
        classification.reason
        == "adjacent_digit"
    )


def test_double_hyphen_is_non_separator() -> None:
    line = "foo--bar"
    indexes = [
        index
        for index, char
        in enumerate(line)
        if char == "-"
    ]

    decisions = [
        classify_hyphen(
            line,
            index,
        )[0]
        for index in indexes
    ]

    assert all(
        item.decision
        == "NON_SEPARATOR"
        for item in decisions
    )
    assert all(
        item.reason
        == "repeated_hyphen"
        for item in decisions
    )


def test_hyphen_inside_parenthesis_is_non_separator() -> None:
    line = "deva (foo-bar) gacchati"
    index = line.index("-")

    classification, _, _ = (
        classify_hyphen(
            line,
            index,
        )
    )

    assert (
        classification.decision
        == "NON_SEPARATOR"
    )
    assert (
        classification.reason
        == "inside_protected_span"
    )


def test_protected_to_lexical_is_separator() -> None:
    line = "(foo)-bar"
    index = line.index("-")

    classification, left, right = (
        classify_hyphen(
            line,
            index,
        )
    )

    assert (
        classification.decision
        == "SEPARATOR"
    )
    assert left.kind == "PROTECTED"
    assert right.kind == "LEXICAL"


def test_adjacent_whitespace_is_review() -> None:
    line = "foo - bar"
    index = line.index("-")

    classification, _, _ = (
        classify_hyphen(
            line,
            index,
        )
    )

    assert (
        classification.decision
        == "REVIEW"
    )
    assert (
        classification.reason
        == "adjacent_whitespace"
    )


def test_line_edge_is_review() -> None:
    line = "-foo"
    index = 0

    classification, _, _ = (
        classify_hyphen(
            line,
            index,
        )
    )

    assert (
        classification.decision
        == "REVIEW"
    )
    assert (
        classification.reason
        == "line_edge"
    )


def test_inventory_document_does_not_modify_text() -> None:
    text = (
        "kule-kule 1901-1905 "
        "anyo-'nyaḥ\n"
    )

    occurrences, _ = (
        inventory_document(
            text,
            "example.txt",
        )
    )

    assert len(occurrences) == 3
    assert text == (
        "kule-kule 1901-1905 "
        "anyo-'nyaḥ\n"
    )


def test_build_inventory_reports_candidates(
    tmp_path: Path,
) -> None:
    input_root = (
        tmp_path / "input"
    )
    report_dir = (
        tmp_path / "reports"
    )

    good = "5_poetry/good.txt"
    mixed = "5_poetry/mixed.txt"

    _write(
        input_root / good,
        " ".join(
            "kule-kule"
            for _ in range(30)
        )
        + "\n",
    )

    _write(
        input_root / mixed,
        "kule-kule 1901-1905 foo - bar\n",
    )

    result = build_inventory(
        input_root=input_root,
        report_dir=report_dir,
        min_occurrences=20,
        min_separator_share=0.95,
        max_review_share=0.05,
    )

    assert result.files_scanned == 2
    assert result.files_with_hyphen == 2
    assert result.candidate_files == 1

    candidate_path = (
        report_dir
        / "gretil_hyphen_inventory_candidates.csv"
    )

    with candidate_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(
                handle
            )
        )

    assert len(rows) == 1
    assert rows[0]["path"] == good

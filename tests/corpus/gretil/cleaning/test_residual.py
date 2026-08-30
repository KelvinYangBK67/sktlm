"""Tests for post-Pass-3B full residual audit."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.residual import (
    IMPLEMENTATION,
    audit_text,
    build_audit,
    classify_character,
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
        == "post-pass3b-full-audit-v1.1"
    )


def test_allowed_sanskrit_text() -> None:
    text = (
        "devo'pi gacchati |\n"
        "śivaḥ śaṅkaraḥ ||\n"
    )

    counts, hits = audit_text(
        text,
        "clean.txt",
    )

    assert sum(
        counts.values()
    ) == 0
    assert not hits



def test_anusvara_and_visarga_allowed() -> None:
    assert classify_character("ṃ") is None
    assert classify_character("ḥ") is None

def test_categories() -> None:
    assert classify_character(
        "."
    ) == "DOT"
    assert classify_character(
        ","
    ) == "COMMA"
    assert classify_character(
        "-"
    ) == "HYPHEN"
    assert classify_character(
        "_"
    ) == "UNDERSCORE"
    assert classify_character(
        "3"
    ) == "DIGIT"
    assert classify_character(
        "("
    ) == "ROUND"
    assert classify_character(
        "["
    ) == "SQUARE"
    assert classify_character(
        "{"
    ) == "CURLY"
    assert classify_character(
        "<"
    ) == "ANGLE"
    assert classify_character(
        "A"
    ) == "UPPERCASE"
    assert classify_character(
        "x"
    ) == "NON_IAST_LATIN"


def test_combining_accent_allowed() -> None:
    assert classify_character(
        "\u0301"
    ) is None


def test_build_audit_counts_files(
    tmp_path: Path,
) -> None:
    input_root = (
        tmp_path / "input"
    )
    report_dir = (
        tmp_path / "reports"
    )

    _write(
        input_root / "clean.txt",
        "devo'pi |\n",
    )
    _write(
        input_root / "dirty.txt",
        "devaḥ, rāmaḥ. 3\n",
    )

    result = build_audit(
        input_root=input_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 2
    assert result.strict_clean_files == 1
    assert result.flagged_files == 1

    summary = (
        report_dir
        / "gretil_post_pass3b_full_audit_summary.txt"
    )
    files = (
        report_dir
        / "gretil_post_pass3b_full_audit_files.csv"
    )

    assert summary.is_file()
    assert files.is_file()

    with files.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    dirty = next(
        row
        for row in rows
        if row["path"] == "dirty.txt"
    )

    assert int(
        dirty["DOT"]
    ) == 1
    assert int(
        dirty["COMMA"]
    ) == 1
    assert int(
        dirty["DIGIT"]
    ) == 1

"""Tests for the whitelist-only formal GRETIL canonical corpus."""

from __future__ import annotations

import csv

import pytest

from sktlm.data.dataset import load_canonical_segments
from sktlm.data.gretil_canonical import (
    build_canonical_corpus,
    extract_gretil_body,
    has_accent,
    normalize_canonical_iast,
    parse_whitelist,
    unknown_characters,
    validate_canonical_corpus,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("deva\u015b  ca", "deva\u015b ca"),
        ("deva\u015b ca r\u0101ma\u015b ca", "deva\u015b ca r\u0101ma\u015b ca"),
        ("devo'pi", "devo'pi"),
        ("r\u0101ma\u015bca", "r\u0101ma\u015bca"),
        ("deva\u1e25 12 gacchati", "deva\u1e25 gacchati"),
        ("deva\u1e25\u0964", "deva\u1e25|"),
    ),
)
def test_normalization_preserves_observed_lexical_boundaries(source: str, expected: str) -> None:
    assert normalize_canonical_iast(source).text == expected


def test_structural_prefixes_are_removed_without_joining_words() -> None:
    source = (
        "01,000.000*0001_01\tdeva\u015b ca\n"
        "01,002.126d*0128_01(127ab)\tkar\u1e47a\u1e25\n"
        "(GBr_1,1.1a) r\u0101ma\u015b ca\n"
        "AB 1.1a/ devo'pi\n"
        "div1 agni\u1e25 //143//\n"
        "KAZ01.1.01| artha\u1e25 || GarP_1,1.1 ||\n"
        "pada\u1e43 ||43|||\n"
        "nested ||57|| || ManGS_1,1. ||\n"
        "suffix // ManGS_1,1. 17 //\n"
        "(GBr_col) sam\u0101ptam"
    )
    assert normalize_canonical_iast(source).text.splitlines() == [
        "deva\u015b ca",
        "kar\u1e47a\u1e25",
        "r\u0101ma\u015b ca",
        "devo'pi",
        "agni\u1e25 ||",
        "artha\u1e25 ||",
        "pada\u1e43 ||",
        "nested ||",
        "suffix ||",
        "sam\u0101ptam",
    ]


def test_vedic_pluta_number_is_not_treated_as_a_structural_prefix() -> None:
    source = "adhvaryo3.ity.\u0101mantrita\u1e25 |"
    assert normalize_canonical_iast(source).text == source


def test_parallel_citation_numbers_are_not_treated_as_verse_numbers() -> None:
    source = "text [RV 10.42/43/44.11a, PS_15.11.1/16.8.11a]"
    result = normalize_canonical_iast(source).text
    assert "10.42|43|44.11a" in result
    assert "PS_15.11.1|16.8.11a" in result
    assert normalize_canonical_iast("[BhP  10.29.41] iti text").text == "iti text"


def test_lacuna_markers_are_not_treated_as_decorative_headers() -> None:
    source = "**** **** ratham \u0101ruhya"
    assert normalize_canonical_iast(source).text == source
    marker_only = "**** **** **** ****"
    assert normalize_canonical_iast(marker_only).text == marker_only


def test_structural_normalization_is_idempotent() -> None:
    source = "01,002.126d*0128_01(127ab) text // ManGS_1,1. 17 //"
    once = normalize_canonical_iast(source).text
    assert normalize_canonical_iast(once).text == once


def test_accents_are_preserved_and_detected() -> None:
    source = "agni\u0301m ile\u0300"
    result = normalize_canonical_iast(source).text
    assert has_accent(result)
    assert "\u0301" in __import__("unicodedata").normalize("NFD", result)
    assert "\u0300" in __import__("unicodedata").normalize("NFD", result)


def test_unknown_characters_are_preserved_and_reported() -> None:
    source = "deva\u2603 gacchati a\u036f"
    result = normalize_canonical_iast(source).text
    assert "\u2603" in result
    assert "\u036f" in result
    assert unknown_characters(result) == {"\u2603": 1, "\u036f": 1}


def test_body_extraction_starts_after_second_rule_and_keeps_body_tables() -> None:
    source = (
        "<html><head><title>ignore</title></head><body>banner<hr>"
        "<table><tr><td>metadata</td></tr></table><hr><pre>"
        "001.001. deva\u015b ca\n<table><tr><td>r\u0101ma\u015b ca</td></tr></table>"
        "</pre></body></html>"
    )
    body = extract_gretil_body(source)
    assert "banner" not in body
    assert "metadata" not in body
    assert "deva\u015b ca" in body
    assert "r\u0101ma\u015b ca" in body


def test_whitelist_is_exact_and_rejects_duplicates(tmp_path) -> None:
    whitelist = tmp_path / "whitelist.txt"
    whitelist.write_text("# comment\n2_epic/a.htm\n\n2_epic/b.htm\n", encoding="utf-8")
    assert parse_whitelist(whitelist) == ("2_epic/a.htm", "2_epic/b.htm")
    whitelist.write_text("2_epic/a.htm\n2_epic/a.htm\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        parse_whitelist(whitelist)


def test_build_validate_and_dataset_loader_integration(tmp_path, monkeypatch) -> None:
    relative = "2_epic/sample.htm"
    source_root = tmp_path / "data" / "raw" / "gretil"
    source_path = source_root / "2_epic" / "sample.htm"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "<html><body>header<hr>metadata<hr><pre>"
        "001.001. deva\u015b ca r\u0101ma\u015b ca\n"
        "001.002. devo'pi r\u0101ma\u015bca\n"
        "001.003. agni\u0301m \u2603"
        "</pre></body></html>",
        encoding="utf-8",
    )
    whitelist = tmp_path / "notes" / "whitelist.txt"
    whitelist.parent.mkdir()
    whitelist.write_text(f"{relative}\n", encoding="utf-8")
    canonical_root = tmp_path / "data" / "canonical" / "gretil_iast"
    manifest = tmp_path / "data" / "manifests" / "canonical_corpus.csv"
    report_dir = tmp_path / "data" / "_reports"

    result = build_canonical_corpus(
        source_root=source_root,
        whitelist_path=whitelist,
        canonical_root=canonical_root,
        manifest_path=manifest,
        report_dir=report_dir,
        repo_root=tmp_path,
    )
    assert len(result.rows) == 1
    output = canonical_root / "2_epic" / "sample.txt"
    text = output.read_text(encoding="utf-8")
    assert "deva\u015b ca r\u0101ma\u015b ca" in text
    assert "devo'pi r\u0101ma\u015bca" in text
    assert "\u2603" in text
    assert (report_dir / "gretil_unknown_characters.csv").is_file()
    assert (report_dir / "gretil_cleaning_audit.csv").is_file()
    assert (report_dir / "gretil_corpus_summary.txt").is_file()
    summary = (report_dir / "gretil_corpus_summary.txt").read_text(encoding="utf-8")
    assert "whitelist_document_count: 1" in summary
    assert "successfully_processed_count: 1" in summary
    assert "missing_source_count: 0" in summary
    with (report_dir / "gretil_cleaning_audit.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        audit_row = next(csv.DictReader(handle))
    assert {
        "source_path", "source_chars", "extracted_chars", "canonical_chars",
        "removed_chars", "replacement_count",
    }.issubset(audit_row)

    rows = validate_canonical_corpus(
        source_root=source_root,
        whitelist_path=whitelist,
        canonical_root=canonical_root,
        manifest_path=manifest,
        repo_root=tmp_path,
    )
    assert len(rows) == 1
    monkeypatch.chdir(tmp_path)
    segments = load_canonical_segments(manifest)
    assert [segment.canonical_text for segment in segments] == text.splitlines()
    assert all(segment.canonical_script == "iast" for segment in segments)

    with manifest.open("r", encoding="utf-8", newline="") as handle:
        manifest_row = next(csv.DictReader(handle))
    assert manifest_row["source"] == "gretil"
    assert manifest_row["relative_path"] == relative
    assert manifest_row["has_accent"] == "true"
    assert manifest_row["has_unknown_chars"] == "true"


def test_missing_sources_fail_before_any_output_is_written(tmp_path) -> None:
    whitelist = tmp_path / "whitelist.txt"
    whitelist.write_text("2_epic/missing.htm\n", encoding="utf-8")
    canonical_root = tmp_path / "canonical"
    with pytest.raises(FileNotFoundError, match="missing"):
        build_canonical_corpus(
            source_root=tmp_path / "raw",
            whitelist_path=whitelist,
            canonical_root=canonical_root,
            manifest_path=tmp_path / "manifest.csv",
            report_dir=tmp_path / "reports",
            repo_root=tmp_path,
        )
    assert not canonical_root.exists()

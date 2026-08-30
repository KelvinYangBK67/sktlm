from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sktlm.corpus.gretil.cleaning.pre_m0 import (
    audit_anomalies,
    normalize_to_fixed_point,
    run_pre_m0_closure,
    validate_mechanical_corpus,
)
from sktlm.corpus.gretil.freeze import validate_freeze


def test_fixed_point_normalization_applies_only_mechanical_policy() -> None:
    dirty = (
        "\r\n"
        "  a\u0304  text||next  \r\n"
        "|\r"
        "||\r\n"
        " | second\r\n"
        "||third\r\n"
        "\r\n"
        "\r\n"
        "last |end\r\n"
    )
    result = normalize_to_fixed_point(dirty)

    assert result.text == (
        "ā text || next\n"
        "second\n"
        "|| third\n"
        "\n"
        "last | end\n"
    )
    assert result.iterations == 2
    assert result.counts["unicode_nfc"] == 1
    assert result.counts["standalone_single_danda_lines_removed"] == 1
    assert result.counts["standalone_double_danda_lines_removed"] == 1
    assert result.counts["line_start_single_danda_removed"] == 1


def test_recursive_normalization_reaches_newly_exposed_leading_danda() -> None:
    result = normalize_to_fixed_point("| | text\n")
    assert result.text == "text\n"
    assert result.iterations == 3
    assert result.counts["line_start_single_danda_removed"] == 2


def test_max_iteration_guard_fails_instead_of_silently_continuing() -> None:
    with pytest.raises(RuntimeError, match="did not reach a fixed point"):
        normalize_to_fixed_point("| text\n", max_iterations=1)


def test_anomaly_audit_reports_examples_but_does_not_modify_corpus(
    tmp_path: Path,
) -> None:
    root = tmp_path / "canonical"
    root.mkdir()
    source = root / "example.txt"
    source.write_text(
        "k pūutinā bhuñjīita vipluaṃ ai au\n",
        encoding="utf-8",
        newline="",
    )
    before = source.read_bytes()
    summary = tmp_path / "summary.tsv"
    details = tmp_path / "details.tsv"

    result = audit_anomalies(
        canonical_root=root,
        summary_path=summary,
        details_path=details,
    )

    assert source.read_bytes() == before
    assert result.occurrence_counts["isolated_consonant"] == 1
    assert result.distinct_form_counts["isolated_consonant"] == 1
    assert result.occurrence_counts["adjacent_vowels"] == 3
    assert result.distinct_form_counts["adjacent_vowels"] == 3
    sequences = {
        row["matched_sequence"]
        for row in result.details
        if row["issue_type"] == "adjacent_vowels"
    }
    assert sequences == {"ūu", "īi", "ua"}
    assert "ai" not in sequences
    assert "au" not in sequences
    assert summary.read_text(encoding="utf-8").splitlines()[0] == (
        "issue_type\tmatched_form\tcount\tfile_count"
    )
    assert details.read_text(encoding="utf-8").splitlines()[0] == (
        "file\tline_no\tissue_type\tmatched_form\tmatched_sequence\tcontext"
    )


def test_closure_refreshes_manifest_and_remains_freeze_valid(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "canonical" / "gretil_iast"
    source = root / "layer" / "example.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(
        ("\n ra\u0304ma  nara||deva \r\n|\r\n").encode("utf-8")
    )
    manifest = tmp_path / "canonical.csv"
    fields = [
        "canonical_path",
        "canonical_script",
        "document_id",
        "source_hash",
        "char_count",
        "line_count",
        "segment_count",
        "canonical_hash",
        "byte_count",
        "freeze_id",
        "freeze_input_path",
    ]
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "canonical_path": "data/canonical/gretil_iast/layer/example.txt",
                "canonical_script": "iast",
                "document_id": "doc-fixed",
                "source_hash": "source-fixed",
                "char_count": "0",
                "line_count": "0",
                "segment_count": "0",
                "canonical_hash": "old",
                "byte_count": "0",
                "freeze_id": "old",
                "freeze_input_path": "layer/example.txt",
            }
        )

    result = run_pre_m0_closure(
        canonical_root=root,
        manifest_path=manifest,
        freeze_report_path=tmp_path / "freeze.txt",
        summary_path=tmp_path / "summary.tsv",
        details_path=tmp_path / "details.tsv",
        closure_report_path=tmp_path / "closure.md",
    )

    assert source.read_text(encoding="utf-8") == "rāma nara || deva\n"
    mechanical = validate_mechanical_corpus(canonical_root=root)
    assert mechanical.is_clean
    validated = validate_freeze(output_root=root, manifest_path=manifest)
    assert validated.corpus_sha256 == result.normalization.after_sha256
    with manifest.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["document_id"] == "doc-fixed"
    assert row["source_hash"] == "source-fixed"
    assert result.anomaly_audit.corpus_sha256 == result.audit_after_sha256

"""Tests for conservative GRETIL canonical Pass 1 cleanup."""

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.mechanical import (
    apply_pass1,
    build_pass1_candidate,
)


def _write_canonical(
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


def test_control_characters_are_removed_without_losing_text() -> None:
    original = (
        "\u0015bharadvāja uvāca:\n"
        "tanno rudraḥ pracodayāt ||\u0001\n"
    )

    result = apply_pass1(
        original,
    )

    assert result.text == (
        "bharadvāja uvāca:\n"
        "tanno rudraḥ pracodayāt ||\n"
    )

    assert (
        result.counts["control_or_format_removed"]
        == 2
    )


def test_zero_width_joiner_is_removed() -> None:
    result = apply_pass1(
        "samohK\u200Dh̲ 'parimukto |\n"
    )

    assert "\u200d" not in result.text
    assert (
        result.counts["control_or_format_removed"]
        == 1
    )


def test_underscore_becomes_space() -> None:
    result = apply_pass1(
        "brāhmaṇam_iti\n"
    )

    assert result.text == (
        "brāhmaṇam iti\n"
    )

    assert (
        result.counts["underscore_to_space"]
        == 1
    )


def test_short_sanskrit_supplement_is_unwrapped() -> None:
    result = apply_pass1(
        "dhī-gī[ḥ]- |\n"
    )

    # Hyphens are intentionally untouched in Pass 1.
    assert result.text == (
        "dhī-gīḥ- |\n"
    )

    assert (
        result.counts[
            "square_supplement_unwrapped"
        ]
        == 1
    )


def test_editorial_square_note_is_removed() -> None:
    result = apply_pass1(
        "pracodayāt savitā "
        "[ed. pracodayānt, corr. Patyal] iti |\n"
    )

    assert result.text == (
        "pracodayāt savitā iti |\n"
    )

    assert (
        result.counts["square_editorial_removed"]
        == 1
    )


def test_scriptural_citation_is_removed() -> None:
    result = apply_pass1(
        "agnim īḷe [ṚV 1.1.1] iti |\n"
    )

    assert result.text == (
        "agnim īḷe iti |\n"
    )

    assert (
        result.counts["square_citation_removed"]
        == 1
    )


def test_angle_quote_preserves_sanskrit_and_removes_citation() -> None:
    result = apply_pass1(
        "<agnim īḷe purohitaṃ "
        "[ṚV 1.1.1]> ity evam |\n"
    )

    assert result.text == (
        "agnim īḷe purohitaṃ ity evam |\n"
    )

    assert (
        result.counts["square_citation_removed"]
        == 1
    )

    assert (
        result.counts["angle_unwrapped"]
        == 1
    )


def test_numeric_angle_locator_is_deleted() -> None:
    result = apply_pass1(
        "<1.2.13> agnīt paridhīn |\n"
    )

    assert result.text == (
        "agnīt paridhīn |\n"
    )

    assert (
        result.counts[
            "angle_numeric_locator_removed"
        ]
        == 1
    )


def test_hv_metadata_record_is_deleted() -> None:
    result = apply_pass1(
        "[h: HV (CE) Appendix I, "
        "transliterated by Peter Schreiner :h]\n"
        "nārada uvāca |\n"
    )

    assert result.text == (
        "nārada uvāca |\n"
    )

    assert (
        result.counts["hv_metadata_removed"]
        == 1
    )


def test_hv_k_record_is_deleted() -> None:
    result = apply_pass1(
        "[k: K2.4 Ñ2.3 V B Dn ins. appendix I :k]\n"
        "rāma uvāca |\n"
    )

    assert result.text == (
        "rāma uvāca |\n"
    )

    assert (
        result.counts["hv_metadata_removed"]
        == 1
    )


def test_known_round_locator_is_removed() -> None:
    result = apply_pass1(
        "sa rātryā madhyame yāme "
        "(SBV I 118) nava daśa |\n"
    )

    assert result.text == (
        "sa rātryā madhyame yāme "
        "nava daśa |\n"
    )

    assert (
        result.counts["round_editorial_removed"]
        == 1
    )


def test_folio_locator_is_removed() -> None:
    result = apply_pass1(
        "bhavati (79r = GBM 741) "
        "anāpattir varṣācchede |\n"
    )

    assert result.text == (
        "bhavati anāpattir varṣācchede |\n"
    )

    assert (
        result.counts["round_editorial_removed"]
        == 1
    )


def test_unknown_parenthesis_is_preserved() -> None:
    result = apply_pass1(
        "atha (agnyādhāna) karma |\n"
    )

    assert result.text == (
        "atha (agnyādhāna) karma |\n"
    )

    assert (
        result.counts["round_editorial_removed"]
        == 0
    )


def test_unknown_square_passage_is_preserved() -> None:
    original = (
        "ātmabhāvapratilambhe "
        "[bskal pa graṅs med pa gsum] "
        "bodhimaṇḍe |\n"
    )

    result = apply_pass1(
        original,
    )

    assert (
        "[bskal pa graṅs med pa gsum]"
        in result.text
    )


def test_hyphen_is_not_generally_modified() -> None:
    original = (
        "kule-kule pañca-pañca "
        "anyo-'nyaḥ |\n"
    )

    result = apply_pass1(
        original,
    )

    assert result.text == original


def test_period_is_not_generally_modified() -> None:
    original = (
        "apām.idma.nyayanam.samudrasya."
        "niveśanam |\n"
    )

    result = apply_pass1(
        original,
    )

    assert result.text == original


def test_comma_is_not_generally_modified() -> None:
    original = (
        "satvāḥ, dharmāḥ, bhikṣavaḥ |\n"
    )

    result = apply_pass1(
        original,
    )

    assert result.text == original


def test_uppercase_is_not_generally_modified() -> None:
    original = (
        "Var-v bhikṣavaḥ |\n"
    )

    result = apply_pass1(
        original,
    )

    assert result.text == original


def test_non_iast_latin_is_not_generally_modified() -> None:
    original = (
        "tūfaro hi prajāpatiḥ |\n"
    )

    result = apply_pass1(
        original,
    )

    assert result.text == original


def test_candidate_build_preserves_directory_structure_and_input(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "canonical"
    output_root = tmp_path / "candidate"
    report_dir = tmp_path / "reports"

    source = (
        input_root
        / "2_epic"
        / "mbh"
        / "example.txt"
    )

    original = (
        "\u0015"
        "<agnim īḷe [ṚV 1.1.1]>_iti |\n"
    )

    _write_canonical(
        source,
        original,
    )

    before = source.read_bytes()

    result = build_pass1_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 1

    destination = (
        output_root
        / "2_epic"
        / "mbh"
        / "example.txt"
    )

    assert destination.is_file()

    assert destination.read_text(
        encoding="utf-8",
    ) == (
        "agnim īḷe iti |\n"
    )

    # Formal canonical input must remain byte-identical.
    assert source.read_bytes() == before


def test_candidate_build_writes_reports(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "canonical"
    output_root = tmp_path / "candidate"
    report_dir = tmp_path / "reports"

    _write_canonical(
        input_root / "example.txt",
        "rāmaḥ_iti [ṚV 1.1.1] |\n",
    )

    build_pass1_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    audit_path = (
        report_dir
        / "gretil_canonical_pass1_cleaning_audit.csv"
    )

    summary_path = (
        report_dir
        / "gretil_canonical_pass1_summary.txt"
    )

    assert audit_path.is_file()
    assert summary_path.is_file()

    with audit_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert len(rows) == 1

    assert rows[0]["path"] == "example.txt"

    assert (
        int(rows[0]["underscore_to_space"])
        == 1
    )

    assert (
        int(rows[0]["square_citation_removed"])
        == 1
    )


def test_output_cannot_equal_input(
    tmp_path: Path,
) -> None:
    root = tmp_path / "corpus"

    _write_canonical(
        root / "example.txt",
        "rāmaḥ |\n",
    )

    try:
        build_pass1_candidate(
            input_root=root,
            output_root=root,
            report_dir=tmp_path / "reports",
        )
    except ValueError as error:
        assert (
            "must not equal"
            in str(error)
        )
    else:
        raise AssertionError(
            "expected in-place build protection"
        )

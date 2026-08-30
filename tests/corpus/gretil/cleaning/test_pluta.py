"""Tests for conservative Vedic pluta normalization."""

from __future__ import annotations

import csv
import unicodedata
from pathlib import Path

from sktlm.corpus.gretil.cleaning.pluta import (
    normalize_corpus,
    normalize_vedic_pluta,
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
        text.encode(
            "utf-8"
        )
    )


def test_long_vowels_are_auto_normalized() -> None:
    result = normalize_vedic_pluta(
        (
            "ā3 ī3 ū3 ṝ3 ḹ3 "
            "iti |\n"
        ),
        "1_veda/example.txt",
    )

    assert result.text == (
        "ā ī ū ṝ ḹ iti |\n"
    )

    assert len(
        result.normalized
    ) == 5

    assert not result.review


def test_e_o_are_auto_normalized() -> None:
    result = normalize_vedic_pluta(
        "e3 o3 iti |\n",
        "1_veda/example.txt",
    )

    assert result.text == (
        "e o iti |\n"
    )

    assert len(
        result.normalized
    ) == 2


def test_diphthongs_are_auto_normalized() -> None:
    result = normalize_vedic_pluta(
        "ai3 au3 iti |\n",
        "1_veda/example.txt",
    )

    assert result.text == (
        "ai au iti |\n"
    )

    assert len(
        result.normalized
    ) == 2


def test_o3m_becomes_om() -> None:
    result = normalize_vedic_pluta(
        "o3m ity ācāryāḥ |\n",
        "1_veda/example.txt",
    )

    assert result.text == (
        "om ity ācāryāḥ |\n"
    )

    assert len(
        result.normalized
    ) == 1


def test_known_long_pluta_examples() -> None:
    result = normalize_vedic_pluta(
        (
            "yātayāmāḥ "
            "saṃvatsarā3 "
            "ayātayāmā3 iti |\n"
        ),
        "1_veda/example.txt",
    )

    assert result.text == (
        "yātayāmāḥ "
        "saṃvatsarā "
        "ayātayāmā iti |\n"
    )

    assert len(
        result.normalized
    ) == 2


def test_short_vowel_plus_three_is_review_only() -> None:
    original = (
        "a3 i3 u3 ṛ3 ḷ3 iti |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/example.txt",
    )

    assert result.text == original

    assert not result.normalized

    assert len(
        result.review
    ) == 5

    assert {
        occurrence.before
        for occurrence
        in result.review
    } == {
        "a3",
        "i3",
        "u3",
        "ṛ3",
        "ḷ3",
    }


def test_accented_short_vowel_is_review_only() -> None:
    original = (
        "á3 iti |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/example.txt",
    )

    assert result.text == original

    assert not result.normalized

    assert len(
        result.review
    ) == 1

    assert (
        result.review[0].lexical_base
        == "a"
    )


def test_accent_on_long_vowel_is_preserved() -> None:
    source = unicodedata.normalize(
        "NFC",
        "ā\u03013 iti |\n",
    )

    result = normalize_vedic_pluta(
        source,
        "1_veda/example.txt",
    )

    expected = unicodedata.normalize(
        "NFC",
        "ā\u0301 iti |\n",
    )

    assert result.text == expected

    assert len(
        result.normalized
    ) == 1


def test_decomposed_long_vowel_is_auto_normalized() -> None:
    # a + COMBINING MACRON + 3
    source = (
        "a\u03043 iti |\n"
    )

    result = normalize_vedic_pluta(
        source,
        "1_veda/example.txt",
    )

    assert result.text == (
        "ā iti |\n"
    )

    assert len(
        result.normalized
    ) == 1


def test_structural_numbers_are_untouched() -> None:
    original = (
        "1.2.3.\n"
        "||31||\n"
        "(18.15)\n"
        "3050101athāto vapānāṃ homaḥ\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/example.txt",
    )

    assert result.text == original

    assert not result.normalized

    assert not result.review


def test_locator_like_short_form_is_ignored() -> None:
    original = (
        "10a3 P.10a3 A_a3 |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/example.txt",
    )

    assert result.text == original

    assert not result.normalized

    assert not result.review


def test_protected_spans_are_untouched() -> None:
    original = (
        "rāmaḥ "
        "[ā3 a3] "
        "(ī3 i3) "
        "{ū3 u3} "
        "<o3 a3> "
        "gacchati |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/example.txt",
    )

    assert result.text == original

    assert not result.normalized

    assert not result.review


def test_non_vedic_file_is_untouched() -> None:
    original = (
        "ā3 o3 a3 i3 |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "4_rellit/example.txt",
    )

    assert result.text == original

    assert not result.normalized

    assert not result.review


def test_auto_and_review_can_coexist() -> None:
    original = (
        "nā3 a3 nū3 u3 iti |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/example.txt",
    )

    assert result.text == (
        "nā a3 nū u3 iti |\n"
    )

    assert len(
        result.normalized
    ) == 2

    assert len(
        result.review
    ) == 2


def test_corpus_build_preserves_non_vedic_files(
    tmp_path: Path,
) -> None:
    input_root = (
        tmp_path
        / "input"
    )

    output_root = (
        tmp_path
        / "output"
    )

    report_dir = (
        tmp_path
        / "reports"
    )

    vedic = (
        input_root
        / "1_veda"
        / "vedic.txt"
    )

    buddh = (
        input_root
        / "4_rellit"
        / "buddh.txt"
    )

    _write(
        vedic,
        "nā3 a3 iti |\n",
    )

    _write(
        buddh,
        "nā3 a3 Ms.10a3 |\n",
    )

    buddh_before = (
        buddh.read_bytes()
    )

    result = normalize_corpus(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert (
        result.files_scanned
        == 2
    )

    assert (
        result.vedic_files_scanned
        == 1
    )

    assert (
        result.files_changed
        == 1
    )

    assert (
        result.normalized_occurrences
        == 1
    )

    assert (
        result.review_occurrences
        == 1
    )

    assert (
        output_root
        / "1_veda"
        / "vedic.txt"
    ).read_text(
        encoding="utf-8"
    ) == (
        "nā a3 iti |\n"
    )

    assert (
        output_root
        / "4_rellit"
        / "buddh.txt"
    ).read_bytes() == (
        buddh_before
    )


def test_review_only_file_remains_byte_identical(
    tmp_path: Path,
) -> None:
    input_root = (
        tmp_path
        / "input"
    )

    output_root = (
        tmp_path
        / "output"
    )

    report_dir = (
        tmp_path
        / "reports"
    )

    source = (
        input_root
        / "1_veda"
        / "review.txt"
    )

    _write(
        source,
        "a3 i3 u3 iti |\n",
    )

    before = (
        source.read_bytes()
    )

    result = normalize_corpus(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert (
        result.files_changed
        == 0
    )

    assert (
        result.review_occurrences
        == 3
    )

    destination = (
        output_root
        / "1_veda"
        / "review.txt"
    )

    assert (
        destination.read_bytes()
        == before
    )

    assert (
        source.read_bytes()
        == before
    )


def test_reports_are_written(
    tmp_path: Path,
) -> None:
    input_root = (
        tmp_path
        / "input"
    )

    output_root = (
        tmp_path
        / "output"
    )

    report_dir = (
        tmp_path
        / "reports"
    )

    _write(
        input_root
        / "1_veda"
        / "example.txt",
        (
            "ekā3 nā3 "
            "a3 i3 |\n"
        ),
    )

    normalize_corpus(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    summary = (
        report_dir
        / "gretil_pluta_normalization_summary.txt"
    )

    normalized_files = (
        report_dir
        / "gretil_pluta_normalized_files.csv"
    )

    normalized_occurrences = (
        report_dir
        / "gretil_pluta_normalized_occurrences.csv"
    )

    review_files = (
        report_dir
        / "gretil_pluta_review_files.csv"
    )

    review_occurrences = (
        report_dir
        / "gretil_pluta_review_occurrences.csv"
    )

    assert summary.is_file()
    assert normalized_files.is_file()
    assert normalized_occurrences.is_file()
    assert review_files.is_file()
    assert review_occurrences.is_file()

    with normalized_files.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        normalized_rows = list(
            csv.DictReader(
                handle
            )
        )

    assert len(
        normalized_rows
    ) == 1

    assert (
        int(
            normalized_rows[0][
                "replacements"
            ]
        )
        == 2
    )

    with review_files.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        review_rows = list(
            csv.DictReader(
                handle
            )
        )

    assert len(
        review_rows
    ) == 1

    assert (
        int(
            review_rows[0][
                "review_occurrences"
            ]
        )
        == 2
    )


def test_input_is_never_modified(
    tmp_path: Path,
) -> None:
    input_root = (
        tmp_path
        / "input"
    )

    output_root = (
        tmp_path
        / "output"
    )

    report_dir = (
        tmp_path
        / "reports"
    )

    source = (
        input_root
        / "1_veda"
        / "example.txt"
    )

    _write(
        source,
        "nā3 a3 iti |\n",
    )

    before = (
        source.read_bytes()
    )

    normalize_corpus(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert (
        source.read_bytes()
        == before
    )

def test_verified_satapatha_short_i_pluta() -> None:
    original = (
        "vettha catvāri vratāni3 iti "
        "veda bho3 iti |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/2_bra/satapath/sb_10_u.txt",
    )

    assert result.text == (
        "vettha catvāri vratāni iti "
        "veda bho iti |\n"
    )

    assert len(
        result.normalized
    ) == 2

    assert not result.review


def test_verified_chandogya_hu3m_becomes_hum_long() -> None:
    original = (
        "paśyema tvā vayaṃ sāmrā "
        "hu3m ā iti |\n"
    )

    result = normalize_vedic_pluta(
        original,
        "1_veda/4_upa/chup___u.txt",
    )

    assert result.text == (
        "paśyema tvā vayaṃ sāmrā "
        "hūm ā iti |\n"
    )

    assert len(
        result.normalized
    ) == 1

    assert (
        result.normalized[0].rule
        == "verified_chup_hum_stobha"
    )

    assert not result.review

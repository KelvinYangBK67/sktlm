"""Minimal assert-based tests for tokenizer.normalize."""

from __future__ import annotations

from normalize import (
    normalize_text,
    normalize_unicode,
    remove_invisible_chars,
)


def test_nfc() -> None:
    assert normalize_unicode("e\u0301") == "é"


def test_remove_invisible_chars() -> None:
    assert normalize_text("अ\u200bग्नि") == "अग्नि"


def test_space_compression() -> None:
    assert normalize_text("राम  गच्छति") == "राम गच्छति"


def test_non_standard_spaces() -> None:
    assert normalize_text("राम\tगच्छति\u00a0वनम्\u3000इति") == "राम गच्छति वनम् इति"


def test_strip_line_edges() -> None:
    assert normalize_text("  रामः  \n  गच्छति  ") == "रामः\nगच्छति"


def test_single_newline_preserved() -> None:
    assert normalize_text("रामः\nगच्छति") == "रामः\nगच्छति"


def test_multiple_blank_lines_collapsed() -> None:
    assert normalize_text("रामः\n\n\n\nगच्छति") == "रामः\n\nगच्छति"


def test_single_danda_spacing() -> None:
    assert normalize_text("रामः  ।   गच्छति") == "रामः। गच्छति"


def test_ascii_single_danda() -> None:
    assert normalize_text("रामः |") == "रामः।"


def test_ascii_double_danda() -> None:
    assert normalize_text("रामः ||") == "रामः॥"


def test_ascii_double_danda_numbering() -> None:
    assert normalize_text("रामः ||०||") == "रामः॥"


def test_ascii_danda_paragraph_example() -> None:
    text = (
        "नारायणं नमस्कृत्य नरं चैव नरोत्तमम् |\n"
        "देवीं सरस्वतीं चैव ततो जयमुदीरयेत् ||०||"
    )
    expected = (
        "नारायणं नमस्कृत्य नरं चैव नरोत्तमम्।\n"
        "देवीं सरस्वतीं चैव ततो जयमुदीरयेत्॥"
    )
    assert normalize_text(text) == expected


def test_double_danda_at_end() -> None:
    assert normalize_text("रामः॥") == "रामः॥"


def test_double_danda_before_newline() -> None:
    assert normalize_text("रामः॥\nगच्छति") == "रामः॥\nगच्छति"


def test_double_danda_numbering_without_space() -> None:
    assert normalize_text("रामः॥२३॥") == "रामः॥"


def test_double_danda_numbering_with_space() -> None:
    assert normalize_text("रामः॥ २३ ॥") == "रामः॥"


def test_double_danda_numbering_with_many_spaces() -> None:
    assert normalize_text("रामः॥   २३॥") == "रामः॥"


def test_double_danda_numbering_one_digit_removed() -> None:
    assert normalize_text("रामः॥ २॥") == "रामः॥"


def test_double_danda_newline_gets_no_space() -> None:
    assert normalize_text("रामः॥\n") == "रामः॥"


def test_double_danda_breaks_body_text() -> None:
    assert normalize_text("रामः ॥ गच्छति") == "रामः॥\nगच्छति"


def test_avagraha_preserved() -> None:
    assert normalize_text("सोऽहम्") == "सोऽहम्"


def test_western_punctuation() -> None:
    assert normalize_text("रामः, गच्छति: वनम्!") == "रामः गच्छति वनम्।"


def test_arabic_digits_to_devanagari() -> None:
    assert normalize_text("अध्याय 12 ३") == "अध्याय"


def test_arabic_digits_removed() -> None:
    assert normalize_text("रामः 123 गच्छति") == "रामः गच्छति"


def test_devanagari_digits_removed() -> None:
    assert normalize_text("रामः १२३ गच्छति") == "रामः गच्छति"


def test_non_devanagari_noise_removed() -> None:
    assert normalize_text("रामः abc @@@ गच्छति") == "रामः गच्छति"


def test_editorial_layout_noise() -> None:
    assert normalize_text("12\n[रामः]* गच्छति¹\nfooter 3") == "रामः गच्छति"


def test_structural_number_after_title_is_removed() -> None:
    assert normalize_text("अनुक्रमणीपर्व\n१") == "अनुक्रमणीपर्व"


def test_structural_number_after_section_is_removed() -> None:
    assert normalize_text("अध्याय\n२") == "अध्याय"


def test_standalone_page_number_still_removed() -> None:
    assert normalize_text("१२\nरामः") == "रामः"


def test_layout_numbering_line_removed() -> None:
    assert normalize_text("रामः\n६। ७३\nगच्छति") == "रामः\nगच्छति"


def test_body_single_danda_preserved() -> None:
    assert normalize_text("रामः। गच्छति") == "रामः। गच्छति"


def test_body_double_danda_preserved() -> None:
    assert normalize_text("रामः॥\nगच्छति") == "रामः॥\nगच्छति"


def test_standalone_single_danda_line_removed() -> None:
    assert normalize_text("रामः\n।\nगच्छति") == "रामः\nगच्छति"


def test_standalone_double_danda_line_removed() -> None:
    assert normalize_text("रामः\n॥\nगच्छति") == "रामः\nगच्छति"


def test_only_standalone_danda_becomes_empty() -> None:
    assert normalize_text("।\n॥") == ""


def test_trailing_percent_file_name_removed() -> None:
    assert normalize_text("रामः\n% File name : mbh01.txt") == "रामः"


def test_trailing_encoding_removed() -> None:
    assert normalize_text("रामः\nEncoding: ISCII") == "रामः"


def test_trailing_electronic_text_removed() -> None:
    assert normalize_text("रामः\nElectronic text prepared in 1999") == "रामः"


def test_trailing_url_removed() -> None:
    assert normalize_text("रामः\nhttp://example.org/source") == "रामः"


def test_trailing_timestamp_removed() -> None:
    assert normalize_text("रामः\n02/23/2025 03:52:33") == "रामः"


def test_devanagari_body_before_trailer_is_preserved() -> None:
    text = "रामः गच्छति।\nसीता पठति।\n% File name : sample.txt\nEncoding: ISCII"
    assert normalize_text(text) == "रामः गच्छति।\nसीता पठति।"


def run_tests() -> None:
    tests = [
        test_nfc,
        test_remove_invisible_chars,
        test_space_compression,
        test_non_standard_spaces,
        test_strip_line_edges,
        test_single_newline_preserved,
        test_multiple_blank_lines_collapsed,
        test_single_danda_spacing,
        test_ascii_single_danda,
        test_ascii_double_danda,
        test_ascii_double_danda_numbering,
        test_ascii_danda_paragraph_example,
        test_double_danda_at_end,
        test_double_danda_before_newline,
        test_double_danda_numbering_without_space,
        test_double_danda_numbering_with_space,
        test_double_danda_numbering_with_many_spaces,
        test_double_danda_numbering_one_digit_removed,
        test_double_danda_newline_gets_no_space,
        test_double_danda_breaks_body_text,
        test_avagraha_preserved,
        test_western_punctuation,
        test_arabic_digits_to_devanagari,
        test_arabic_digits_removed,
        test_devanagari_digits_removed,
        test_non_devanagari_noise_removed,
        test_editorial_layout_noise,
        test_structural_number_after_title_is_removed,
        test_structural_number_after_section_is_removed,
        test_standalone_page_number_still_removed,
        test_layout_numbering_line_removed,
        test_body_single_danda_preserved,
        test_body_double_danda_preserved,
        test_standalone_single_danda_line_removed,
        test_standalone_double_danda_line_removed,
        test_only_standalone_danda_becomes_empty,
        test_trailing_percent_file_name_removed,
        test_trailing_encoding_removed,
        test_trailing_electronic_text_removed,
        test_trailing_url_removed,
        test_trailing_timestamp_removed,
        test_devanagari_body_before_trailer_is_preserved,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} normalization tests passed.")


if __name__ == "__main__":
    run_tests()

from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.tokenizer_final import (
    AGP,
    ANANDK,
    BRHAJJ,
    KAUSSU,
    SS2,
    VAIMP,
    audit_single_letters,
    clean_editorial_text,
)


def test_kaussu_removes_complete_division_suffix_only() -> None:
    text = "saṃskṛtam sūtra division emended |\n"
    cleaned, details = clean_editorial_text(relative=KAUSSU, text=text)
    assert cleaned == "saṃskṛtam |\n"
    assert len(details) == 1
    assert details[0].occurrence_count == 2
    assert details[0].action == "remove_editorial_suffix"


def test_agp_removes_only_standalone_chapter_lines() -> None:
    text = "chapter\n\nchapter |\n\nchaptera ḷkāra ḹ\n"
    cleaned, details = clean_editorial_text(relative=AGP, text=text)
    assert cleaned == "chaptera ḷkāra ḹ\n"
    assert len(details) == 2
    assert all(row.removed_line_count == 1 for row in details)


def test_confirmed_apparatus_lines_are_deleted_as_units() -> None:
    vaimp = "edition | vṛṣabhāyai | eds || vṛṣahāyai\nsaṃskṛtam\n"
    cleaned, details = clean_editorial_text(relative=VAIMP, text=vaimp)
    assert cleaned == "saṃskṛtam\n"
    assert details[0].rule == "vaimp_edition_apparatus_line"

    ss2 = "variant | sanandanādyair munibhir vibhāvyam |\nsaṃskṛtam\n"
    cleaned, details = clean_editorial_text(relative=SS2, text=ss2)
    assert cleaned == "saṃskṛtam\n"
    assert details[0].removed_line_count == 1


def test_anandk_preserves_sanskrit_head_and_deletes_english_head() -> None:
    text = (
        "pattraṭālaka || phys | properties\n\n"
        "sea salt || medic | properties\n"
    )
    cleaned, details = clean_editorial_text(relative=ANANDK, text=text)
    assert cleaned == "pattraṭālaka\n\n"
    assert [row.action for row in details] == [
        "remove_metadata_tail",
        "delete_line",
    ]


def test_repeated_a_junk_is_deleted() -> None:
    cleaned, details = clean_editorial_text(
        relative=BRHAJJ, text="aaaaaaaaaaaaaaaaa\n\nsaṃskṛtam\n"
    )
    assert cleaned == "saṃskṛtam\n"
    assert details[0].rule == "brhajj_repeated_a_junk"


def test_single_letter_audit_observes_token_boundaries_and_avagraha(
    tmp_path: Path,
) -> None:
    root = tmp_path / "canonical"
    source = root / "sample.txt"
    source.parent.mkdir(parents=True)
    source.write_text(
        "a ā | k || ṃ ḥ\nai au kh gh\ne'va ' a\n",
        encoding="utf-8",
    )
    details_path = tmp_path / "details.tsv"
    summary_path = tmp_path / "summary.tsv"
    by_file_path = tmp_path / "by_file.tsv"
    details, summary, _by_file = audit_single_letters(
        canonical_root=root,
        details_path=details_path,
        summary_path=summary_path,
        by_file_path=by_file_path,
    )
    assert [row["token"] for row in details] == ["a", "a", "k", "ā", "ḥ", "ṃ"]
    assert all(row["token"] not in {"ai", "au", "kh", "gh", "e"} for row in details)
    assert {row["token"]: row["total_count"] for row in summary}["a"] == 2
    with details_path.open(encoding="utf-8", newline="") as handle:
        assert csv.DictReader(handle, delimiter="\t").fieldnames == [
            "file",
            "line_no",
            "token",
            "context",
            "prev_line",
            "next_line",
        ]

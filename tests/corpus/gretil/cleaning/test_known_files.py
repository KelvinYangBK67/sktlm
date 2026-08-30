from pathlib import Path

from sktlm.corpus.gretil.cleaning.source_specific.known_files import (
    build_cleanup,
    clean_document,
)


def clean(text: str, path: str) -> tuple[str, list]:
    return clean_document(text, path=path)


def test_internal_single_danda_policy_is_path_scoped() -> None:
    output, changes = clean(
        "atha | madhyam | iti ||\nantaḥ |",
        "4_rellit/buddh/udanav_u.txt",
    )
    assert output == "atha   madhyam   iti ||\nantaḥ |"
    assert len(changes) == 2

    untouched, no_changes = clean(
        "atha | madhyam | iti ||",
        "6_sastra/8_jyot/aryabh_u.txt",
    )
    assert untouched == "atha | madhyam | iti ||"
    assert no_changes == []


def test_buddhist_wrappers_and_locators_preserve_body() -> None:
    output, _ = clean(
        "| sūtram |\n|| ślokam ||",
        "4_rellit/buddh/vinsutru.txt",
    )
    assert output == "sūtram\n|| ślokam ||"

    output, _ = clean(
        "(Pravr-v II): ||| .ṭ. m iti | sa kathayati",
        "4_rellit/buddh/vinv01_u.txt",
    )
    assert output == "iti | sa kathayati"

    output, _ = clean(
        "Var-v § 1.1.a buddho bhagavān\nVar-v § a pañcabhiḥ",
        "4_rellit/buddh/vinv04_u.txt",
    )
    assert output == "buddho bhagavān\npañcabhiḥ"


def test_tibetan_segments_are_removed_without_losing_sanskrit() -> None:
    output, changes = clean(
        "rkyen dman pa gaṅ źe na | ātmasampat parasampat ||\n"
        "saddharmadeśanā [de'i phyir dam pa'i chos] iti |",
        "4_rellit/buddh/srabhu_u.txt",
    )
    assert "rkyen" not in output
    assert "de'i" not in output
    assert "ātmasampat parasampat" in output
    assert "saddharmadeśanā" in output
    assert changes


def test_short_tibetan_segments_and_pure_locator_rows_are_removed() -> None:
    output, _ = clean(
        "saddharma [bskal pa graṅs med pa gsum gyis tha maḥi lus phyi ma] iti\n"
        "de dag thams cad mdor bsdus te || rigs kyi sar ni śes par bya ||)\n"
        "||||| bag yod par spyod la |||||| de ltar rtog par byed ciṅ ||||||||||\n"
        "(I)-C-IIl-4-a- -ii\n",
        "4_rellit/buddh/srabhu_u.txt",
    )
    assert "saddharma" in output
    assert "bskal" not in output
    assert "thams" not in output
    assert "spyod" not in output
    assert "IIl-4" not in output


def test_document_units_and_apparatus_are_removed_as_units() -> None:
    output, _ = clean(
        "This edition is [Vṛ. adds: saṃskṛtam | end Vṛ.] body\n"
        "citation [BhP 1.2.3]",
        "4_rellit/vaisn/ss4_krsu.txt",
    )
    assert "adds" not in output
    assert "saṃskṛtam" not in output
    assert "[BhP 1.2.3]" in output

    output, _ = clean(
        "[Vṛ. adds: saṃskṛtam [BhP 1.2.3] iti | end Vṛ.] body",
        "4_rellit/vaisn/ss4_krsu.txt",
    )
    assert output == " body"

    output, _ = clean(
        "before\n[Vṛ. adds here:] saṃskṛtam\n[BhP 1.2.3] iti\n"
        "[end Vṛ. addition.]\nafter",
        "4_rellit/vaisn/ss4_krsu.txt",
    )
    assert output == "before\n\n\n\nafter"

    output, _ = clean(
        "prefix [Vṛ. reads here: variant\n[end Vṛ. addition] suffix\n"
        "text (page\n15)-body",
        "4_rellit/vaisn/ss4_krsu.txt",
    )
    assert output == "prefix \n suffix\ntext \n-body"

    output, _ = clean(
        "prefix [Vṛ.\n\nadds: variant\n[end Vṛ. addition]\nafter",
        "4_rellit/vaisn/ss4_krsu.txt",
    )
    assert output == "prefix \n\n\n\nafter"

    output, _ = clean(
        "upanayanādhyāyaḥ\nśāstraṃ *vāggmī[K.vāgmī] iti\n[K.ca] body",
        "6_sastra/8_jyot/brhats_u.txt",
    )
    assert "[K." not in output
    assert "vāggmī" in output
    assert "body" in output


def test_residual_locator_variants_and_english_rows_close() -> None:
    output, _ = clean(
        "(Poṣ-v 458) Poṣ-v 85.1.b. sūtroddeśam\n",
        "4_rellit/buddh/vinv02_u.txt",
    )
    assert "Poṣ-v" not in output
    assert "sūtroddeśam" in output

    output, _ = clean(
        "(Pravā-v\nFor Pravā-v 7 the Sanskrit text is lost.\n"
        "body (Pravā-v 159) text",
        "4_rellit/buddh/vinv03_u.txt",
    )
    assert "Pravā-v" not in output
    assert "body  text" in output

    output, _ = clean(
        "Pāṇḍ v § first\nPāṇḍ v second",
        "4_rellit/buddh/vinv11_u.txt",
    )
    assert output == "first\nsecond"

    output, _ = clean(
        "sūtram [R omits line] iti",
        "4_rellit/buddh/vinsutru.txt",
    )
    assert output == "sūtram  iti"

    output, _ = clean(
        "Input by Andreas Bigger\nPLAIN TEXT VERSION\n###\nsaṃskṛtam",
        "5_poetry/4_narr/brkas_pu.txt",
    )
    assert output == "\n\n\nsaṃskṛtam"

    output, _ = clean(
        "Verses found in Arjunavarmadeva's version not found here\nślokaḥ",
        "5_poetry/2_kavya/amaru_u.txt",
    )
    assert output == "\nślokaḥ"


def test_source_grammar_and_segmentation_rules_preserve_lemmas() -> None:
    output, _ = clean(
        r"Ap1.1.1.12| [īpset[\āp, des.opt.] | atha ||",
        "6_sastra/4_dharma/sutra/apastd_u.txt",
    )
    assert "opt" not in output
    assert "īpset" in output
    assert output.endswith("atha ||")

    output, _ = clean(
        "Va.1.7 a.gṛhyamāṇa.kāraṇas^dharmas^||",
        "6_sastra/4_dharma/sutra/vasist_u.txt",
    )
    assert output == "a gṛhyamāṇa kāraṇas dharmas ||"


def test_pratyabu_soft_wrap_and_notes_tail() -> None:
    text = "mahāphalatva.=\n\nm\n\nca abhivyaṅktum\n\nNOTES\n\nEnglish note"
    output, changes = clean(text, "6_sastra/3_phil/saiva/pratyabu.txt")
    assert "mahāphalatvam" in output
    assert "\nm\n" not in output
    assert "English note" not in output
    assert any(
        change.rule == "quoted_printable_split_letter_rejoined"
        for change in changes
    )


def test_isvskaru_removes_witness_rows_and_word_index() -> None:
    output, _ = clean(
        "duḥkha-trayābhighātāj jijñāsā\n"
        "abhi M, G(A, D, G); ava J, S\n"
        "The words of the Sāṃkhya-kārikā\n"
        "a-karaṇa\n",
        "6_sastra/3_phil/samkhya/isvskaru.txt",
    )
    assert "duḥkha" in output
    assert "abhi M" not in output
    assert "a-karaṇa" not in output


def test_build_cleanup_copies_non_targets_and_writes_evidence(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    raw_root = tmp_path / "raw"
    output_root = tmp_path / "output"
    report_dir = tmp_path / "reports"
    target = input_root / "3_purana" / "sivap1_u.txt"
    other = input_root / "misc" / "other.txt"
    raw_target = raw_root / "3_purana" / "sivap1_u.htm"
    target.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    raw_target.parent.mkdir(parents=True)
    target.write_text("Chapter\n\nśivaḥ ||", encoding="utf-8")
    other.write_text("unchanged\n", encoding="utf-8")
    raw_target.write_text("<html>raw</html>", encoding="utf-8")

    result = build_cleanup(
        input_root=input_root,
        raw_root=raw_root,
        output_root=output_root,
        report_dir=report_dir,
        require_all_targets=False,
    )

    assert result.files_changed == 1
    assert (output_root / "3_purana" / "sivap1_u.txt").read_text(
        encoding="utf-8"
    ) == "\n\nśivaḥ ||"
    assert (output_root / "misc" / "other.txt").read_bytes() == other.read_bytes()
    assert (report_dir / "known_file_cleanup_occurrences.csv").is_file()
    assert (
        report_dir / "diffs" / "3_purana" / "sivap1_u.txt.diff"
    ).is_file()

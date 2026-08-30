from __future__ import annotations

import csv
from pathlib import Path

from sktlm.corpus.gretil.cleaning.editorial import (
    build_pass2_candidate,
    clean_document,
)


def _clean(text: str) -> str:
    return clean_document(text, 'example.txt').text


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


def test_full_line_dotted_locator_removed() -> None:
    assert _clean('2.1.4.\nrāmaḥ |\n') == '\nrāmaḥ |\n'


def test_full_line_bracketed_numeric_locator_removed() -> None:
    assert _clean('1.1.3[[.]]5\n1.4.3[.1]0\n') == '\n\n'


def test_bare_number_not_removed() -> None:
    assert _clean('31\n') == '31\n'


def test_leading_dotted_locator_removed() -> None:
    assert _clean('11.7.4.2prajāpatir ha vai |\n') == 'prajāpatir ha vai |\n'


def test_midline_dotted_locator_removed() -> None:
    assert _clean('aśvānavaghrāpayati 5.1.5.tadyadājiṃ dhāvanti |\n') == (
        'aśvānavaghrāpayati tadyadājiṃ dhāvanti |\n'
    )


def test_double_danda_verse_number_removed() -> None:
    assert _clean('agnim īḷe ||31|| iti |\n') == 'agnim īḷe || iti |\n'


def test_line_final_danda_number_removed() -> None:
    assert _clean('etābhir jayet |27\n') == 'etābhir jayet |\n'


def test_leading_parenthesized_locator_removed() -> None:
    assert _clean('(1.9) āgnīdhrasyottarata upācāraḥ |\n') == (
        'āgnīdhrasyottarata upācāraḥ |\n'
    )


def test_general_parenthesis_preserved() -> None:
    assert _clean('atha (agnyādhāna) karma |\n') == 'atha (agnyādhāna) karma |\n'


def test_editorial_square_removed() -> None:
    assert _clean('rāmaḥ [lacuna] gacchati |\n') == 'rāmaḥ gacchati |\n'
    assert _clean('rāmaḥ [thus with Caland, AZ p. 55, n. 5] gacchati |\n') == (
        'rāmaḥ gacchati |\n'
    )
    assert _clean('rāmaḥ [Bhattacharyya edits bhujagainava] gacchati |\n') == (
        'rāmaḥ gacchati |\n'
    )


def test_numeric_editorial_square_removed() -> None:
    assert _clean(
        'āhṛte anne [19.52.1, sakala follows thus PS 1.30.5] ity etayā |\n'
    ) == 'āhṛte anne ity etayā |\n'


def test_citation_only_square_removed() -> None:
    assert _clean(
        'suvīryam [.RV 5.13.5c; 8.98.12c; ;SS 20.108.3c] iti |\n'
    ) == 'suvīryam iti |\n'


def test_sanskrit_square_content_preserved() -> None:
    original = 'rāmaḥ [yad ucchiṣṭam] gacchati |\n'
    assert _clean(original) == original


def test_tibetan_square_content_preserved() -> None:
    original = "rāmaḥ [bskal pa graṅs med pa gsum] gacchati |\n"
    assert _clean(original) == original


def test_metadata_line_removed() -> None:
    assert _clean('date: fri, jul 1996 -0600\nrāmaḥ |\n') == '\nrāmaḥ |\n'
    assert _clean('-version: 1.0status: rokṣ-status:\nrāmaḥ |\n') == '\nrāmaḥ |\n'


def test_percent_note_is_not_generic_pass2() -> None:
    original = '% note PS mantra in pratīka?\n'
    assert _clean(original) == original


def test_standalone_known_siglum_locator_removed() -> None:
    assert _clean('JaimGS 1.20:\nrāmaḥ |\n') == '\nrāmaḥ |\n'


def test_unknown_heading_not_removed() -> None:
    original = 'Chapter 1.20:\n'
    assert _clean(original) == original


def test_hv_suffix_removed_only_after_verse_text() -> None:
    original = 'raver gativiśeṣeṇa nityaśaḥ || **HV App.I,2.7**1:1 ||\n'
    assert _clean(original) == 'raver gativiśeṣeṇa nityaśaḥ ||\n'


def test_hv_speaker_metadata_line_not_mangled() -> None:
    original = '{{vahnir uvāca} **HV App.I,18.748**78:4}\n'
    assert _clean(original) == original


def test_general_punctuation_untouched() -> None:
    original = "kule-kule, viris.yate; anyo-'nyaḥ: iti |\n"
    assert _clean(original) == original


def test_pluta_like_forms_untouched_by_pass2() -> None:
    original = 'ā3 o3m a3 i3 |\n'
    assert _clean(original) == original


def test_candidate_build_preserves_untouched_file_bytes(tmp_path: Path) -> None:
    input_root = tmp_path / 'input'
    output_root = tmp_path / 'output'
    report_dir = tmp_path / 'reports'

    source = input_root / 'clean.txt'
    _write(source, 'rāmaḥ gacchati |\n')
    before = source.read_bytes()

    result = build_pass2_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_processed == 1
    assert result.files_changed == 0
    assert (output_root / 'clean.txt').read_bytes() == before
    assert source.read_bytes() == before


def test_candidate_build_writes_audit_and_occurrences(tmp_path: Path) -> None:
    input_root = tmp_path / 'input'
    output_root = tmp_path / 'output'
    report_dir = tmp_path / 'reports'

    _write(input_root / 'x.txt', '(1.9) rāmaḥ [lacuna] gacchati ||31||\n')

    result = build_pass2_candidate(
        input_root=input_root,
        output_root=output_root,
        report_dir=report_dir,
    )

    assert result.files_changed == 1
    assert result.total_changes == 3
    assert (output_root / 'x.txt').read_text(encoding='utf-8') == 'rāmaḥ gacchati ||\n'

    audit = report_dir / 'gretil_canonical_pass2_cleaning_audit.csv'
    occurrences = report_dir / 'gretil_canonical_pass2_occurrences.csv'
    summary = report_dir / 'gretil_canonical_pass2_summary.txt'
    assert audit.is_file()
    assert occurrences.is_file()
    assert summary.is_file()

    with occurrences.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert {row['rule'] for row in rows} == {
        'leading_parenthesized_locator_removed',
        'square_editorial_removed',
        'double_danda_number_removed',
    }

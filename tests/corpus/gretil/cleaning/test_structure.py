from sktlm.corpus.gretil.cleaning.structure import (
    SANKHARU_PATH,
    SANKHARU_TITLE,
    clean_document,
)


def test_sankharu_title_and_sigla_are_deleted_not_lowercased() -> None:
    siglum = '\u015a\u0100'
    text = '\n'.join(
        [
            SANKHARU_TITLE,
            '',
            siglum,
            '',
            'praj\u0101patir vai |',
            '',
            siglum + ' = KU',
            '',
        ]
    )
    output, changes = clean_document(text, path=SANKHARU_PATH)
    assert SANKHARU_TITLE not in output
    assert siglum not in output
    assert 'praj\u0101patir vai |' in output
    assert [change['rule'] for change in changes].count(
        'sankharu_standalone_siglum_removed'
    ) == 2


def test_repeated_running_header_is_removed_but_body_is_retained() -> None:
    header = 'V\u0101r\u0101hag\u1e5bhyas\u016btra,'
    text = '\n'.join([header, '', 'agnir vai |', '', header, ''])
    output, changes = clean_document(text, path='example.txt')
    assert header not in output
    assert 'agnir vai |' in output
    assert any(
        change['rule'] == 'repeated_running_header_or_abbreviation_removed'
        for change in changes
    )

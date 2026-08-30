from sktlm.corpus.gretil.cleaning.finalize import clean_document, clean_line
from sktlm.corpus.gretil.cleaning.strict import (
    ALLOWED_CHARACTERS,
    is_valid_avagraha,
)


def test_projection_lowercases_body_and_resolves_punctuation_and_hyphens() -> None:
    apostrophe = chr(39)
    source = 'Devo ' + apostrophe + 'pi, agni-k\u0101ryam | 01nara\u1e25'
    output, counts = clean_line(source)
    assert 'devo ' + apostrophe + 'pi' in output
    assert 'agnik\u0101ryam' in output
    assert 'nara\u1e25' in output
    assert '-' not in output
    assert ',' not in output
    assert counts['textual_sanskrit_uppercase_lowered'] == 1


def test_projection_removes_editorial_unit_instead_of_mapping_its_content() -> None:
    apostrophe = chr(39)
    source = (
        'r\u0101ma | English apparatus qxz 12 | devo '
        + apostrophe
        + 'pi |'
    )
    output, _, _ = clean_document(source)
    assert 'english' not in output
    assert 'qxz' not in output
    assert 'r\u0101ma' in output
    assert 'devo ' + apostrophe + 'pi' in output


def test_projection_emits_only_strict_characters_and_valid_avagraha() -> None:
    apostrophe = chr(39)
    source = (
        '\u015aivo ' + apostrophe + 'pi; r\u0101ma\u1e25 (variant 12) '
        '[ed. X] agni-k\u0101ryam\r\n'
    )
    output, _, _ = clean_document(source)
    assert all(character in ALLOWED_CHARACTERS for character in output)
    for index, character in enumerate(output):
        if character == apostrophe:
            assert is_valid_avagraha(output, index)


def test_compact_leading_edition_locator_is_removed_without_body_loss() -> None:
    source = 'Va.1.1 atha^atas^puru\u1e63a.ni\u1e25\u015breyasam ||'
    output, _ = clean_line(source)
    assert 'va' not in output.split()
    assert 'atha atas puru\u1e63a' in output
    assert output.endswith('||')

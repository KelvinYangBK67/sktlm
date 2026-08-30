from pathlib import Path

import pytest

from sktlm.corpus.gretil.cleaning.strict import (
    is_valid_avagraha,
    validate_corpus,
)


def test_positive_avagraha_environment() -> None:
    apostrophe = chr(39)
    spaced = 'devo ' + apostrophe + 'pi |'
    joined = 'mano' + apostrophe + 'nus\u0101ri\u1e47a\u1e25'
    assert is_valid_avagraha(spaced, spaced.index(apostrophe))
    assert is_valid_avagraha(joined, joined.index(apostrophe))


def test_rare_vocalic_l_long_is_valid_lowercase_iast(tmp_path: Path) -> None:
    root = tmp_path / 'vocalic_l'
    root.mkdir()
    (root / 'ok.txt').write_text('k\u1e39pta\u1e25 |\n', encoding='utf-8', newline='')
    assert validate_corpus(input_root=root).is_clean


@pytest.mark.parametrize(
    'text',
    [
        chr(39) + 'r\u0101ma',
        'r\u0101ma ' + chr(39) + 'iti',
        'devo ' + chr(39) + chr(39) + 'pi',
        'devo ' + chr(39) + ' pi',
    ],
)
def test_non_avagraha_apostrophe_is_rejected(text: str) -> None:
    assert not is_valid_avagraha(text, text.index(chr(39)))


def test_strict_validator_requires_zero_characters_and_apostrophes(
    tmp_path: Path,
) -> None:
    root = tmp_path / 'clean'
    root.mkdir()
    apostrophe = chr(39)
    (root / 'ok.txt').write_text(
        'devo ' + apostrophe + 'pi |\n', encoding='utf-8', newline=''
    )
    result = validate_corpus(input_root=root)
    assert result.is_clean
    assert result.invalid_character_occurrences == 0
    assert result.invalid_apostrophe_occurrences == 0

    (root / 'bad.txt').write_text(
        'R\u0101ma ' + apostrophe + 'iti.\n', encoding='utf-8', newline=''
    )
    with pytest.raises(RuntimeError, match='invalid_characters=2'):
        validate_corpus(input_root=root)

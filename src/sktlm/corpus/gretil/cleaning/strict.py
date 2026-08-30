'''Strict final-corpus policy and validator for canonical GRETIL IAST.'''

from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMPLEMENTATION = 'gretil-strict-validator-1'
DEFAULT_INPUT_ROOT = Path('data/canonical/gretil_iast')
DEFAULT_REPORT_DIR = Path('reports/cleaning/generated/strict_validation')

# Exact lowercase code points used by the project's NFC IAST representation.
IAST_LOWER = frozenset(
    'a\u0101i\u012bu\u016b\u1e5b\u1e5d\u1e37\u1e39eo'
    'kg\u1e45cj\u00f1\u1e6d\u1e0d\u1e47tdnpbmyrlv\u015b\u1e63sh\u1e43\u1e25'
)
ALLOWED_CHARACTERS = IAST_LOWER | frozenset({chr(39), '|', ' ', '\n'})
AVAGRAHA_LEFT = frozenset('eo')


@dataclass(frozen=True, slots=True)
class StrictValidationResult:
    files_processed: int
    invalid_character_files: int
    invalid_character_occurrences: int
    invalid_apostrophe_files: int
    invalid_apostrophe_occurrences: int
    apostrophe_occurrences: int

    @property
    def is_clean(self) -> bool:
        return not (
            self.invalid_character_occurrences
            or self.invalid_apostrophe_occurrences
        )


def is_valid_avagraha(text: str, index: int) -> bool:
    '''Validate one apostrophe by a positive IAST avagraha environment.

    Avagraha records elided initial a after an e/o sandhi result. Spaces may
    occur before it, but validation never crosses LF or danda boundaries.
    '''

    apostrophe = chr(39)
    if index < 0 or index >= len(text) or text[index] != apostrophe:
        return False
    if (index and text[index - 1] == apostrophe) or (
        index + 1 < len(text) and text[index + 1] == apostrophe
    ):
        return False
    if index + 1 >= len(text) or text[index + 1] not in IAST_LOWER:
        return False
    left = index - 1
    while left >= 0 and text[left] == ' ':
        left -= 1
    return left >= 0 and text[left] in AVAGRAHA_LEFT


def _location(text: str, index: int) -> tuple[int, int, str]:
    line_number = text.count('\n', 0, index) + 1
    line_start = text.rfind('\n', 0, index) + 1
    column = index - line_start + 1
    context = text[max(0, index - 32) : index + 33]
    context = context.replace('\n', '\\n').replace('\r', '\\r')
    return line_number, column, context


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def validate_corpus(
    *,
    input_root: Path,
    report_dir: Path | None = None,
    require_clean: bool = True,
    example_limit: int = 2000,
) -> StrictValidationResult:
    '''Audit exact characters and apostrophe semantics, optionally failing.'''

    if not input_root.is_dir():
        raise FileNotFoundError(f'strict validation root does not exist: {input_root}')
    files = tuple(sorted(path for path in input_root.rglob('*.txt') if path.is_file()))
    if not files:
        raise RuntimeError(f'no .txt files found under: {input_root}')

    invalid_char_counts: Counter[str] = Counter()
    invalid_char_files: set[str] = set()
    invalid_apostrophe_files: set[str] = set()
    invalid_char_examples: list[dict[str, Any]] = []
    invalid_apostrophe_examples: list[dict[str, Any]] = []
    apostrophes = 0
    invalid_apostrophes = 0

    for path in files:
        relative = path.relative_to(input_root).as_posix()
        text = path.read_bytes().decode('utf-8')
        for index, character in enumerate(text):
            if character not in ALLOWED_CHARACTERS:
                invalid_char_counts[character] += 1
                invalid_char_files.add(relative)
                if len(invalid_char_examples) < example_limit:
                    line, column, context = _location(text, index)
                    invalid_char_examples.append(
                        {
                            'path': relative,
                            'line_number': line,
                            'column': column,
                            'character': character,
                            'codepoint': f'U+{ord(character):04X}',
                            'unicode_name': unicodedata.name(character, 'UNKNOWN'),
                            'context': context,
                        }
                    )
            if character == chr(39):
                apostrophes += 1
                if not is_valid_avagraha(text, index):
                    invalid_apostrophes += 1
                    invalid_apostrophe_files.add(relative)
                    if len(invalid_apostrophe_examples) < example_limit:
                        line, column, context = _location(text, index)
                        invalid_apostrophe_examples.append(
                            {
                                'path': relative,
                                'line_number': line,
                                'column': column,
                                'context': context,
                            }
                        )

    result = StrictValidationResult(
        files_processed=len(files),
        invalid_character_files=len(invalid_char_files),
        invalid_character_occurrences=sum(invalid_char_counts.values()),
        invalid_apostrophe_files=len(invalid_apostrophe_files),
        invalid_apostrophe_occurrences=invalid_apostrophes,
        apostrophe_occurrences=apostrophes,
    )

    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(
            report_dir / 'invalid_character_inventory.csv',
            ('character', 'codepoint', 'unicode_name', 'count'),
            [
                {
                    'character': character,
                    'codepoint': f'U+{ord(character):04X}',
                    'unicode_name': unicodedata.name(character, 'UNKNOWN'),
                    'count': count,
                }
                for character, count in sorted(
                    invalid_char_counts.items(),
                    key=lambda item: (-item[1], ord(item[0])),
                )
            ],
        )
        _write_csv(
            report_dir / 'invalid_character_examples.csv',
            (
                'path',
                'line_number',
                'column',
                'character',
                'codepoint',
                'unicode_name',
                'context',
            ),
            invalid_char_examples,
        )
        _write_csv(
            report_dir / 'invalid_apostrophe_examples.csv',
            ('path', 'line_number', 'column', 'context'),
            invalid_apostrophe_examples,
        )
        status = 'PASS' if result.is_clean else 'FAIL'
        summary = [
            'Formal GRETIL strict final validation',
            '======================================',
            f'implementation: {IMPLEMENTATION}',
            f'input_root: {input_root}',
            f'files_processed: {result.files_processed}',
            f'invalid_character_files: {result.invalid_character_files}',
            f'invalid_character_occurrences: {result.invalid_character_occurrences}',
            f'apostrophe_occurrences: {result.apostrophe_occurrences}',
            f'invalid_apostrophe_files: {result.invalid_apostrophe_files}',
            f'invalid_apostrophe_occurrences: {result.invalid_apostrophe_occurrences}',
            f'status: {status}',
            '',
            'policy:',
            '  exact lowercase NFC IAST code points only',
            '  ASCII apostrophe only in a positive e/o + elided-a environment',
            '  danda is ASCII |; the only whitespace is ASCII space and LF',
            '  combining accents, punctuation, digits, and editorial symbols are forbidden',
            '',
        ]
        (report_dir / 'strict_validation_summary.txt').write_text(
            '\n'.join(summary), encoding='utf-8', newline=''
        )

    if require_clean and not result.is_clean:
        raise RuntimeError(
            'strict canonical validation failed: '
            f'invalid_characters={result.invalid_character_occurrences}; '
            f'invalid_apostrophes={result.invalid_apostrophe_occurrences}'
        )
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Validate strict final GRETIL IAST')
    parser.add_argument('--input-root', type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument('--report-dir', type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args(argv)
    result = validate_corpus(
        input_root=args.input_root,
        report_dir=args.report_dir,
        require_clean=not args.audit_only,
    )
    print(f'files processed: {result.files_processed}')
    print(f'invalid characters: {result.invalid_character_occurrences}')
    print(f'invalid apostrophes: {result.invalid_apostrophe_occurrences}')


if __name__ == '__main__':
    main()

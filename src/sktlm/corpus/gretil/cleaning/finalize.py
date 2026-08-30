'''Project structure-cleaned GRETIL text into the strict final alphabet.'''

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sktlm.corpus.gretil.cleaning.strict import (
    ALLOWED_CHARACTERS,
    IAST_LOWER,
    is_valid_avagraha,
    validate_corpus,
)


IMPLEMENTATION = 'gretil-strict-final-projection-1'
DEFAULT_INPUT_ROOT = Path(
    'data/intermediate/gretil/document_structure_cleaned_gretil_iast'
)
DEFAULT_OUTPUT_ROOT = Path('data/intermediate/gretil/strict_final_candidate_gretil_iast')
DEFAULT_REPORT_DIR = Path('reports/cleaning/generated/strict_final_projection')

ROUND_RE = re.compile(r'\([^()\n]*\)')
CURLY_RE = re.compile(r'\{[^{}\n]*\}')
SQUARE_RE = re.compile(r'\[([^\[\]\n]*)\]')
ANGLE_RE = re.compile(r'<([^<>\n]*)>')
TOKEN_RE = re.compile(r'\S+')
HORIZONTAL_SPACE_RE = re.compile(r'[ \t\v\f\u00a0]+')
PIPE_RUN_RE = re.compile(r'\|{3,}')
SPACED_MULTI_PIPE_RE = re.compile(r' *(?:\| *){2,}')

EDITORIAL_WORD_RE = re.compile(
    r'\b(?:cf|corr|ed|edition|editor|emend|fol|ms|mss|note|read|reading|'
    r'variant|omitted|inserted|apparatus|colophon|page|line)\b',
    re.IGNORECASE,
)
HV_INLINE_SUFFIX_RE = re.compile(
    r'\s+@\s+\*{0,2}HV(?:\s+App\.)?[^\n]*$', re.IGNORECASE
)

SMART_APOSTROPHES = frozenset({'\u2018', '\u2019', '\u02bc', '\u02b9', '\u00b4', ''})
TEXTUAL_BOUNDARIES = frozenset(
    {'.', ',', ';', ':', '!', '?', '\u0964', '\u0965', '\u2024', '\u2026'}
)
SOURCE_FLAGS = frozenset({'+', '@', '%', '*'})
WORD_SEPARATORS = frozenset({'^'})
DELETE_MARKS = frozenset(
    {'[', ']', '{', '}', '(', ')', '<', '>', chr(34), '\u201c', '\u201d'}
)


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    files_processed: int
    files_changed: int
    input_chars: int
    output_chars: int
    apostrophes_retained: int
    invalid_apostrophes_removed: int
    rule_counts: Counter[str]


def _sub_count(
    pattern: re.Pattern[str],
    replacement: str | Callable[[re.Match[str]], str],
    text: str,
    rule: str,
    counts: Counter[str],
) -> str:
    output, number = pattern.subn(replacement, text)
    if number:
        counts[rule] += number
    return output


def _unit_is_editorial(content: str) -> bool:
    if any(character.isdigit() for character in content):
        return True
    if EDITORIAL_WORD_RE.search(content):
        return True
    if any(character in '=:@%*' for character in content):
        return True
    letters = [character for character in content if character.isalpha()]
    if letters and len(letters) <= 16 and all(character.isupper() for character in letters):
        return True
    return any(
        character.isalpha() and character.lower() not in IAST_LOWER
        for character in content
    )


def _remove_delimited_units(text: str, counts: Counter[str]) -> str:
    for _ in range(4):
        before = text
        text = _sub_count(
            ROUND_RE, '', text, 'round_editorial_unit_removed', counts
        )
        text = _sub_count(
            CURLY_RE, '', text, 'curly_apparatus_unit_removed', counts
        )

        def square(match: re.Match[str]) -> str:
            content = match.group(1)
            if _unit_is_editorial(content):
                counts['square_editorial_unit_removed'] += 1
                return ' '
            counts['square_text_delimiters_removed'] += 1
            return f' {content} '

        def angle(match: re.Match[str]) -> str:
            content = match.group(1)
            if _unit_is_editorial(content):
                counts['angle_editorial_unit_removed'] += 1
                return ' '
            counts['angle_text_delimiters_removed'] += 1
            return f' {content} '

        text = SQUARE_RE.sub(square, text)
        text = ANGLE_RE.sub(angle, text)
        if text == before:
            break
    return text


def _is_sanskrit_letter(character: str) -> bool:
    return character.lower() in IAST_LOWER


def _strip_numeric_affix(token: str) -> str | None:
    if not any(character.isdigit() for character in token):
        return token
    alpha_positions = [
        index for index, character in enumerate(token) if character.isalpha()
    ]
    if not alpha_positions:
        return None
    first = alpha_positions[0]
    last = alpha_positions[-1]
    middle = token[first : last + 1]
    prefix = token[:first]
    suffix = token[last + 1 :]
    if any(character.isdigit() for character in middle):
        return None
    if not all(_is_sanskrit_letter(character) for character in middle if character.isalpha()):
        return None
    # Va.1.2, CS.4 and similar compact edition locators are one structural
    # token. Do not preserve their alphabetic siglum as fake Sanskrit.
    if (
        first == 0
        and any(character.isdigit() for character in suffix)
        and len([character for character in middle if character.isalpha()]) <= 8
        and any(character.isupper() for character in middle)
    ):
        return None
    if any(character.isdigit() for character in prefix) and not any(
        character.isdigit() for character in suffix
    ):
        return token[first:]
    if any(character.isdigit() for character in suffix) and not any(
        character.isdigit() for character in prefix
    ):
        return token[: last + 1]
    return None


def _remove_numeric_tokens(segment: str, counts: Counter[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if not any(character.isdigit() for character in token):
            return token
        stripped = _strip_numeric_affix(token)
        if stripped is None:
            counts['numeric_structural_token_removed'] += 1
            return ' '
        counts['numeric_locator_affix_removed'] += 1
        return stripped

    return TOKEN_RE.sub(replace, segment)


def _remove_compact_sigla(segment: str, counts: Counter[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        letters = [character for character in token if character.isalpha()]
        uppercase = sum(character.isupper() for character in letters)
        if letters and len(letters) <= 12 and uppercase >= 2:
            counts['inline_edition_siglum_removed'] += 1
            return ' '
        return token

    return TOKEN_RE.sub(replace, segment)


def _lower_sanskrit(segment: str, counts: Counter[str]) -> str:
    output: list[str] = []
    for character in segment:
        if character.isupper() and character.lower() in IAST_LOWER:
            output.append(character.lower())
            counts['textual_sanskrit_uppercase_lowered'] += 1
        else:
            output.append(character)
    return ''.join(output)


def _project_characters(segment: str, counts: Counter[str]) -> str:
    output: list[str] = []
    for index, character in enumerate(segment):
        if character in IAST_LOWER or character in {' ', '|', chr(39)}:
            output.append(character)
        elif character in SMART_APOSTROPHES:
            output.append(chr(39))
            counts['apostrophe_candidate_ascii_normalized'] += 1
        elif character in TEXTUAL_BOUNDARIES:
            output.append('|')
            counts['textual_boundary_normalized'] += 1
        elif character == '-':
            left = segment[index - 1] if index else ''
            right = segment[index + 1] if index + 1 < len(segment) else ''
            if left and right and _is_sanskrit_letter(left) and _is_sanskrit_letter(right):
                counts['intra_lexical_hyphen_removed'] += 1
            else:
                output.append('|')
                counts['structural_hyphen_to_boundary'] += 1
        elif character in SOURCE_FLAGS:
            counts['source_separator_removed'] += 1
        elif character in WORD_SEPARATORS:
            output.append(' ')
            counts['source_word_separator_normalized'] += 1
        elif character in DELETE_MARKS:
            counts['editorial_delimiter_removed'] += 1
        elif unicodedata.category(character).startswith('M'):
            counts['combining_accent_removed'] += 1
        elif character.isspace():
            output.append(' ')
            counts['non_ascii_space_normalized'] += 1
        elif unicodedata.category(character)[0] in {'P', 'S'}:
            output.append('|')
            counts['residual_symbol_to_boundary'] += 1
        else:
            counts['residual_control_removed'] += 1
    return ''.join(output)


def _remove_invalid_apostrophes(text: str, counts: Counter[str]) -> str:
    output: list[str] = []
    for index, character in enumerate(text):
        if character == chr(39) and not is_valid_avagraha(text, index):
            counts['non_avagraha_apostrophe_removed'] += 1
        else:
            output.append(character)
    return ''.join(output)


def _clean_segment(segment: str, counts: Counter[str]) -> str:
    had_digits = any(character.isdigit() for character in segment)
    segment = _remove_delimited_units(segment, counts)
    segment, suffixes = HV_INLINE_SUFFIX_RE.subn('', segment)
    if suffixes:
        counts['harivamsa_inline_locator_suffix_removed'] += suffixes
    segment = _remove_numeric_tokens(segment, counts)
    segment = _remove_compact_sigla(segment, counts)

    if had_digits:
        compact_upper = any(
            token
            and len([character for character in token if character.isalpha()]) <= 4
            and any(character.isupper() for character in token)
            for token in TOKEN_RE.findall(segment)
        )
        if compact_upper:
            counts['digit_bearing_apparatus_segment_removed'] += 1
            return ''

    segment = _lower_sanskrit(segment, counts)
    if any(character.isdigit() for character in segment):
        counts['residual_digit_segment_removed'] += 1
        return ''
    if any(
        character.isalpha() and character not in IAST_LOWER
        for character in segment
    ):
        counts['non_iast_editorial_segment_removed'] += 1
        return ''

    segment = _project_characters(segment, counts)
    segment = HORIZONTAL_SPACE_RE.sub(' ', segment).strip()
    segment = _remove_invalid_apostrophes(segment, counts)
    segment = HORIZONTAL_SPACE_RE.sub(' ', segment).strip()
    return segment


def clean_line(line: str) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()
    line = unicodedata.normalize('NFC', line)
    segments = [_clean_segment(segment, counts) for segment in line.split('|')]
    output = '|'.join(segments)
    output = PIPE_RUN_RE.sub('||', output)
    output = SPACED_MULTI_PIPE_RE.sub(' || ', output)
    output = re.sub(r'(?<!\|) *\| *(?!\|)', ' | ', output)
    output = HORIZONTAL_SPACE_RE.sub(' ', output).strip()
    output = _remove_invalid_apostrophes(output, counts)
    output = HORIZONTAL_SPACE_RE.sub(' ', output).strip()
    return output, counts


def clean_document(text: str) -> tuple[str, Counter[str], list[dict[str, Any]]]:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    output_lines: list[str] = []
    totals: Counter[str] = Counter()
    changes: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.split('\n'), start=1):
        cleaned, counts = clean_line(line)
        output_lines.append(cleaned)
        totals.update(counts)
        if cleaned != line:
            changes.append(
                {
                    'line_number': line_number,
                    'rules': ';'.join(
                        f'{rule}={count}' for rule, count in sorted(counts.items())
                    ),
                    'before': line,
                    'after': cleaned,
                }
            )
    output = '\n'.join(output_lines)
    if any(character not in ALLOWED_CHARACTERS for character in output):
        raise RuntimeError('projection emitted a character outside the strict alphabet')
    for index, character in enumerate(output):
        if character == chr(39) and not is_valid_avagraha(output, index):
            raise RuntimeError('projection emitted an invalid apostrophe')
    return output, totals, changes


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def build_projection(
    *, input_root: Path, output_root: Path, report_dir: Path
) -> ProjectionResult:
    if not input_root.is_dir():
        raise FileNotFoundError(f'projection input root does not exist: {input_root}')
    if input_root.resolve() == output_root.resolve():
        raise ValueError('input_root and output_root must differ')
    if output_root.exists():
        raise FileExistsError(f'projection output root already exists: {output_root}')
    files = tuple(sorted(path for path in input_root.rglob('*.txt') if path.is_file()))
    if not files:
        raise RuntimeError(f'no .txt files found under: {input_root}')

    output_root.mkdir(parents=True)
    totals: Counter[str] = Counter()
    files_changed = 0
    input_chars = 0
    output_chars = 0
    file_rows: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []

    for source in files:
        relative = source.relative_to(input_root).as_posix()
        text = source.read_bytes().decode('utf-8')
        output, counts, changes = clean_document(text)
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output, encoding='utf-8', newline='')
        input_chars += len(text)
        output_chars += len(output)
        totals.update(counts)
        files_changed += int(output != text)
        file_rows.append(
            {
                'path': relative,
                'changed': int(output != text),
                'input_chars': len(text),
                'output_chars': len(output),
                'char_delta': len(output) - len(text),
                'changed_lines': len(changes),
            }
        )
        change_rows.extend({'path': relative, **change} for change in changes)

    validation = validate_corpus(
        input_root=output_root,
        report_dir=report_dir / 'validation',
        require_clean=True,
    )
    _write_csv(
        report_dir / 'strict_projection_files.csv',
        ('path', 'changed', 'input_chars', 'output_chars', 'char_delta', 'changed_lines'),
        file_rows,
    )
    _write_csv(
        report_dir / 'strict_projection_changes.csv',
        ('path', 'line_number', 'rules', 'before', 'after'),
        change_rows,
    )
    removed_apostrophes = totals['non_avagraha_apostrophe_removed']
    summary = [
        'Formal GRETIL strict final projection',
        '=====================================',
        f'implementation: {IMPLEMENTATION}',
        f'input_root: {input_root}',
        f'output_root: {output_root}',
        f'files_processed: {len(files)}',
        f'files_changed: {files_changed}',
        f'input_chars: {input_chars}',
        f'output_chars: {output_chars}',
        f'char_delta: {output_chars - input_chars}',
        f'apostrophes_retained: {validation.apostrophe_occurrences}',
        f'invalid_apostrophes_removed: {removed_apostrophes}',
        'invalid_character_occurrences: 0',
        'invalid_apostrophe_occurrences: 0',
        '',
        'rule totals:',
        *(f'  {rule}: {count}' for rule, count in sorted(totals.items())),
        '',
        'projection policy:',
        '  structural/editorial units are deleted before character projection',
        '  uppercase Sanskrit in surviving text is lowercased; compact sigla are deleted',
        '  punctuation carrying a textual boundary becomes |',
        '  intralexical hyphens and source flags are removed without inventing danda',
        '  digit/non-IAST apparatus is removed as a token or danda-delimited unit',
        '  only positive e/o avagraha contexts retain ASCII apostrophe',
        '',
    ]
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'strict_projection_summary.txt').write_text(
        '\n'.join(summary), encoding='utf-8', newline=''
    )
    return ProjectionResult(
        files_processed=len(files),
        files_changed=files_changed,
        input_chars=input_chars,
        output_chars=output_chars,
        apostrophes_retained=validation.apostrophe_occurrences,
        invalid_apostrophes_removed=totals['non_avagraha_apostrophe_removed'],
        rule_counts=totals,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Build strict final GRETIL candidate')
    parser.add_argument('--input-root', type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--report-dir', type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)
    result = build_projection(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
    )
    print(f'files processed: {result.files_processed}')
    print(f'character delta: {result.output_chars - result.input_chars}')
    print(f'apostrophes retained: {result.apostrophes_retained}')
    print('invalid characters: 0')
    print('invalid apostrophes: 0')


if __name__ == '__main__':
    main()

'''Remove positive-match document and edition structure before projection.'''

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMPLEMENTATION = 'gretil-document-structure-1'
DEFAULT_INPUT_ROOT = Path(
    'data/intermediate/gretil/known_file_cleaned_gretil_iast'
)
DEFAULT_OUTPUT_ROOT = Path(
    'data/intermediate/gretil/document_structure_cleaned_gretil_iast'
)
DEFAULT_REPORT_DIR = Path('reports/cleaning/generated/document_structure')

SANKHARU_PATH = '1_veda/3_ara/sankharu.txt'
SANKHARU_TITLE = '\u015a\u0101\u1e45kh\u0101yan\u0101ra\u1e47yakam'
SANKHARU_SIGLUM_RE = re.compile(r'^\u015a\u0100(?:\s*=\s*KU)?$')
EXPLICIT_STRUCTURE_RE = re.compile(
    r'^\s*(?:\[?colophon\]?|notation|appendix|addenda|running\s+header|table\s+of\s+contents)\b.*$',
    re.IGNORECASE,
)
EDITORIAL_NOTE_RE = re.compile(r'^\s*(?:%\s*)?(?:note|editorial\s+note)\b', re.I)


@dataclass(frozen=True, slots=True)
class StructureResult:
    files_processed: int
    files_changed: int
    lines_removed: int
    input_chars: int
    output_chars: int
    rule_counts: Counter[str]


def _is_all_upper_siglum(line: str) -> bool:
    if not line or len(line) > 48 or '|' in line:
        return False
    letters = [character for character in line if character.isalpha()]
    if not letters or len(letters) > 16:
        return False
    return all(character.isupper() for character in letters)


def _structure_rule(
    line: str,
    *,
    path: str,
    line_number: int,
    first_nonblank: int | None,
    repeated: Counter[str],
    followed_by_blank: bool,
) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None

    if path == SANKHARU_PATH:
        if stripped == SANKHARU_TITLE:
            return 'sankharu_standalone_title_removed'
        if SANKHARU_SIGLUM_RE.fullmatch(stripped):
            return 'sankharu_standalone_siglum_removed'

    if EXPLICIT_STRUCTURE_RE.fullmatch(stripped) or EDITORIAL_NOTE_RE.match(stripped):
        return 'explicit_editorial_structure_line_removed'
    if _is_all_upper_siglum(stripped):
        return 'standalone_siglum_removed'

    has_upper = any(character.isupper() for character in stripped)
    has_structure_punctuation = any(
        character in '[]=,:;*@%' or character.isdigit() for character in stripped
    )
    if (
        repeated[stripped] >= 2
        and len(stripped) <= 120
        and '|' not in stripped
        and has_upper
        and has_structure_punctuation
    ):
        return 'repeated_running_header_or_abbreviation_removed'

    if (
        first_nonblank == line_number
        and followed_by_blank
        and len(stripped) <= 160
        and '|' not in stripped
        and has_upper
    ):
        return 'standalone_document_title_removed'
    return None


def clean_document(text: str, *, path: str) -> tuple[str, list[dict[str, Any]]]:
    lines = text.split('\n')
    repeated = Counter(line.strip() for line in lines if line.strip())
    first_nonblank = next(
        (number for number, line in enumerate(lines, start=1) if line.strip()), None
    )
    output: list[str] = []
    changes: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        line_number = index + 1
        followed_by_blank = index + 1 < len(lines) and not lines[index + 1].strip()
        rule = _structure_rule(
            line,
            path=path,
            line_number=line_number,
            first_nonblank=first_nonblank,
            repeated=repeated,
            followed_by_blank=followed_by_blank,
        )
        if rule is None:
            output.append(line)
        else:
            output.append('')
            changes.append(
                {
                    'path': path,
                    'line_number': line_number,
                    'rule': rule,
                    'removed': line,
                }
            )
    return '\n'.join(output), changes


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def build_cleanup(
    *, input_root: Path, output_root: Path, report_dir: Path
) -> StructureResult:
    if not input_root.is_dir():
        raise FileNotFoundError(f'structure input root does not exist: {input_root}')
    if input_root.resolve() == output_root.resolve():
        raise ValueError('input_root and output_root must differ')
    if output_root.exists():
        raise FileExistsError(f'structure output root already exists: {output_root}')
    files = tuple(sorted(path for path in input_root.rglob('*.txt') if path.is_file()))
    if not files:
        raise RuntimeError(f'no .txt files found under: {input_root}')

    output_root.mkdir(parents=True)
    file_rows: list[dict[str, Any]] = []
    occurrences: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    files_changed = 0
    input_chars = 0
    output_chars = 0

    for source in files:
        relative = source.relative_to(input_root).as_posix()
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding='utf-8')
        cleaned, changes = clean_document(text, path=relative)
        input_chars += len(text)
        output_chars += len(cleaned)
        if changes:
            files_changed += 1
            destination.write_text(cleaned, encoding='utf-8', newline='')
        else:
            shutil.copy2(source, destination)
        document_counts = Counter(str(change['rule']) for change in changes)
        counts.update(document_counts)
        occurrences.extend(changes)
        file_rows.append(
            {
                'path': relative,
                'changed': int(bool(changes)),
                'lines_removed': len(changes),
                'input_chars': len(text),
                'output_chars': len(cleaned),
                'char_delta': len(cleaned) - len(text),
            }
        )

    _write_csv(
        report_dir / 'document_structure_files.csv',
        ('path', 'changed', 'lines_removed', 'input_chars', 'output_chars', 'char_delta'),
        file_rows,
    )
    _write_csv(
        report_dir / 'document_structure_occurrences.csv',
        ('path', 'line_number', 'rule', 'removed'),
        occurrences,
    )
    summary = [
        'Formal GRETIL document-structure cleanup',
        '==========================================',
        f'implementation: {IMPLEMENTATION}',
        f'input_root: {input_root}',
        f'output_root: {output_root}',
        f'files_processed: {len(files)}',
        f'files_changed: {files_changed}',
        f'lines_removed: {len(occurrences)}',
        f'input_chars: {input_chars}',
        f'output_chars: {output_chars}',
        f'char_delta: {output_chars - input_chars}',
        '',
        'rule totals:',
        *(f'  {rule}: {count}' for rule, count in sorted(counts.items())),
        '',
        'policy:',
        '  matched structure lines are blanked; their LF positions are preserved',
        '  document titles, standalone sigla, repeated headers, and edition notes are not lowercased',
        '  non-matching Sanskrit text is byte/text identical at this stage',
        '',
    ]
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'document_structure_summary.txt').write_text(
        '\n'.join(summary), encoding='utf-8', newline=''
    )
    return StructureResult(
        files_processed=len(files),
        files_changed=files_changed,
        lines_removed=len(occurrences),
        input_chars=input_chars,
        output_chars=output_chars,
        rule_counts=counts,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Remove GRETIL document structure')
    parser.add_argument('--input-root', type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--report-dir', type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)
    result = build_cleanup(
        input_root=args.input_root,
        output_root=args.output_root,
        report_dir=args.report_dir,
    )
    print(f'files processed: {result.files_processed}')
    print(f'files changed: {result.files_changed}')
    print(f'structure lines removed: {result.lines_removed}')


if __name__ == '__main__':
    main()

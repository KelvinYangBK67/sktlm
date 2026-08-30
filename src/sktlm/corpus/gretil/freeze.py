'''Freeze a strictly validated GRETIL cleanup candidate as canonical.'''

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sktlm.corpus.gretil.cleaning.strict import validate_corpus


IMPLEMENTATION = 'gretil-canonical-freeze-2-strict'
DEFAULT_INPUT_ROOT = Path('data/intermediate/gretil/strict_final_candidate_gretil_iast')
DEFAULT_OUTPUT_ROOT = Path('data/canonical/gretil_iast')
DEFAULT_BASE_MANIFEST = Path(
    'data/manifests/checkpoints/gretil_pre_strict_canonical.csv'
)
DEFAULT_MANIFEST = Path('data/manifests/canonical_corpus.csv')
DEFAULT_REPORT = Path('reports/cleaning/gretil_canonical_freeze_summary.txt')

FREEZE_COLUMNS = ('byte_count', 'freeze_id', 'freeze_input_path')


@dataclass(frozen=True, slots=True)
class FreezeResult:
    files_frozen: int
    corpus_sha256: str
    byte_count: int
    char_count: int
    flagged_files: int
    flagged_occurrences: int
    invalid_apostrophe_occurrences: int


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def corpus_sha256(root: Path, files: tuple[Path, ...]) -> str:
    '''Hash ordered relative paths and exact bytes into one corpus identity.'''

    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode('utf-8')
        digest.update(len(relative).to_bytes(4, 'big'))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()


def _manifest_relative(row: dict[str, str]) -> str:
    canonical = PurePosixPath(row['canonical_path'].replace('\\', '/'))
    if 'gretil_iast' in canonical.parts:
        index = canonical.parts.index('gretil_iast')
        return PurePosixPath(*canonical.parts[index + 1 :]).as_posix()
    return PurePosixPath(row['relative_path']).with_suffix('.txt').as_posix()


def _read_manifest(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f'manifest has no header: {path}')
        return list(reader.fieldnames), list(reader)


def _write_manifest(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def freeze_corpus(
    *,
    input_root: Path,
    output_root: Path,
    base_manifest: Path,
    manifest_path: Path,
    report_path: Path,
) -> FreezeResult:
    '''Validate strictly, then copy exact bytes and bind provenance.'''

    if not input_root.is_dir():
        raise FileNotFoundError(f'freeze input root does not exist: {input_root}')
    if input_root.resolve() == output_root.resolve():
        raise ValueError('input_root and output_root must differ')
    if output_root.exists():
        raise FileExistsError(f'freeze output root already exists: {output_root}')
    if not base_manifest.is_file():
        raise FileNotFoundError(f'base manifest does not exist: {base_manifest}')

    files = tuple(sorted(path for path in input_root.rglob('*.txt') if path.is_file()))
    if not files:
        raise RuntimeError(f'no .txt files found under: {input_root}')

    # This gate runs before creating output_root: a failed policy can never
    # leave a partially frozen canonical corpus.
    strict_validation = validate_corpus(
        input_root=input_root, report_dir=None, require_clean=True
    )

    fieldnames, base_rows = _read_manifest(base_manifest)
    rows_by_relative = {_manifest_relative(row): row for row in base_rows}
    input_relatives = {path.relative_to(input_root).as_posix() for path in files}
    if set(rows_by_relative) != input_relatives:
        missing_manifest = sorted(input_relatives - set(rows_by_relative))
        missing_input = sorted(set(rows_by_relative) - input_relatives)
        raise RuntimeError(
            'freeze input/manifest membership mismatch; '
            f'missing_manifest={missing_manifest}; missing_input={missing_input}'
        )

    freeze_id = corpus_sha256(input_root, files)
    output_root.mkdir(parents=True)
    output_rows: list[dict[str, Any]] = []
    byte_count = 0
    char_count = 0

    for source_path in files:
        relative = source_path.relative_to(input_root).as_posix()
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)

        data = source_path.read_bytes()
        text = data.decode('utf-8')
        if unicodedata.normalize('NFC', text) != text:
            raise RuntimeError(f'freeze input is not NFC: {relative}')
        byte_count += len(data)
        char_count += len(text)

        row: dict[str, Any] = dict(rows_by_relative[relative])
        row.update(
            {
                'canonical_path': destination.as_posix(),
                'canonical_script': 'iast',
                'char_count': len(text),
                'line_count': len(text.splitlines()),
                'segment_count': sum(1 for line in text.splitlines() if line.strip()),
                'canonical_hash': hashlib.sha256(data).hexdigest(),
                'byte_count': len(data),
                'freeze_id': freeze_id,
                'freeze_input_path': relative,
            }
        )
        output_rows.append(row)

    output_rows.sort(key=lambda row: str(row['freeze_input_path']))
    output_fields = [
        *fieldnames,
        *(name for name in FREEZE_COLUMNS if name not in fieldnames),
    ]
    _write_manifest(manifest_path, output_fields, output_rows)

    summary = [
        'Formal GRETIL canonical corpus freeze',
        '======================================',
        f'implementation: {IMPLEMENTATION}',
        f'input_root: {input_root}',
        f'output_root: {output_root}',
        f'base_manifest: {base_manifest}',
        f'manifest: {manifest_path}',
        f'files_frozen: {len(files)}',
        f'byte_count: {byte_count}',
        f'char_count: {char_count}',
        f'corpus_sha256: {freeze_id}',
        f'strict_clean_files: {len(files)}',
        'invalid_character_files: 0',
        'invalid_character_occurrences: 0',
        'invalid_apostrophe_files: 0',
        'invalid_apostrophe_occurrences: 0',
        f'validated_apostrophe_occurrences: {strict_validation.apostrophe_occurrences}',
        '',
        'freeze policy:',
        '  input is the structure-cleaned and strict-projected candidate',
        '  exact file membership, provenance identifiers, and split assignments are preserved',
        '  canonical bytes are copied without representation conversion',
        '  freeze is forbidden unless invalid characters and invalid apostrophes are both zero',
        '  representation generation must consume this freeze and remain a separate stage',
        '',
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('\n'.join(summary), encoding='utf-8', newline='')

    return FreezeResult(
        files_frozen=len(files),
        corpus_sha256=freeze_id,
        byte_count=byte_count,
        char_count=char_count,
        flagged_files=0,
        flagged_occurrences=0,
        invalid_apostrophe_occurrences=0,
    )


def validate_freeze(*, output_root: Path, manifest_path: Path) -> FreezeResult:
    '''Validate membership, hashes, counts, NFC, strict policy, and freeze ID.'''

    if not output_root.is_dir():
        raise FileNotFoundError(f'canonical freeze root does not exist: {output_root}')
    strict_validation = validate_corpus(
        input_root=output_root, report_dir=None, require_clean=True
    )
    _, rows = _read_manifest(manifest_path)
    files = tuple(sorted(path for path in output_root.rglob('*.txt') if path.is_file()))
    rows_by_relative = {_manifest_relative(row): row for row in rows}
    relatives = {path.relative_to(output_root).as_posix() for path in files}
    if set(rows_by_relative) != relatives:
        raise RuntimeError('canonical freeze membership does not match manifest')

    digest = corpus_sha256(output_root, files)
    freeze_ids = {row.get('freeze_id', '') for row in rows}
    if freeze_ids != {digest}:
        raise RuntimeError('canonical freeze corpus digest does not match manifest')

    byte_count = 0
    char_count = 0
    for path in files:
        relative = path.relative_to(output_root).as_posix()
        row = rows_by_relative[relative]
        data = path.read_bytes()
        text = data.decode('utf-8')
        if hashlib.sha256(data).hexdigest() != row['canonical_hash']:
            raise RuntimeError(f'canonical hash mismatch: {relative}')
        if unicodedata.normalize('NFC', text) != text:
            raise RuntimeError(f'canonical file is not NFC: {relative}')
        if len(data) != int(row['byte_count']) or len(text) != int(row['char_count']):
            raise RuntimeError(f'canonical count mismatch: {relative}')
        byte_count += len(data)
        char_count += len(text)

    return FreezeResult(
        files_frozen=len(files),
        corpus_sha256=digest,
        byte_count=byte_count,
        char_count=char_count,
        flagged_files=0,
        flagged_occurrences=0,
        invalid_apostrophe_occurrences=strict_validation.invalid_apostrophe_occurrences,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Freeze strict canonical GRETIL corpus')
    parser.add_argument('--input-root', type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--base-manifest', type=Path, default=DEFAULT_BASE_MANIFEST)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    result = freeze_corpus(
        input_root=args.input_root,
        output_root=args.output_root,
        base_manifest=args.base_manifest,
        manifest_path=args.manifest,
        report_path=args.report,
    )
    print(f'files frozen: {result.files_frozen}')
    print(f'corpus sha256: {result.corpus_sha256}')
    print('invalid characters: 0')
    print('invalid apostrophes: 0')


def validate_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Validate strict frozen GRETIL corpus')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    result = validate_freeze(output_root=args.output_root, manifest_path=args.manifest)
    print(f'validated files: {result.files_frozen}')
    print(f'corpus sha256: {result.corpus_sha256}')
    print('invalid characters: 0')
    print('invalid apostrophes: 0')


if __name__ == '__main__':
    main()

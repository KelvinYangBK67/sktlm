from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sktlm.corpus.gretil.freeze import freeze_corpus, validate_freeze


def write_base_manifest(path: Path, canonical_path: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        'source',
        'source_path',
        'relative_path',
        'canonical_path',
        'canonical_script',
        'document_id',
        'layer',
        'split',
        'char_count',
        'line_count',
        'segment_count',
        'has_accent',
        'has_unknown_chars',
        'source_hash',
        'canonical_hash',
    ]
    row = {
        'source': 'gretil',
        'source_path': 'data/raw/gretil/1_veda/example.htm',
        'relative_path': '1_veda/example.htm',
        'canonical_path': canonical_path,
        'canonical_script': 'iast',
        'document_id': 'doc_fixed',
        'layer': 'veda',
        'split': 'train',
        'char_count': '0',
        'line_count': '0',
        'segment_count': '0',
        'has_accent': 'false',
        'has_unknown_chars': 'false',
        'source_hash': 'source-hash',
        'canonical_hash': 'old-hash',
    }
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerow(row)


def test_freeze_preserves_provenance_and_validates(tmp_path: Path) -> None:
    input_root = tmp_path / 'input'
    output_root = tmp_path / 'canonical/gretil_iast'
    base_manifest = tmp_path / 'base.csv'
    manifest = tmp_path / 'canonical.csv'
    report = tmp_path / 'freeze.txt'
    source = input_root / '1_veda/example.txt'
    source.parent.mkdir(parents=True)
    source.write_text(
        'devo ' + chr(39) + 'pi |\n\n', encoding='utf-8', newline=''
    )
    write_base_manifest(base_manifest, 'data/canonical/gretil_iast/1_veda/example.txt')

    result = freeze_corpus(
        input_root=input_root,
        output_root=output_root,
        base_manifest=base_manifest,
        manifest_path=manifest,
        report_path=report,
    )
    validated = validate_freeze(output_root=output_root, manifest_path=manifest)

    assert validated == result
    assert (output_root / '1_veda/example.txt').read_bytes() == source.read_bytes()
    with manifest.open(encoding='utf-8', newline='') as handle:
        row = next(csv.DictReader(handle))
    assert row['document_id'] == 'doc_fixed'
    assert row['source_hash'] == 'source-hash'
    assert row['freeze_id'] == result.corpus_sha256
    summary = report.read_text(encoding='utf-8')
    assert 'invalid_character_occurrences: 0' in summary
    assert 'invalid_apostrophe_occurrences: 0' in summary


@pytest.mark.parametrize(
    'dirty_text, expected',
    [
        ('deva\u1e25.\n', 'invalid_characters=1'),
        ('r\u0101ma ' + chr(39) + 'iti |\n', 'invalid_apostrophes=1'),
    ],
)
def test_freeze_rejects_dirty_input_before_creating_output(
    tmp_path: Path, dirty_text: str, expected: str
) -> None:
    input_root = tmp_path / 'input'
    output_root = tmp_path / 'output'
    source = input_root / '1_veda/example.txt'
    source.parent.mkdir(parents=True)
    source.write_text(dirty_text, encoding='utf-8', newline='')
    base = tmp_path / 'base.csv'
    write_base_manifest(base, 'data/canonical/gretil_iast/1_veda/example.txt')
    with pytest.raises(RuntimeError, match=expected):
        freeze_corpus(
            input_root=input_root,
            output_root=output_root,
            base_manifest=base,
            manifest_path=tmp_path / 'manifest.csv',
            report_path=tmp_path / 'report.txt',
        )
    assert not output_root.exists()


def test_validation_rejects_tampering(tmp_path: Path) -> None:
    input_root = tmp_path / 'input'
    output_root = tmp_path / 'output'
    source = input_root / '1_veda/example.txt'
    source.parent.mkdir(parents=True)
    source.write_text('deva\u1e25 |\n', encoding='utf-8', newline='')
    base = tmp_path / 'base.csv'
    manifest = tmp_path / 'manifest.csv'
    write_base_manifest(base, 'data/canonical/gretil_iast/1_veda/example.txt')
    freeze_corpus(
        input_root=input_root,
        output_root=output_root,
        base_manifest=base,
        manifest_path=manifest,
        report_path=tmp_path / 'report.txt',
    )
    (output_root / '1_veda/example.txt').write_text('changed\n', encoding='utf-8')
    with pytest.raises(RuntimeError):
        validate_freeze(output_root=output_root, manifest_path=manifest)

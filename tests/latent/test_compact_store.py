from __future__ import annotations

import csv
from pathlib import Path

from sktlm.latent.phonology import Phoneme, PhonologicalForm
from sktlm.latent.store import LexiconStore


def _columns(store: LexiconStore, table: str) -> tuple[str, ...]:
    return tuple(
        str(row[1])
        for row in store.connection.execute(f'PRAGMA table_info({table})')
    )


def test_compact_store_reconstructs_export_payload(tmp_path: Path) -> None:
    store = LexiconStore(tmp_path / 'compact.sqlite')
    form = PhonologicalForm((Phoneme.O, Phoneme.M))
    try:
        store.begin_count_pass(resume=False, checkpoint={})
        assert _columns(store, 'counts_next') == ('form_key', 'expected_count')
        schema = store.connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'counts_next'"
        ).fetchone()
        assert schema is not None and 'WITHOUT ROWID' in str(schema[0])

        store.add_counts(((form, 2.5),))
        store.finalize_count_pass(alpha=0.1, checkpoint={})
        assert _columns(store, 'lexicon') == (
            'form_key',
            'expected_count',
            'probability',
        )

        store.begin_inspection()
        store.add_counts(((form, 1.25),), table='inspection_counts')
        output = tmp_path / 'lexicon.tsv'
        store.export_lexicon(output, usage_threshold=0.01)
        with output.open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle, delimiter='\t'))

        assert rows == [
            {
                'form_key': 'V_O.C_M',
                'latent_form': 'om',
                'phoneme_ids': 'V_O C_M',
                'expected_count': '1.25',
                'probability': str((2.5 + 0.1) / (2.5 + 0.1)),
                'number_of_surface_variants': '0',
                'number_of_contexts': '0',
            }
        ]
    finally:
        store.close()


def test_expanded_count_table_remains_writable_for_safe_resume(
    tmp_path: Path,
) -> None:
    store = LexiconStore(tmp_path / 'expanded.sqlite')
    form = PhonologicalForm((Phoneme.A, Phoneme.P, Phoneme.I))
    try:
        store.connection.execute(
            'CREATE TABLE counts_next ('
            'form_key TEXT PRIMARY KEY, '
            'iast TEXT NOT NULL, '
            'phoneme_ids TEXT NOT NULL, '
            'expected_count REAL NOT NULL)'
        )
        store.add_counts(((form, 3.0),))
        row = store.connection.execute(
            'SELECT form_key, iast, phoneme_ids, expected_count FROM counts_next'
        ).fetchone()

        assert row == ('V_A.C_P.V_I', 'api', 'V_A C_P V_I', 3.0)
    finally:
        store.close()

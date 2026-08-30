# Interrupted M₀ latent run diagnostics

Date of analysis: 2026-08-30

## Preservation status

The interrupted run remains at:

    artifacts/latent_lexicon/m0_iast_surface_word_v1_interrupted_20260830_1600/

No training resume, WAL checkpoint, VACUUM, integrity scan, table mutation, or artifact deletion was performed. The durable database and WAL retained their original sizes and mtimes:

| file | bytes | mtime |
|---|---:|---|
| learner.sqlite | 3,514,896,384 | 2026-08-30 15:59:58 |
| learner.sqlite-wal | 110,436,632 | 2026-08-30 16:00:07 |

Important preservation caveat: opening the database through Python SQLite with mode=ro and PRAGMA query_only=ON still caused SQLite on Windows to rebuild/resize the transient WAL shared-memory index. learner.sqlite-shm changed from 229,376 bytes (mtime 13:55:46) to 196,608 bytes (mtime 16:27:22). The main database and WAL were not changed. No attempt was made to delete or reconstruct the SHM file afterward.

## Provenance and progress

- implementation: latent-lexicon-v1
- implementation commit: f95cfba4071f7b54cd238f1873da4dbd9d82b66e
- condition: IAST + surface_word
- freeze ID: 9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40
- manifest SHA256: c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520
- rules SHA256: 76f00baca78f97472731ff6ba1e24fca56985bc229523fb2dcc7a2018fa73f00
- active pass: 1 (neutral initialization)
- durable next document index: 169 of 240
- durable characters: 41,788,595
- durable segments: 977,174
- durable expected lexical tokens: 10,013,823.01724547
- durable identity / latent mass: 24,301.44188480 / 952,872.55811543
- overflowed tokens: 0

Identity plus latent mass agrees with the durable segment count to floating-point tolerance. This verifies posterior conservation only through the last JSON checkpoint.

## SQLite structure

SQLite version was 3.45.1, journal mode wal, page size 4,096 bytes, logical page count 860,534, and freelist count 0. The database contained:

- metadata(key TEXT PRIMARY KEY, value TEXT);
- counts_next(form_key TEXT PRIMARY KEY, iast TEXT, phoneme_ids TEXT, expected_count REAL);
- the automatic primary-key indexes for those two rowid tables.

There was no lexicon table and no inspection table, confirming that pass 1 never finalized. This Python SQLite build does not include ENABLE_DBSTAT_VTAB, and no sqlite3_analyzer executable was installed, so an exact safe table-vs-index page allocation was unavailable.

## Counts ahead of the checkpoint

The read-only counts_next aggregate was:

| measure | value |
|---|---:|
| distinct form keys / rows | 14,038,465 |
| sum expected count | 10,050,446.91437637 |
| minimum expected count | 1.4155089311e-45 |
| maximum expected count | 165,550.71518216 |
| mean expected count | 0.71592207 |

The database total exceeds the JSON checkpoint by:

    10,050,446.91437637 - 10,013,823.01724547 = 36,623.89713090

Therefore counts_next contains committed partial work after the durable document boundary. The old resume path would keep this mass and recompute document 169, confirming the double-count root cause.

## Type-count distribution

| expected-count interval | types |
|---|---:|
| <= 1e-12 | 43,167 |
| (1e-12, 1e-6] | 1,325,320 |
| (1e-6, 1e-3] | 4,220,215 |
| (1e-3, 1e-2] | 3,066,887 |
| (1e-2, 1e-1] | 3,669,626 |
| (1e-1, 1] | 1,435,042 |
| > 1 | 278,208 |

In total, 13,760,257 of 14,038,465 types (about 98.0%) have expected count at most 1. They carry only 569,426.763 expected tokens (about 5.7%); the 278,208 types above 1 carry 9,481,020.151 expected tokens. Neutral-pass candidate proliferation is therefore a real primary storage driver, not merely a schema illusion.

## Key and payload distribution

| payload | total UTF-8 bytes | mean character length | maximum character length |
|---|---:|---:|---:|
| form_key | 855,331,768 | 60.928 | 1,250 |
| phoneme_ids | 855,331,768 | 60.928 | 1,250 |
| iast | 261,371,854 | 14.867 | 312 |

form_key and phoneme_ids are equivalent serializations separated only by punctuation, so 855 MB is duplicated directly in the table. Because the table is a rowid table with form_key TEXT PRIMARY KEY, the automatic unique index stores the long form key again.

Form-key length buckets:

| characters | types |
|---|---:|
| <=16 | 33,427 |
| 17–32 | 1,632,362 |
| 33–64 | 7,788,353 |
| 65–128 | 4,055,491 |
| 129–256 | 459,547 |
| >256 | 69,285 |

IAST length buckets:

| characters | types |
|---|---:|
| <=4 | 41,434 |
| 5–8 | 2,050,332 |
| 9–16 | 7,961,997 |
| 17–32 | 3,515,858 |
| 33–64 | 402,844 |
| >64 | 66,000 |

The three text columns alone occupy about 1.972 GB before SQLite record/B-tree overhead; an expected-count double uses another roughly 112 MB. Repeating the form key in the primary-key index contributes another lower-bound 855 MB of logical key material. Schema amplification is therefore also substantial.

## Diagnosis

Both proposed explanations are true:

1. Candidate/type explosion: neutral inference has produced 14.0 million distinct lexical keys, overwhelmingly with tiny posterior counts.
2. Storage amplification: two equivalent phoneme serializations and a rowid-table primary-key index repeat long key material.

The P0 correctness bug is independent of those size issues: document-internal flushes committed global counts while JSON progress advanced only at document boundaries.

## Scientific usability

This artifact is useful for incident, storage, and neutral-pass candidate diagnostics. It is not a final learned lexicon:

- pass 1 is incomplete;
- the SQLite state is ahead of the durable progress checkpoint;
- no lexicon was finalized;
- no learned passes or final inspection ran;
- safe exactly-once continuation cannot be inferred for this legacy state.

The artifact must remain excluded from Git and must not be resumed. A new production run ID is required after correctness/performance validation.

# Latent lexicon v1 performance optimization log

All entries use the frozen M₀ IAST/surface_word observation, fixed 1218-rule grammar, exact inference, and unchanged alpha=0.1, lambda=0.5, tau=1.0, whitespace penalty 8.0, and candidate bounds.

| version | commit | benchmark | workers | char visits | segment visits | wall s | chars/s | segments/s | peak RAM | DB/temp storage | equivalence |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| P0 reference | 1c5530f + benchmark instrumentation | smoke, 1 pass + inspection | 1 | 94,080 | 2,446 | 22.222 | 4,233.61 | 110.07 | unavailable on Windows harness | 44,108,686 B artifacts | reference pair: PASS |

## P0: transactionally coupled resume

- Change: document-internal count flushes remain uncommitted; document counts, metrics, and progress metadata commit in one SQLite transaction. JSON is an atomic mirror; the database checkpoint is authoritative.
- Safety: crash before commit rolls the entire document back; crash after commit resumes after that document even if JSON lags.
- Tests: partial-document write crash, post-commit JSON lag, legacy unsafe resume refusal, and byte-identical scientific outputs against uninterrupted reference.
- Performance effect: not claimed as an optimization. It fixes exactly-once semantics while preserving bounded memory.

## Pending measurements

The medium reference, accepted/rejected optimizations, single-worker optimized result, worker scaling, memory/storage effects, and full-M₀ projection will be appended as they are measured.

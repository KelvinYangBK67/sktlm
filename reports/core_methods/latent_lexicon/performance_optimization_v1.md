# Latent lexicon v1 performance optimization log

All entries use the frozen M₀ IAST/surface_word observation, fixed 1218-rule grammar, exact inference, and unchanged alpha=0.1, lambda=0.5, tau=1.0, whitespace penalty 8.0, and candidate bounds.

| version | commit | benchmark | workers | char visits | segment visits | wall s | chars/s | segments/s | peak RAM | DB/temp storage | equivalence |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| P0 reference | 1c5530f + telemetry instrumentation | smoke, 1 pass + inspection, median of 3 | 1 | 94,080 | 2,446 | 55.046 | 1,709.10 | 44.44 | 54.5 MiB measured in 2 fixed-sampler repeats | 44,109,992 B artifacts | 3 repeats vs original: PASS |

## P0: transactionally coupled resume

- Change: document-internal count flushes remain uncommitted; document counts, metrics, and progress metadata commit in one SQLite transaction. JSON is an atomic mirror; the database checkpoint is authoritative.
- Safety: crash before commit rolls the entire document back; crash after commit resumes after that document even if JSON lags.
- Tests: partial-document write crash, post-commit JSON lag, legacy unsafe resume refusal, and byte-identical scientific outputs against uninterrupted reference.
- Performance effect: not claimed as an optimization. It fixes exactly-once semantics while preserving bounded memory.

## P1: benchmark telemetry

- Change: record low-overhead phase timings, count-store activity, scorer cache/SQLite counters, and a non-scientific timing artifact. Repair the Windows process-memory sampler with explicit 64-bit ctypes signatures.
- Stability: three repeats were 54.049, 55.046, and 56.323 seconds. The earlier 22.222-second observation did not reproduce and is excluded as a host-state outlier.
- Scientific effect: none. Equivalence against the pre-telemetry reference reported zero mismatches at relative tolerance 1e-10 and absolute tolerance 1e-12.
- Bottleneck: final inspection consumes about 44.44 seconds, including about 31.94 seconds exact inference. Training consumes about 8.80 seconds, including about 4.53 seconds inference.

## Pending measurements

The medium reference, accepted/rejected optimizations, single-worker optimized result, worker scaling, memory/storage effects, and full-M₀ projection will be appended as they are measured.

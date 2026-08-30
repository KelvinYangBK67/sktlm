# Latent lexicon v1 reference performance profile

Date: 2026-08-30

## Fixed benchmarks

- smoke list: configs/benchmarks/latent_smoke_documents.txt
  - 12 documents;
  - 52,203 manifest characters;
  - selection uses the smallest documents by (char_count, relative_path) until at least 50,000 characters;
  - 116 observed apostrophes.
- medium list: configs/benchmarks/latent_medium_documents.txt
  - 20 documents;
  - 4,519,181 manifest characters (7.8474% of M₀);
  - one path-hash-selected document from each of 20 document-size rank bins;
  - size range 877 to 1,213,181 characters;
  - 7,823 observed apostrophes.

Both selections are document-based, deterministic, independent of model output, and reference the frozen representations rather than duplicating corpus text.

## Interrupted full-run reference

The interrupted pass-1 run processed 41,788,595 characters between roughly 12:30 and 15:58, or about 12 million characters/hour. A single unoptimized neutral pass therefore projects to roughly 4.8 hours for full M₀. This is not a projection for all three learned passes plus inspection.

## Smoke wall baseline

Command:

    .\.venv\Scripts\python.exe -m sktlm.latent.benchmark --benchmark smoke --run-id smoke_reference_p0_wall --passes 1

This benchmark performs one exact neutral training pass plus exact final inspection. The original uninstrumented observation was:

| metric | value |
|---|---:|
| actual characters per pass | 47,040 |
| actual segments per pass | 1,223 |
| total character visits | 94,080 |
| total segment visits | 2,446 |
| wall time | 22.222 s |
| CPU time | 20.547 s |
| character visits/s | 4,233.61 |
| segment visits/s | 110.07 |
| artifact bytes | 44,108,686 |

This observation did not reproduce after the host returned to a stable load and is retained only as the first historical measurement. It is an anomalously fast outlier, not the accepted baseline.

Three consecutive telemetry-enabled repeats used the same inputs and scientific configuration. Their accepted wall baseline is the median:

| metric | median | range |
|---|---:|---:|
| wall time | 55.046 s | 54.049–56.323 s |
| CPU time | 49.031 s | 48.563–49.969 s |
| character visits/s | 1,709.10 | 1,670.37–1,740.65 |
| segment visits/s | 44.44 | 43.43–45.26 |
| artifact bytes | 44,109,992 | 44,109,988–44,109,997 |
| measured peak RSS | 54.5 MiB | 54.5–54.6 MiB for the two repeats after the Windows sampler fix |

Median low-overhead phase timings:

| phase | seconds |
|---|---:|
| training document total | 8.799 |
| training candidate generation | 2.948 |
| training exact inference | 4.529 |
| final-inspection document total | 44.440 |
| inspection candidate generation | 4.214 |
| inspection exact inference | 31.940 |
| inspection serialization | 4.364 |
| SQLite count-row serialization | 0.834 |
| SQLite count upsert | 0.656 |
| SQLite document commit | 0.390 |

The inspection scorer made 1,448,559 score calls on every repeat: 1,408,809 cache hits, 39,750 cache misses and SQLite selects. The counter invariants were likewise identical: 99,854 rows serialized/upserted in 24 upsert calls, with 12 document commits.

All telemetry repeats remained scientifically equivalent to the original reference with zero mismatches at relative tolerance 1e-10 and absolute tolerance 1e-12, including candidate fingerprints, segment log partitions, posteriors, expected counts, boundary/rule output, top analyses, and final probabilities.

## Smoke cProfile

The profiled run took 72.530 s wall / 70.359 s CPU and made about 254 million function calls. cProfile overhead is large, so these timings identify call structure and relative hotspots; the unprofiled run above is the wall baseline.

Top cumulative costs:

| function/group | cumulative seconds | observation |
|---|---:|---|
| final inspection | 57.156 | dominant workflow phase |
| exact infer_segment | 50.884 | called once per segment per phase |
| factor/token evaluation | 36.970 | includes repeated scoring and local decode |
| _trim_paths / sorting | 32.776 | dominated by repeated word.key construction |
| PhonologicalForm.key | 36.645 | 8.38 million property calls |
| outer top-path decode | 12.002 | inspection-only structure |
| training pass | 15.219 | still requests top_k=1 decode |
| candidate graph construction | 8.882 | 22,248 token lattices |
| benchmark candidate fingerprint | 4.457 | equivalence diagnostics only; disabled in production |
| internal grammar matching | 1.864 | called 157,500 times |
| count flush path | 2.380 | includes row serialization and SQLite |

The profile confirms:

1. training performs bounded decoding and inspection-only work it does not consume;
2. lexical forms are scored and serialized repeatedly;
3. internal matches are recomputed for incoming/outgoing combinations;
4. SQLite is a major full-run storage risk, but not the leading smoke CPU hotspot;
5. final inspection needs its own optimized/parallel path.

## Medium reference

Command:

    .\.venv\Scripts\python.exe -m sktlm.latent.benchmark --benchmark medium --run-id medium_reference_p1 --passes 1

This completed from clean commit 232eacf. It performs one exact neutral training pass plus exact final inspection over the deterministic 7.8474% document subset.

| metric | value |
|---|---:|
| actual characters per phase | 4,231,365 |
| actual segments per phase | 95,847 |
| total character visits | 8,462,730 |
| total segment visits | 191,694 |
| wall time | 5,297.481 s |
| CPU time | 4,464.578 s |
| character visits/s | 1,597.50 |
| segment visits/s | 36.19 |
| peak RSS | 123.43 MiB |
| total artifacts | 3,288,521,198 B |
| learner SQLite | 1,479,335,936 B |
| analyses JSONL | 1,046,361,666 B |
| boundary JSONL | 441,118,636 B |
| latent lexicon TSV | 321,630,165 B |

Low-overhead phase breakdown:

| phase | seconds | share of wall |
|---|---:|---:|
| training document total | 1,099.381 | 20.75% |
| training candidate generation | 370.215 | 6.99% |
| training exact inference | 525.008 | 9.91% |
| inspection document total | 3,977.911 | 75.09% |
| inspection candidate generation | 358.656 | 6.77% |
| inspection exact inference | 2,557.635 | 48.28% |
| inspection serialization | 327.551 | 6.18% |
| SQLite count-row serialization | 61.318 | 1.16% |
| SQLite count upsert | 162.685 | 3.07% |
| SQLite document commit | 48.610 | 0.92% |
| lexicon finalize | 16.569 | 0.31% |

The finalized neutral lexicon contains 1,888,526 active types, of which 1,866,183 have expected count at most 1. Inspection made 129,313,724 lexical score calls. The LRU served 126,840,086 calls, a 98.0871% hit rate, but 2,473,638 SQLite SELECTs still consumed 145.657 seconds. The profile therefore prioritizes eliminating repeated scoring and path-key construction, then reducing candidate reconstruction and storage amplification; increasing the SQLite cache alone cannot address the dominant call volume.

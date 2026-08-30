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

Pending low-overhead phase-timing instrumentation. The medium run must be performed before accepting optimization speedups and will be recorded here without cProfile's multi-fold overhead.

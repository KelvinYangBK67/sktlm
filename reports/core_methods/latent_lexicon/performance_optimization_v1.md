# Latent lexicon v1 performance optimization log

All entries use the frozen M₀ IAST/surface_word observation, fixed 1218-rule grammar, exact inference, and unchanged alpha=0.1, lambda=0.5, tau=1.0, whitespace penalty 8.0, and candidate bounds.

| version | commit | benchmark | workers | char visits | segment visits | wall s | chars/s | segments/s | peak RAM | DB/temp storage | equivalence |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| P0 reference | 1c5530f + telemetry instrumentation | smoke, 1 pass + inspection, median of 3 | 1 | 94,080 | 2,446 | 55.046 | 1,709.10 | 44.44 | 54.5 MiB measured in 2 fixed-sampler repeats | 44,109,992 B artifacts | 3 repeats vs original: PASS |
| P1 medium reference | 232eacf | medium, 1 pass + inspection | 1 | 8,462,730 | 191,694 | 5,297.481 | 1,597.50 | 36.19 | 123.43 MiB | 3,288,521,198 B artifacts; 1,479,335,936 B SQLite | reference |

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
- Medium confirmation: 5,297.481 seconds wall. Inspection consumes 3,977.911 seconds, including 2,557.635 seconds inference; training consumes 1,099.381 seconds. Inspection makes 129,313,724 lexical score calls, with 2,473,638 SQLite misses costing 145.657 seconds.

## Accepted single-process optimizations

All smoke comparisons below used scientific equivalence diagnostics. Every accepted candidate reported zero mismatches at relative tolerance `1e-10` and absolute tolerance `1e-12`.

| version | commit | isolated change | smoke result |
|---|---|---|---|
| P2 | `75da12f` | training-only exact inference, without inspection-only marginals/top-k | training document median 8.799 -> 4.562 s; training inference 4.529 -> 0.775 s |
| P3 | `14d883c` | cache `PhonologicalForm.key` at construction | wall median 13.134 s; inspection inference 4.020 s; training inference 0.521 s |
| P4 | `87113e0` | score each distinct lexical form once per segment | lexical score calls 1,448,559 -> 74,131; wall median 12.855 s; inspection inference 3.462 s |
| P5 | `26e3a99` | cache script-neutral internal-sandhi matches | 18,468 hits / 3,764 misses (83.1%); wall median 12.771 s |
| P6 | `3840576` | compact SQLite count tables and reconstruct payloads on export | SQLite 21,753,856 -> 13,762,560 B (-36.7%); total artifacts 44.11 -> 36.12 MB (-18.1%); wall 12.352 s |

P3 is the largest single-process improvement. The canonical key was formerly rebuilt by repeated string joins throughout candidate sorting, scoring, and reporting. The cached value is immutable and therefore does not change key identity or ordering.

P4 targets calls rather than only SQLite misses: a segment-local map evaluates each distinct `PhonologicalForm` once, then reuses its scalar score across all edges/paths in that segment. This preserves the scorer and posterior equations exactly.

P6 retains read/write compatibility with legacy expanded count tables during safe resume. New count, lexicon, and inspection tables store the canonical key plus numeric fields in `WITHOUT ROWID` tables; IAST and phoneme columns are reconstructed only during export.

## Rejected smoke candidates

- Cached `TokenPath` sort keys plus `heapq.nsmallest`: scientifically equivalent but no reproducible wall benefit; reverted.
- Indexed lattice adjacency: scientifically equivalent, but construction cost offset the inference shift; reverted.
- Removing unused incoming adjacency alone: no reproducible benefit; reverted.
- Visible-boundary LRU caching: scientifically equivalent but slower and larger in memory; reverted.

These experiments were not committed.

## Deterministic multiprocessing

P7 (`fa27389`) parallelizes training by document. Workers use read-only lexicon connections and write bounded count shards with `float.hex` values, configuration identity, SHA-256 checksums, and completion markers. The master process reduces shards in original document order and commits each document's counts plus checkpoint atomically. Valid shards survive a crash and are reused on resume.

P8 (`3da7ad1`) applies the same design to inspection. Each document produces analysis, boundary, count, surface-usage, context-usage, and ordered reduction shards. The master concatenates and reduces them in original document/segment order, preserving report tie-breaking and floating-point accumulation order. Inspection completion is durable in SQLite before optional shard cleanup; a completed `--resume` does not repeat inference. Atomic file replacement has a short bounded retry for transient Windows sharing violations.

The relevant 3-pass smoke scaling measurements are:

| path | workers | repeats | wall median | training median | inspection median | scientific equivalence |
|---|---:|---:|---:|---:|---:|---|
| optimized serial reference | 1 | 3 | 19.268 s | 10.091 s | 8.088 s | reference |
| training-only multiprocessing | 4 | 3 | 17.023 s | 7.885 s | serial inspection | zero mismatches |
| training + inspection multiprocessing, final | 4 | 3 | 13.305 s | 6.998 s | 5.292 s | zero mismatches |

The final 4-worker path is 1.45x faster end to end than the optimized serial reference on smoke; training is 1.44x faster and inspection is 1.53x faster. A 2-worker smoke run was slightly slower than serial (19.480 s wall) because the documents are too short to amortize Windows spawn, shard, and cache-splitting overhead. Four workers crossed that threshold. Medium/full scaling must therefore be measured rather than extrapolated from logical CPU count.

The benchmark's current `peak_rss_bytes` is the main process's peak only. It is valid for serial runs but does not include simultaneous worker RSS and must not be used to claim that multiprocessing reduces memory. The implementation itself remains bounded by `workers * per-document working state` plus bounded count buffers and on-disk shards; aggregate process-tree memory still needs an explicit measurement before choosing a full-run worker count.

## Completed P8 medium validation

The 4-worker, 3-pass P8 benchmark completed successfully at
`artifacts/latent_benchmarks/medium_optimized_p8_w4_p3/` from commit
`049d439`.

| measurement | P1 medium reference | P8 medium | change |
|---|---:|---:|---:|
| training passes | 1 | 3 | — |
| wall time | 5,297.481 s | 2,141.125 s | 2.474x faster despite two additional passes |
| normalized character throughput | 1,597.50 chars/s | 7,904.94 chars/s | 4.948x |
| training document wall | 1,099.381 s | 884.096 s total; 294.699 s/pass | 3.731x per pass |
| inspection document wall | 3,977.911 s | 1,185.712 s | 3.355x |
| inspection inference | 2,557.635 s | 673.600 s | 3.797x |
| inspection lexical-score calls | 129,313,724 | 6,593,658 | 19.612x fewer |
| artifact bytes | 3,288,521,198 | 2,571,478,847 | 21.8% smaller |
| SQLite bytes | 1,479,335,936 | 770,027,520 | 47.95% smaller |

Integrity checks found three completed passes, completed inspection, zero
candidate overflow, no retained shard files, the expected artifact line counts,
and `PRAGMA quick_check = ok`. The exported lexicon has 1,888,526 rows. Its
training-count sum is 394,031.7572; the inspection-count sum is 395,770.4820.
Pass 1 iteration metrics are byte-for-byte/numerically identical to the old
1-pass reference, which is the valid cross-pass scientific comparison.

The conservative character-throughput projection for full M₀ is about 8.09
hours, still 2.70x slower than the approximately 3-hour goal. The document-count
projection is about 7.14 hours. Neither projection includes aggregate worker RSS:
the recorded 78.5 MB peak covers only the main process.

The medium scientific audit reports mean identity mass 0.070468, mean latent
mass 0.929532, mean posterior entropy 1.044665, and mean top-1 posterior
0.594393. Of 1,888,526 active rows, 1,866,960 (98.858%) are low-count. This is
not a counting error—active means a positive stored row, not hard support—but
lexicon proliferation remains a substantive modeling issue for the first full
run.

The sanity-run `om` / `oṃ` symmetry does not persist on medium:

| form | key | pass-3 training count | inspection expected count |
|---|---|---:|---:|
| `om` | `V_O.C_M` | 47.612692 | 50.809742 |
| `oṃ` | `V_O.M_ANUSVARA` | 29.976378 | 27.907685 |

Literal `om iti` / `om ity...` environments support `C_M`, while literal
`oṃ ...` environments and grammar-licensed analyses distribute evidence
differently. The forms are distinct intentional phonological types; the near
equality in the tiny sanity sample was expected local unidentifiability, not
representation or expected-count duplication.

## P9-P10 post-medium smoke optimizations

P9 (`e731d6c`) replaces fixed worker batches with a bounded rolling FIFO window
of at most `2 * workers` submitted documents. Workers can prepare later
documents while the master still reduces results in canonical index order.
Crash-reusable shard semantics and the memory bound are unchanged. The repeated
4-worker, 3-pass smoke median fell from 13.305 to 10.322 seconds; training fell
from 6.998 to 5.360 seconds and inspection from 5.292 to 3.992 seconds. Scientific
equivalence reported zero mismatches.

P10 (`dc68089`) serializes the five scalar `BoundaryPosterior` fields directly
instead of recursively converting each dataclass. Exact output bytes are
preserved by the existing sorted-key JSON writer. The targeted inspection
serialization median fell from 1.841 to 1.683 seconds (8.6%). Overall smoke wall
time was host-noisy, so acceptance is based on the isolated phase improvement
and zero scientific mismatches.

Rejected post-P9 variants were a `4 * workers` queue (only 0.8% faster while
doubling the pending-shard bound), file-size-prioritized submission (slower due
to canonical-reducer blocking), compact reduction TSV, incremental checksums,
unsorted JSON keys, and compact JSON separators. All were reverted.

## Completed P10 medium validation

The 4-worker, 3-pass P10 benchmark completed at
`artifacts/latent_benchmarks/medium_optimized_p10_w4_p3/` from commit
`9be29ea`.

| measurement | P8 medium | P10 medium | P8/P10 |
|---|---:|---:|---:|
| wall time | 2,141.125 s | 1,216.915 s | 1.759x |
| character throughput | 7,904.94 chars/s | 13,908.50 chars/s | 1.759x |
| training document wall | 884.096 s | 625.509 s | 1.413x |
| inspection document wall | 1,185.712 s | 523.347 s | 2.266x |
| inspection inference | 673.600 s | 572.871 s | 1.176x |
| inspection candidate generation | 391.150 s | 319.259 s | 1.225x |
| inspection serialization | 237.169 s | 166.122 s | 1.428x |
| total process CPU | 2,811.500 s | 2,859.047 s | 0.983x |

The near-flat CPU total together with the 43.2% wall reduction confirms that
P9's rolling scheduler primarily removed worker idle time. Aggregate training
candidate-generation and inference timers increased on this run, but training
wall still fell 29.2%; those worker-summed phase timers reflect greater
concurrency and host contention and must not be added as serial wall time.

P10 has the same three completed pass summaries, final summary, analyses,
boundary posteriors, lexicon, and rule usage as P8. All six scientific artifact
pairs have identical sizes and SHA-256 hashes, which is stronger than
tolerance-based equivalence. SQLite `quick_check` is healthy; both count tables
have 1,888,526 rows and the expected training/inspection totals. No shard files
remain.

The conservative full-M₀ projection is now 4.60 hours by characters; the
document-count projection is 4.06 hours. Reaching three hours still requires
about 1.53x or 1.35x respectively. Eight-worker medium scaling is therefore the
next measurement. Aggregate worker memory must be observed externally because
the benchmark's 78.4 MB peak is main-process-only.

One post-P10 experiment reused a token's internal-match inventory across its
incoming/outgoing lattice combinations. It produced zero scientific mismatches,
but three experimental smoke runs and a current-host P10 control did not show a
reproducible phase or wall improvement. The patch and its focused test were
reverted.

## Validation before local scaling closure

- Focused latent suite after P8: `22 passed`.
- Full repository suite: `444 passed, 3 failed`; the three failures are the pre-existing SentencePiece 0.2.2 removal of `immutable_proto`, outside this latent-method change.
- Final reference-vs-4-worker 3-pass smoke comparison: zero mismatches.
- The P8 4-worker, 3-pass medium benchmark completed and passed the integrity/scientific audit above.
- P10 completed on medium and is byte-identical to P8 for all six scientific artifacts.
- The failed transient-lock smoke artifact `smoke_inspection_workers_4_final_b` was preserved for diagnostics and was not counted; the bounded replacement retry is covered by a focused test.

This checkpoint authorized the later 8-worker run recorded below. The next
active measurement is now the independent cloud scaling gate, not another local
benchmark.

## Completed local 8-worker scaling

The clean run `medium_optimized_p10_w8_p3_rerun1` completed in 1,526.624
seconds and is scientifically byte-identical to the 4-worker P10 reference.
Checkpoint, SQLite, zero-overflow, and shard-cleanup audits all pass.

Eight workers regress wall by 25.45%, training wall by 13.33%, inspection wall
by 27.05%, and total CPU by 23.81%; throughput is 20.29% lower. Four workers
are the local production sweet spot, and local 12/16-worker runs are closed.
Cloud scaling remains an independent 4→8 gate because the host/OS/storage
topology differs. Full details and hashes are in `medium_scaling_p10.md`.

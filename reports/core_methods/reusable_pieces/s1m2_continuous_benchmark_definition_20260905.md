# S1M2 continuous benchmark-definition freeze

Date: 2026-09-05

```text
S1M2_TRAINER_INTEGRATION=COMPLETE
CONTINUOUS_BENCHMARK_SELECTION_RULE=FROZEN
CONTINUOUS_STATIC_SCAN=COMPLETE_VALIDATED
```

This checkpoint freezes workload selection before any S1M2 continuous timing
or optimization result is observed. It does not select documents from model
runtime, launch a model benchmark, or authorize full-M0.

## Inputs

The tracked configuration is
`configs/benchmarks/s1m2_continuous_selection.json`. It names exactly:

- validated M0-prime IAST `continuous`, frontend `iast_m0_prime`, manifest
  SHA-256 `3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`;
- frozen M0 Devanagari `continuous`, frontend `devanagari`, representation
  manifest SHA-256
  `c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520`.

The scan trusts the already validated per-file manifest hashes instead of
rehashing the full frozen/derived corpora. It does fail closed on manifest
identity, freeze ID, document membership, file presence, and recorded byte,
character, line, and (where present) phoneme counts.

## Static measurements and fixed selection

`sktlm.latent.continuous_structure` streams documents and observes only
frontend/static structure:

- bytes, written characters, lines, and phonemes;
- punctuation-delimited continuous span lengths;
- punctuation delimiter count;
- exact p50/p90/p95/p99/max span summaries;
- sum of span phonemes and sum of squared span lengths as a declared
  materialization-pressure proxy.

It builds no grammar candidate graph, computes no posterior, uses no learned
state, and measures no runtime outcome. It also requires per-document equality
of total phonemes and the ordered continuous-span-length digest between the
two frontends.

The Devanagari cell is the selection basis. The stress workload is the first
two documents under `(maximum span, sum of squared span lengths, phonemes)`
descending with relative path as the final ascending tie break. Those rows are
removed before representative selection. Remaining documents are ranked by
`(sum of squared span lengths, maximum span, phonemes, relative path)` and the
nearest distinct rows at the fixed 25th, 50th, and 75th percentile ranks are
selected. This rule cannot be changed after observing benchmark timings.

The full static summary supplies corpus totals for character-, document-, and
span/complexity-weighted runtime projections. The emitted document lists will
be promoted under `configs/benchmarks/` only after the detached scan passes
identity and completion validation.

## Validation and detached boundary

Tiny tests require deterministic output, the fixed representative/stress
selection behavior, cross-frontend structural identity, and fail-closed
behavior for a frontend mismatch. Focused continuous-structure,
representation-frontend, and M0-prime tests pass (`26 passed`). `git diff
--check` passes.

The one-time 240-document/two-frontend scan is conservatively treated as a
greater-than-five-minute workload because it parses roughly 199 MB of text.
It must be launched once from a clean committed checkout with durable logs,
an exact attempt identity, a non-overwriting output directory, and a recorded
Git/config identity. It is a static scan, not an S1M2 training run.

```text
FULL_M0_PROCESS_RUNNING=NO
FULL_M0_PROCESS_COMPLETED=NO
```

## Completed static scan

The detached attempt
`sktlm-s1m2-continuous-structure-v1-a01` completed its Python computation at
Git SHA `16c67d33a44d8cf651a795aa89a193490116af23`. The output envelope is
`VALID`; `structure.json` has SHA-256
`03ebdf71afc80f82492d9d36cc593ab50c380fd3b0b57689862ea8e98c7b39f8`.
Both frontend cells have identical ordered nonempty span lengths and phoneme
counts for every document.

Shared full-corpus structure is 240 documents, 2,107,648 lines, 46,255,133
phonemes, 1,261,507 nonempty continuous spans, and 2,285,952,803 summed
squared-span phonemes. Across document maxima, p50/p90/p95/p99 are
101/501/822/1,500 phonemes and the maximum is 2,634. M0-prime IAST and M0
Devanagari differ in orthographic bytes/characters and raw consecutive
punctuation-cue counts, but not in the nonempty inference span sequence; the
latter is the relevant frontend structural workload.

The frozen representative workload is:

```text
6_sastra/7_ayur/bhavpr_u.txt
3_purana/bhagp/bhp_11u.txt
2_epic/mbh/mbh_09_u.txt
```

It contains 456,891 phonemes, 12,306 spans, 17,336,773 squared-span phonemes,
and maximum span 85. The frozen stress workload is:

```text
1_veda/5_vedang/2_grhya/jaimigsu.txt
1_veda/5_vedang/2_grhya/kauthgsu.txt
```

It contains 62,748 phonemes, 241 spans, 51,185,640 squared-span phonemes, and
maximum span 2,634. The lists are now tracked under `configs/benchmarks/`; the
compact evidence envelope is
`reports/core_methods/reusable_pieces/evidence/s1m2_continuous_structure_v1.json`.

The child completed atomically with an empty stderr and a `COMPLETE` stdout,
but Task Scheduler later recorded control-break result `3221225786` and the
wrapper was terminated before replacing its `RUNNING` state file. The output
completion/hash/identity checks pass and no child remains, so this is a wrapper
teardown anomaly, not a computation failure. The stale state and a separate
reconciliation record are preserved; the scan must not be rerun.

```text
CONTINUOUS_STATIC_SCAN=COMPLETE_VALIDATED
CONTINUOUS_BENCHMARK_WORKLOADS=FROZEN
S1M2_CONTINUOUS_PROFILING=READY_TO_IMPLEMENT
```

## Detailed engineering telemetry checkpoint

The S1M2 production path now emits bounded engineering-only telemetry before
any model timing has been used to select an optimization. Fixed power-of-two
histograms retain counts, totals, maxima, and p50/p90/p95/p99 bucket upper
bounds without storing per-segment observations. They cover written length,
phoneme length, token/span length, boundary/factor/match/node work, overflow,
and lazy-span hypotheses.

Candidate construction reports visible-boundary, grammar-match, match-window,
node construction, lattice-validation, and total factor-construction timings,
plus raw/retained match and factor-combination counters. Exact composed
inference reports nested inner piece forward/backward/posterior/top-k,
lazy-token forward/backward/posterior/top-k, factor composition, and outer
forward/backward/posterior/identity/top-k timings. These timers are diagnostic
subphase clocks and may overlap their enclosing phase totals; they never enter
candidate membership, scores, ordering, expected counts, or parameter updates.

Parallel execution now reports the fixed `2 * workers` pending-shard limit,
observed queue occupancy, completed-but-canonically-blocked shards, reducer
stall time, and pending-shard bytes. SQLite database/WAL/shared-memory growth
and the near-final artifact footprint are recorded as high-water gauges.
Production-like Linux runs will continue to use the established external
one-second process-tree sampler for simultaneous worker RSS, CPU, and I/O.

Telemetry-on candidate graphs are structurally identical to telemetry-off
graphs. P1c oracle/outer equivalence, trainer resume behavior, and serial versus
two-worker scientific byte identity remain covered. The focused pieces/latent
suite passes (`80 passed`), and `git diff --check` passes. No model benchmark
has yet been run from this checkpoint, so continuous profiling is not declared
complete.

```text
S1M2_CONTINUOUS_TELEMETRY=IMPLEMENTED_VALIDATED
S1M2_CONTINUOUS_CHEAP_PROFILE=READY_TO_RUN
FULL_M0_PROCESS_RUNNING=NO
FULL_M0_PROCESS_COMPLETED=NO
```

## Runtime benchmark contract

`configs/benchmarks/s1m2_continuous_runtime.json` now binds every continuous
probe, representative, and stress benchmark ID to its exact model, manifest
path/hash, frontend, condition, frozen document-list path/hash, and optional
line bound. The two probe IDs use the frozen representative list but read only
the first two lines per document; they are the fixed cheap profiling workload,
not a projection sample. Representative and stress IDs have no line bound.

The runner rejects a manifest or list hash mismatch, any model other than
`reusable_pieces_v1`, any non-continuous condition, and every frontend except
`iast_m0_prime` or `devanagari`. It therefore has no route to the scientifically
excluded original M0 IAST-continuous cell. Benchmark output records the resolved
contract together with model/frontend/workload identities. S1M1 `smoke` and
`medium` names retain their legacy behavior.

Contract tests pass, including fail-closed hash behavior (`2 passed`; included
in the latest targeted run of `9 passed`). The fixed probes are ready to run
from a clean committed checkpoint.

```text
S1M2_CONTINUOUS_BENCHMARK_CONTRACT=FROZEN
S1M2_CONTINUOUS_CHEAP_PROFILE=READY_TO_RUN
```

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

## Fixed paired probe baseline

At clean Git SHA `95f6029cc2e0e05852305cf7d4f511c064d60789`, both fixed
six-line/one-pass probes completed with final inspection under `cProfile`:

| cell | wall | CPU | training inference | inspection inference |
|---|---:|---:|---:|---:|
| M0-prime IAST continuous | 19.088 s | 15.344 s | 3.902 s | 12.611 s |
| M0 Devanagari continuous | 18.629 s | 15.156 s | 3.801 s | 12.057 s |

The two frontends produced identical 91 training phonemes, five segments,
1,073 candidate span hypotheses, 4,626 composed states, and 25,135 composed
transitions. Piece inventory, lexical diagnostics, and rule-usage artifacts
are byte-identical. Training/inspection summaries differ only in expected
written-character counts (92 IAST versus 75 Devanagari). This rules out a
script-specific residual in the exact composed workload on the probe.

The IAST profile records 25.55 million calls. `LazyLexicalSpan.word` accounts
for 193,077 calls and 5.643 cumulative seconds, while `PhonologicalForm`
initialization accounts for 391,082 calls and 7.001 cumulative seconds. The
lazy lattice already constructs and validates a form when creating each
transient span, then discards it and reconstructs it repeatedly during exact
traversals. Candidate generation is only about two milliseconds. The first
optimization experiment is therefore reuse of that already-validated transient
form, with graph and posterior equivalence required.

The compact evidence envelope is
`evidence/s1m2_continuous_probe_baseline_v1.json`. Because the probe reads only
six lines and `cProfile` inflates Python-heavy work, its wall times are not a
full-M0 projection and do not satisfy the representative/stress gate.

```text
S1M2_CONTINUOUS_CHEAP_PROFILE=COMPLETE
CONTINUOUS_SCRIPT_NEUTRAL_PROBE=PASS
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
```

## Optimization 1 candidate: transient form reuse

The measured first candidate changes only the transient `LazyLexicalSpan`
representation. `LazyTokenLattice.span()` already constructs a
`PhonologicalForm` to apply the unchanged vowel legality check; the span now
retains that validated object for the lifetime of the current iterator result.
Exact traversals therefore reuse `span.word` within that result instead of
reconstructing it on every access. No span is stored in the candidate graph or
across a traversal, so P1b still does not materialize persistent lexical edges
or all span rows.

The P0/P1c equivalence and trainer scientific byte-equivalence gates remain
green, a focused identity test proves repeated access returns the retained
object, and the complete pieces/latent suite passes (`82 passed`). The candidate
is committed for an exact-code paired probe; it is not accepted as a performance
optimization until that measurement improves the identified mechanism without
scientific divergence.

```text
S1M2_OPTIMIZATION_1=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
```

### Optimization 1 result: accepted

The exact fixed paired probe at candidate SHA
`d4e48735cefb9d25a057c40c1b12e811cc1afa32` preserves all seven canonical
scientific artifacts byte-for-byte within each frontend. Profiled wall time
fell from 19.088 to 10.054 seconds for M0-prime IAST (`47.3%`) and from 18.629
to 9.252 seconds for M0 Devanagari (`50.3%`). Training inference improved
`57.8%`/`57.1%`; inspection inference improved `37.6%`/`41.0%`.

The measured mechanism also moved: profiled calls fell from 25.55 million to
14.03 million (`45.1%`), `PhonologicalForm` initializations fell `49.4%`, their
cumulative cost fell `75.9%`, and the `LazyLexicalSpan.word` hotspot vanished.
Process memory and artifact size remained effectively unchanged on this tiny
serial probe. The compact evidence is
`evidence/s1m2_continuous_optimization_1_v1.json`.

The largest remaining exact-inference cost is now per-form piece evaluation,
where the same legal `(start, end, piece, prior, score)` transitions are rebuilt
for forward, backward, posterior, singleton, and inspection top-k passes within
one cache-miss evaluation. The next candidate is a transient per-evaluation
transition table; it must preserve loop order, legal support, path scores, and
all marginals, and it must not persist per-form lattices.

```text
S1M2_OPTIMIZATION_1=ACCEPTED
S1M2_OPTIMIZATION_2=TRANSIENT_PIECE_TRANSITION_REUSE_READY
```

### Optimization 2 candidate: transient piece-transition reuse

One `evaluate_form` cache miss now constructs each legal piece transition once
as `(end, piece, prior, score)` in start-position order. Inner forward,
backward, posterior, singleton-path, and inspection top-k loops traverse that
same iterator-local table in their original order. The table is discarded when
the form evaluation completes; only the existing bounded compact
`FormPieceEvaluation` may enter the pass-local LRU. This is not a P0 lattice,
does not persist candidates, and remains linear in form length times the fixed
piece-length bound plus the required whole-form transition.

The focused P0/P1c, trainer, frontend, and cache suites pass (`82 passed`). A
cache-counter assertion was updated to reflect that repeated within-form
piece-score cache calls are intentionally eliminated: total calls still equal
hits plus misses, and all entry/byte bounds remain enforced. The candidate now
requires the same committed paired probe before acceptance.

```text
S1M2_OPTIMIZATION_2=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
```

#### Optimization 2 result: accepted

At candidate SHA `407904ac8ed8196c7b676b7deab8b707a6f85e8d`, all seven
canonical scientific artifacts remain byte-identical to optimization 1 in both
frontends. Profiled wall time fell another `59.4%` for M0-prime IAST and `58.7%`
for M0 Devanagari. Training inference improved `44.5%`/`46.1%`; inspection
inference improved `66.5%`/`65.7%`.

The profiled call count fell `25.6%`, form initializations fell `67.8%`, and
piece-score calls fell from 79,667 to 25,135 in training and from 104,802 to
25,135 in inspection. Those final counts equal the unchanged composed legal
transition count. The compact acceptance envelope is
`evidence/s1m2_continuous_optimization_2_v1.json`.

The remaining inspection profile is dominated by repeated sort/key allocation
in bounded top-k. The next smallest candidate batches the inner piece-path
sort/truncate once per destination position rather than once after every
incoming transition. Top-k of a union is unchanged by this scheduling, tie keys
remain identical, and the temporary candidates remain bounded by the fixed
piece length and top-k. Lazy-token top-k is not changed in this candidate.

```text
S1M2_OPTIMIZATION_2=ACCEPTED
S1M2_OPTIMIZATION_3=INNER_TOP_K_BATCHING_READY
```

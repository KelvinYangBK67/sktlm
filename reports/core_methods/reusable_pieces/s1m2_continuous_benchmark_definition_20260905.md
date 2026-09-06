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

### Optimization 3 result: accepted

At candidate SHA `e4ed01671a7c0ec027db46372680f5c6b90b176f`, each inner
piece-path destination is sorted and truncated only when all of its incoming
paths have arrived, immediately before that position is consumed. Since every
transition moves right, this is the same top-K union with the unchanged score
and piece-key tie order. Temporary paths remain bounded by
`(max_piece_length + 1) * inspection_top_k` per position, including the
whole-form edge. Exact forward/backward inference is untouched.

A direct P0 comparison passes for ordered paths, log weights, and posterior
probabilities; the pieces/latent suite passes (`83 passed`). All seven
canonical scientific artifacts remain byte-identical to optimization 2 in
both frontends. Profiled wall time improved another `10.5%` for M0-prime IAST
and `9.4%` for M0 Devanagari; inspection inference improved `14.6%`/`17.2%`,
and inner piece top-K time improved `32.3%`/`34.3%`. List-sort calls fell from
26,234 to 5,725 (`78.2%`). The compact acceptance envelope is
`evidence/s1m2_continuous_optimization_3_v1.json`.

The largest remaining avoidable inspection hotspot is now repeated creation
of the same deterministic nested tie key for surviving `_ComposedPath`
objects during 1,078 lazy/outer trims. The next small candidate stores that
inspection-only immutable key on each transient path and extends it alongside
the path, retaining the identical ordering and existing top-K bounds.

```text
S1M2_OPTIMIZATION_3=ACCEPTED
S1M2_OPTIMIZATION_4=COMPOSED_PATH_TIE_KEY_REUSE_READY
```

### Optimization 4 result: accepted

At candidate SHA `942007c231a14c73caa6441176c66cc7cec3ff32`, every bounded
inspection-only `_ComposedPath` stores the exact lexical-key, nested piece-key,
and rule-ID tuple that repeated trims previously reconstructed. New paths
extend this immutable key alongside the corresponding scientific path; the
score and stable deterministic tie order are unchanged. No key survives the
existing bounded top-K path state.

The pieces/latent suite passes (`83 passed`), and all seven canonical artifacts
remain byte-identical to optimization 3 in both frontends. Profiled wall time
improved `25.5%` for M0-prime IAST and `20.9%` for M0 Devanagari; inspection
inference improved `35.4%`/`23.0%`, and lazy-token top-K improved
`78.3%`/`71.3%`. The same 1,078 trim calls now use 0.018 cumulative profiled
seconds instead of 0.547 on the IAST probe. The compact acceptance envelope is
`evidence/s1m2_continuous_optimization_4_v1.json`.

The remaining profile constructs a `PhonologicalForm` before every one of
25,135 piece-score cache lookups even though only 1,039 are misses. The next
small candidate keys the same bounded LRU by the already available immutable
phoneme tuple and constructs a form only on a miss, returning the cached form
on hits. Cache order, byte/entry bounds, scores, legal transitions, and emitted
piece identities must remain identical.

```text
S1M2_OPTIMIZATION_4=ACCEPTED
S1M2_OPTIMIZATION_5=LAZY_PIECE_FORM_CONSTRUCTION_READY
```

### Optimization 5 result: accepted

At candidate SHA `1c27eb02b0dd5db8d6fbc23d2707ee14fa0b8b82`, the existing
bounded piece-score LRU is keyed by the immutable phoneme tuple available
before form construction. A miss constructs and validates the same
`PhonologicalForm`, invokes the same scorer, and stores the form with its score;
a hit returns both. LRU access order, logical byte accounting, entry bounds,
and all score/cache counters are unchanged.

The pieces/latent suite passes (`83 passed`), and all seven canonical artifacts
remain byte-identical to optimization 4 for both frontends. Profiled wall time
improved `20.5%` for M0-prime IAST and `21.5%` for M0 Devanagari. Training
inference improved `30.1%`/`22.3%`, inspection improved `12.7%`/`25.4%`, and
piece-transition construction improved `57--64%`. `PhonologicalForm`
initializations fell from 63,806 to 15,614 while cache calls and misses stayed
at 25,135 and 1,039 per phase. The compact acceptance envelope is
`evidence/s1m2_continuous_optimization_5_v1.json`.

The largest remaining inspection-specific allocation is the inner top-K sort
key: 135,550 calls reconstruct nested piece-key tuples for paths that already
carry those pieces. The next small candidate extends an immutable piece-key
tuple alongside each bounded inner inspection path and sorts on it directly,
without changing path generation, score/tie ordering, or top-K bounds.

```text
S1M2_OPTIMIZATION_5=ACCEPTED
S1M2_OPTIMIZATION_6=INNER_PATH_KEY_REUSE_READY
```

### Optimization 6 result: accepted

At candidate SHA `25fbeedc2afb84b868d35624ba5303310dcc574f`, bounded inner
inspection paths carry the immutable tuple of their piece keys. Appending the
next piece key produces exactly the tuple previously regenerated during sort;
score order, tie order, path generation, and the existing
`(max_piece_length + 1) * inspection_top_k` bound are unchanged. Exact
marginals never consume this path state.

The P0 ordered-top-path test and full pieces/latent suite pass (`83 passed`).
All seven canonical artifacts remain byte-identical to optimization 5 in both
frontends. Inner piece top-K improved `61.1%`/`60.7%`, inspection inference
improved `18.4%`/`15.3%`, and profiled wall time improved `7.2%`/`11.9%`.
The compact acceptance envelope is
`evidence/s1m2_continuous_optimization_6_v1.json`.

The IAST profile now spends 0.219 cumulative seconds in repeated generated
dataclass hashing, with 7,521 form evaluations but only 364 form-cache misses.
The next small candidate keys the existing bounded form-evaluation LRU by the
already cached canonical `form.key` string. This avoids tuple/enum hashing on
hits while preserving equality, LRU order, cache bounds, and returned
evaluations; no global representation or multiprocessing hash behavior changes.

```text
S1M2_OPTIMIZATION_6=ACCEPTED
S1M2_OPTIMIZATION_7=FORM_CACHE_CANONICAL_KEY_READY
```

### Optimization 7 result: accepted (small)

At candidate SHA `29c08a242bc4c4f65b39ddeebeb210c4bc45ccf3`, the existing
bounded form-evaluation LRU uses the canonical cached `form.key` string instead
of hashing the full phoneme tuple on every access. Canonical keys are injective
over form symbols; cache access/eviction order, size accounting, and returned
evaluations remain unchanged. A focused test uses a distinct but equal form
object to exercise the hit path.

The pieces/latent suite passes (`83 passed`), and all seven canonical artifacts
remain byte-identical to optimization 6 in both frontends. Profiled wall time
improved `3.9%` for M0-prime IAST and `1.1%` for M0 Devanagari. Generated hash
cost fell from 0.219 to 0.190 cumulative profiled seconds. This is accepted as
a small exact simplification, not evidence for a new scaling regime. The compact
envelope is `evidence/s1m2_continuous_optimization_7_v1.json`.

The cheap profile is now dominated by actual lazy-span traversal and exact
form/outer dynamic programming rather than a single avoidable allocation
hotspot. The next fixed gate is a detached local measurement of the frozen
representative workload at the established local four-worker setting, with
both continuous frontends run sequentially under one unique attempt. This is
diagnostic evidence only; production readiness still requires cloud w4/w8 and
the frozen stress workload.

```text
S1M2_OPTIMIZATION_7=ACCEPTED_SMALL
S1M2_CONTINUOUS_REPRESENTATIVE_LOCAL=READY_TO_LAUNCH_DETACHED
```

## Frozen representative result

The detached attempt
`s1m2_continuous_representative_local_v1_attempt01` completed successfully at
SHA `765742a1037ff2e1ef5dc267d300742ad84ef0c8` on 2026-09-06. It ran the
three frozen representative documents sequentially through M0-prime IAST and
M0 Devanagari continuous, at four local Windows workers, for one pass plus
final exact inspection. Both stderr logs are empty, both checkpoints record
one completed pass, and both output configurations/provenance records match
the frozen benchmark contract. The compact evidence envelope is
`evidence/s1m2_continuous_representative_local_v1.json`.

The matched frontends produce the same exact script-neutral work: each phase
has 6,886,648 outer span hypotheses, about 33.51 million composed states, and
about 199.68 million composed transitions. Their piece inventory, lexical
diagnostics, and rule usage artifacts are byte-identical. Iteration metrics and
the scientific summary differ only in written character counts; analyses and
boundary files legitimately retain script-specific presentation and written
offsets. This passes the representative cross-frontend scientific identity
check and leaves no unexplained script residual in composed inference.

Measured elapsed time is 10,374.6 seconds (2.882 hours) for IAST and 10,352.9
seconds (2.876 hours) for Devanagari. Those values cover only one training pass
plus inspection. Replacing the measured one-pass training phase by three such
phases while retaining measured inspection and fixed finalization gives a
same-sample formal-pipeline estimate of 4.754/4.738 hours. Scaling that estimate
to all 240 documents gives the following deliberately non-precise projections:

| Basis | M0-prime IAST | M0 Devanagari |
|---|---:|---:|
| documents (80.0x) | 380 h | 379 h |
| phonemes, central (101.24x) | 481 h | 480 h |
| squared-span proxy, conservative (131.86x) | 627 h | 625 h |

The central projection is therefore approximately 480 hours per continuous
cell on this diagnostic local w4 host, not approximately three hours. The
frozen stress workload would only confirm an already decisive bad scaling
regime, so it is not launched at this point. Production-cloud w4/w8 scaling is
also premature until an exact structural change materially reduces the work.

Storage is independently not ready. The representative outputs occupy
2.43/2.52 GB, transient output reaches 3.75/3.89 GB, and SQLite reaches
1.57/1.66 GB. Simple phoneme scaling implies roughly 229/238 GiB final output,
354/367 GiB transient output, and 148/156 GiB SQLite per continuous cell. The
reported 79/83 MB RSS values cover the benchmark parent metric only, not the
aggregate process tree, and cannot close the memory gate.

The measured mechanism is exact per-span form composition under heavy bounded
cache churn: each phase evicts about 1.95 million form evaluations and 3.96
million piece scores. The next optimization must therefore reduce repeated
exact interval/form work or represent it through an equivalent shared dynamic
program, and the storage schema must become substantially more compact without
dropping required scientific information.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_LOCAL=COMPLETE_VALIDATED
CONTINUOUS_SCRIPT_NEUTRAL_REPRESENTATIVE=PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
S1M2_CONTINUOUS_STRESS=DEFERRED_PENDING_STRUCTURAL_OPTIMIZATION
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
```

### Optimization 8 candidate: shared token-local form prefix DAG

The representative profile shows that evaluating every lexical form as an
independent inner DP is the dominant structural error: approximately 1.98
million form misses expand to approximately 199.68 million inner transitions
per phase. The optimization-8 candidate instead inserts the distinct legal
forms of one lazy token into an immutable prefix DAG. Each shared prefix state
computes its bounded-piece forward value once. After the unchanged lexical
forward/backward pass supplies exact outer span masses, one reverse adjoint
pass over that same DAG produces the posterior-weighted expected piece counts
and score/entropy summaries for all form endpoints together. The special
whole-form transition remains endpoint-local and therefore cannot become a
prefix of a longer form.

This route is currently limited to training marginals with
`support_epsilon=0` and no inspection top-K. Positive occurrence support is
then exactly structural because every legal transition has finite weight.
Nonzero support thresholds and inspection use the existing exact path. A
config-recorded limit of 262,144 prefix nodes applies per token; exceeding it
falls back before any shared scoring work. The lazy outer graph remains the
authority, and the shared DAG is discarded with the token summary rather than
persisting lexical-edge rows or a P0 lattice.

Focused shared/legacy tests compare partitions, entropy, lexical and piece
expected counts, identity/latent mass, boundary/rule marginals, occurrence
support, and total posterior mass under the established tolerance. They also
exercise the finite-bound fallback. The pieces/latent suite passes (`87
passed`), including serial/parallel and resume gates. The candidate requires
the fixed paired cheap probe from its clean SHA before acceptance.

```text
S1M2_OPTIMIZATION_8=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 11 result: rejected and reverted

Candidate SHA `5560f620fadeea3947d90e83a00fbf9be7a567de` is scientifically
exact: the canonical comparator reports zero numeric difference across 10,252
values per frontend. It reduces `PhonologicalForm` initialization count by
`13.9%`, from 10,249 to 8,825.

The intended construction path nevertheless regresses. `LazyTokenLattice.span`
cumulative time rises `9.5%` for M0-prime IAST and `27.1%` for M0 Devanagari;
the shared evaluator rises `4.4%`/`3.7%`. Total wall moves in opposite
directions (`-7.7%`/`+5.5%`), consistent with subsecond host noise rather than
a reproducible win. Tuple-key dictionary work outweighs the avoided form/key
construction in the target path. The candidate was reverted at
`035802a5c8acf24291d5bb045d42d6b1d09072e1` without a repeat. Evidence is
`evidence/s1m2_continuous_optimization_11_v1.json`.

```text
S1M2_OPTIMIZATION_10=ACCEPTED_ACTIVE_BASELINE
S1M2_OPTIMIZATION_11=REJECTED_REVERTED
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 12 candidate: exact bounded Cartesian top-K merge

Within shared inspection only, a lexical span previously extended every one
of at most K retained lexical prefixes by every one of at most K retained
piece segmentations, materialized the K-squared `_ComposedPath` objects, and
then sorted/truncated them. For a fixed prefix, the segmentation row is already
ordered by the same additive score and full piece-key tie order. The candidate
therefore heap-merges those rows and visits only row heads that can enter the
global top K.

At most K heap rows and approximately 2K constructed extensions are retained
per span. Prefix/segmentation indices preserve Python's former stable
prefix-major order when scientific keys tie. This changes no exact inference
support or posterior computation; it is solely a bounded top-K presentation
factorization. Shared/legacy path tests cover sandhi ambiguity and a longer
continuous-like form, and all pieces/latent tests pass (`90 passed`). The fixed
paired probe must show identical canonical artifacts plus reduced path/sort or
lazy-token top-K work before acceptance.

```text
S1M2_OPTIMIZATION_12=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 12 result: accepted

Candidate SHA `b0ed64869d1976e51aa841603dec6e5d63cc9a43` compares exactly
against optimization 10 across seven artifacts and 10,252 numeric values for
each frontend. Lazy-token top-K falls from `0.1546` to `0.0658` seconds for
M0-prime IAST (`57.4%`) and from `0.1288` to `0.0677` seconds for M0
Devanagari (`47.5%`). Inspection inference improves `5.3%`/`16.0%`; profiled
function calls fall `4.0%` in both cells.

The IAST total wall is flat (`0.05%` improvement), while Devanagari total wall
regresses `11.8%`; these opposing subsecond totals are host noise and are not
the acceptance basis. The exact bounded target phase improves clearly in both
frontends. Evidence is
`evidence/s1m2_continuous_optimization_12_v1.json`.

The cumulative shared factorization after the frozen optimization-7
representative now changes both training and inspection structurally. A single
new detached run of the already-frozen paired representative workload is
scientifically justified to establish the new runtime/storage regime. It does
not authorize stress, cloud scaling, or any formal full-M0 run.

```text
S1M2_OPTIMIZATION_12=ACCEPTED
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=READY_TO_LAUNCH_DETACHED
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Factorized representative result: complete, artifact audit pending

The detached paired attempt
`s1m2_continuous_representative_factorized_v2_attempt01` completed at
`8f694d64d350b1e7e2c882de3556d69bcda2b8db` with exit code zero and empty
stderr logs. Provenance binds the frozen workload and input manifests, one
pass, and local Windows w4.

| Cell | One pass + inspection | Change vs opt. 7 | Reconstructed 3-pass pipeline | Central full projection | Conservative projection |
|---|---:|---:|---:|---:|---:|
| M0-prime IAST continuous | 1.488 h | -48.4% | 2.299 h | 232.8 h | 303.2 h |
| M0 Devanagari continuous | 1.308 h | -54.5% | 2.043 h | 206.8 h | 269.4 h |

Each phase retains 6,886,648 exact lexical-span hypotheses but shares them
through 5,448,470 prefix states and 39,051,167 transitions. The two frontends
match exactly on these structural counters, no shared cap fallback occurs,
states fall 83.7%, and transitions fall 80.4% relative to optimization 7.
The result is a material exact improvement but remains roughly two orders of
magnitude above the formal runtime target after full-corpus projection.

Scientific output size is unchanged. Final outputs are 2.43/2.52 GB and peak
transient outputs are 3.76/3.89 GB on the fixed representative workload;
phoneme scaling gives 354.1/366.8 GiB transient and 147.8/156.5 GiB SQLite per
cell. Compact storage remains mandatory.

The original comparator materialized complete TSV/JSONL artifacts and is not
safe for these outputs. It now streams TSV rows and JSONL records under the
same `rtol=1e-10`, `atol=1e-12` contract and enforces deterministic order. A
focused fixture and the historical cheap comparisons pass. The full
same-frontend old-vs-new comparisons will run once as a detached read-only
audit; the model workload must not be rerun.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_AWAITING_STREAMING_AUDIT
S1M2_BOUNDED_ARTIFACT_COMPARATOR=IMPLEMENTED_FOCUSED_PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 8 result: accepted for training marginals

At clean candidate SHA `2dad1b342042eb1ec9b282c3fd0d1798b363557e`,
the fixed paired probe passes semantic comparison against optimization 7 over
all seven canonical artifacts. Each frontend comparison covers 10,252 numeric
values; maximum absolute and relative differences are
`7.105427357601002e-14` and `2.8387775957490983e-14`, well inside the frozen
`rtol=1e-10`, `atol=1e-12` contract. Piece identities and occurrence support
are unchanged. The different `lazy_span_traversals` counter is engineering
evidence, not a scientific value.

The intended structural work falls sharply in both frontends: training states
fall from 4,626 to 855 (`81.5%`), transitions and piece-score calls from 25,135
to 5,454 (`78.3%`), and lazy span traversals from 3,224 to 1,073 (`66.7%`).
Training inference improves `70.3%` for M0-prime IAST and `73.2%` for M0
Devanagari. End-to-end probe wall improves `19.0%`/`18.3%` despite final
inspection deliberately remaining on the prior exact path. No shared batch
hit its finite cap. The compact envelope is
`evidence/s1m2_continuous_optimization_8_v1.json`.

Optimization 8 is accepted within its stated training-only scope. The next
exact candidate reuses the same shared prefix DAG for inspection marginals and
derives bounded per-form top segmentations from its already-scored transitions,
without changing top-K support or ordering.

```text
S1M2_OPTIMIZATION_8=ACCEPTED_TRAINING_ONLY
S1M2_OPTIMIZATION_9=SHARED_INSPECTION_MARGINALS_AND_TOP_K_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 9 candidate: shared inspection marginals and piece top-K

Inspection now uses the same token-local prefix DAG and reverse adjoint as
training for exact marginals. For presentation only, each distinct lexical
endpoint reconstructs its outgoing piece transitions from the already-scored
prefix path and runs the unchanged bounded top-K recurrence. Destination and
source order, score order, piece-key tie order, normalized log weights, and
endpoint-local long whole-form transition are identical to the legacy path.
No piece score or independent form marginal DP is repeated for top-K.

The engineering contract adds a separate cap of 4,194,304 top-K piece
references per token. The estimated endpoint/path bound is checked before
shared scoring; exceeding it uses the legacy exact implementation. Focused
tests compare shared and legacy top lexical analyses, nested piece paths,
scores, probabilities, rules, boundaries, exact marginals, and support, and
exercise both prefix-node and top-K-reference fallbacks. The pieces/latent
suite passes (`89 passed`). A fixed clean-SHA paired probe is required before
acceptance.

```text
S1M2_OPTIMIZATION_9=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 9 result: accepted

At clean candidate SHA `fc2b66babd0c77f1984679bedd01c965b1c79c32`,
the fixed probe passes the reusable seven-artifact semantic comparator against
optimization 8. Each frontend again compares 10,252 numeric values; maximum
absolute/relative differences are `1.6697754290362354e-13` and
`1.5066699193640377e-14`, inside the frozen tolerance. Top lexical and nested
piece path order, rules, boundaries, and occurrence support match.

Inspection states fall from 4,626 to 855 (`81.5%`), transitions and piece-score
calls fall from 25,135 to 5,454 (`78.3%`), and inspection inference improves
`54.1%` in both frontends. Complete probe wall improves another `40.7%` for
M0-prime IAST and `35.5%` for M0 Devanagari. No finite-cap fallback occurs.
The compact envelope is
`evidence/s1m2_continuous_optimization_9_v1.json`; future gates use
`scripts/analysis/compare_s1m2_artifacts.py` for the same deterministic
structural/numeric comparison.

The largest remaining shared-inspection hotspot constructs the same bounded
piece prefix paths independently for every form endpoint. Optimization 10 will
carry bounded normal-piece top paths on shared prefix states, then add the
required long whole-form competitor only at each endpoint. A piece-reference
bound must account for every shared state and preserve exact P0 ordering.

```text
S1M2_OPTIMIZATION_9=ACCEPTED
S1M2_OPTIMIZATION_10=SHARED_PREFIX_TOP_K_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 10 candidate: shared bounded piece-prefix top-K

Every shared prefix node now retains its bounded top piece paths, built once
from the top paths of its at-most-`max_piece_length` ancestors. This is the
same destination-wise top-K union used by the P0/legacy recurrence, with the
same raw score and piece-key tie order. Long whole-form paths are excluded from
shared prefix state and inserted only when the corresponding complete form
endpoint is requested, so whole-form memorization cannot become a prefix of a
longer analysis.

The inspection bound now conservatively checks
`top_k * sum(shared_prefix_depth)` before any shared score calls. This bounds
every stored piece reference across every prefix path, rather than only form
endpoints. Exceeding it retains the exact legacy fallback. Shared/legacy
top-analysis tests continue to pass, including long whole-form competition and
both bound fallbacks; the pieces/latent suite passes (`89 passed`). The
candidate requires the fixed clean-SHA paired probe before acceptance.

```text
S1M2_OPTIMIZATION_10=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

### Optimization 10 result: accepted

Candidate SHA `b19df311e3ca15cba40d9a2c29b993434ebb1d19` passes the
tracked canonical-artifact comparator against optimization 9 for both
frontends. Each comparison covers seven artifacts and 10,252 numeric values;
maximum absolute and relative differences are both zero. Shared inspection
retains 855 prefix states and 5,906 bounded prefix paths, with no fallback.

The intended inner piece top-K phase falls from `0.1455` to `0.0622` seconds
for M0-prime IAST (`57.3%`) and from `0.1467` to `0.0616` seconds for M0
Devanagari (`58.0%`). Enclosing lazy-token top-K improves `42.0%`/`52.1%`.
Devanagari total wall improves `17.3%`; IAST total wall changes only `0.25%`,
below useful probe precision, although IAST inspection inference improves
`7.9%`. Optimization 10 is accepted for its exactness, boundedness, and clear
targeted-phase improvement. The compact envelope is
`evidence/s1m2_continuous_optimization_10_v1.json`.

The current profile is led by construction inside the shared evaluator:
shared-form-batch building and transient lazy span/form objects, then bounded
outer composed-path selection. These are the next exact structural targets.
The expensive representative benchmark remains stale-but-decisive evidence
for the pre-optimization regime and is not yet eligible for rerun.

```text
S1M2_OPTIMIZATION_10=ACCEPTED
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

### Factorized representative audit attempt 01: comparator-only failure

Detached audit attempt
`s1m2_continuous_representative_factorized_audit_v1_attempt01` started from
clean pushed SHA `a0887bb33b1e5f2969123b105bff96a988d95706` and failed after
1.9 seconds, before a complete large-artifact scan. It launched no model,
training, inference, representative, stress, cloud, or full-M0 workload.

The preserved error is audit-only: the bounded streaming rewrite compared TSV
rows positionally, but the established semantic comparator keys TSV rows by
their first column. Equal-count piece-inventory rows may exchange presentation
order without changing the inventory. The first such pair was `V_R.V_A` and
`V_RR.V_A`. Attempt-01 state and stderr SHA-256 values are respectively
`56c1f10af244f5be83d2d091cfbb178795b0efc73f4c1f98805f934c0caf5e38` and
`adc562dcca519f787e4acf1636e197b3534a855442a6ef70a1eb55aed7b967ef`.

The corrected comparator restores the original first-column identity contract
using a temporary SQLite `WITHOUT ROWID` table. Reference insertion is batched
at 4,096 rows, candidate rows are consumed one at a time, matched identities
are removed, and any duplicate, unexpected, or missing identity fails closed.
Thus RAM remains bounded even for the 639 MB piece inventory and 401 MB lexical
diagnostics. JSONL remains line-streamed and order-sensitive. A focused fixture
with reversed TSV row order passes under the frozen `rtol=1e-10`,
`atol=1e-12` contract.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_AWAITING_STREAMING_AUDIT_RETRY
S1M2_BOUNDED_ARTIFACT_COMPARATOR=KEYED_DISK_BACKED_FOCUSED_PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

### Factorized representative audit attempt 02: TSV typing correction

Detached audit attempt
`s1m2_continuous_representative_factorized_audit_v1_attempt02` started from
clean pushed SHA `5c47ecde4e1d369630856fe0a35e6a4278512588` and failed after
9m17s during the keyed piece-inventory comparison. It ran no model, training,
inference, representative, stress, cloud, or full-M0 workload and did not
complete the large-artifact scan.

The affected identity is `C_N.V_A.C_N`, whose rendered piece is literally
`nan`. The old and factorized rows retain identical text and differ only at
floating-point roundoff in numeric fields, but the generic TSV value parser
coerced the text spelling to IEEE NaN. The attempt-02 state and stderr SHA-256
values are `50c2bf80034e1bd611d2e44aed1855103fa2f9960b30b4ba0fa49268af77fabc`
and `08a7a6cc4c2adefa545b0e1e5793ae952dda6a31f9f19486f6f7a994cbf724d0`.

The comparator now derives typing from an explicit set of numeric TSV headers.
Only those columns receive the frozen numeric tolerance and nonfinite handling;
piece spellings, phoneme IDs, roles, and other text remain exact. This composes
with the bounded disk-backed first-column join from attempt 01. Three focused
tests pass: reordered keyed TSV rows, equal/unequal numeric nonfinite values,
and exact distinction between text `nan` and `NaN`.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_AWAITING_STREAMING_AUDIT_ATTEMPT_03
S1M2_BOUNDED_ARTIFACT_COMPARATOR=SCHEMA_TYPED_KEYED_DISK_BACKED_FOCUSED_PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

### Factorized representative audit attempt 03: manual reconciliation

Attempt 03 stopped in IAST `analyses.jsonl` on a derived
segmentation-entropy value just outside the frozen numeric tolerance. The
preserved failed job remains provenance, including its copied internal
`attempt: 2` metadata error.

A complete bounded diagnostic and continuation audit closes the scientific
question. IAST covers all 12,306 analysis records and 903,234 numeric values:
70 tolerance exceedances occur, all in
`piece_posterior.segmentation_entropy`; no other scientific numeric field fails.
Five top-K membership differences occur at records 1092, 1203, 1301, 1937,
and 11353, all at the K=8 presentation cutoff among exact or near-exact ties.
The remaining canonical IAST artifacts pass.

For Devanagari, SHA-256 triage proves that piece inventory, lexical diagnostics,
and rule usage are respectively identical to the audited IAST reference and
candidate artifacts. The remaining four artifacts were scanned once. Across
2,132,828 numeric values there are no scientific non-entropy failures and no
structural failures. Two apparent numeric differences are
`lazy_span_traversals`, an engineering-only key. The scan reproduces the same
70 entropy cases, the same five cutoff membership records, and 24 top-K
order-only records.

The frozen comparator remains strict at `rtol=1e-10`, `atol=1e-12`; its JSONL
order sensitivity is unchanged. Scientific closure is recorded by reconciliation
evidence rather than by weakening the comparator or modifying production
inference to match a derived diagnostic bit-for-bit.

The factorized representative therefore passes scientific equivalence with
bounded presentation caveats. No representative rerun or audit rerun is
required without new contradictory evidence.

Canonical evidence:
`evidence/s1m2_factorized_representative_reconciliation_v1.json`.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_RECONCILED
S1M2_FACTORIZED_REPRESENTATIVE_SCIENTIFIC_EQUIVALENCE=PASS_WITH_BOUNDED_PRESENTATION_CAVEATS
S1M2_REPRESENTATIVE_RERUN=FORBIDDEN_WITHOUT_NEW_CONTRADICTORY_EVIDENCE
S1M2_REPRESENTATIVE_AUDIT_RERUN=NOT_REQUIRED
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

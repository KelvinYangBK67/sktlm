# CURRENT_TASK.md

## Current status

Branch: `exp/s1m2-reusable-pieces`.

```text
S1M1: FROZEN
researcher-authorized S1M1 regenerable-file cleanup: COMPLETE (12/12 absent)
M0-prime formal substrate: COMPLETE / VALID
S1M2 P0 reference oracle: COMPLETE
S1M2 P1a production scoring: COMPLETE
S1M2 P1b lazy candidates: COMPLETE
S1M2 P1c exact composed inference: COMPLETE
P1c/P0 and lazy/materialized equivalence gates: PASS
S1M2 streaming trainer integration: COMPLETE
resume and serial/parallel scientific equivalence: PASS
continuous profiling/benchmark freeze: IN PROGRESS
continuous benchmark selection rule: FROZEN
continuous static corpus scan: COMPLETE / VALIDATED
continuous representative/stress workloads: FROZEN
continuous detailed profiling telemetry: IMPLEMENTED / VALIDATED
paired fixed cheap profile: COMPLETE
probe script-neutral workload identity: PASS
optimization 1 transient span-form reuse: ACCEPTED
optimization 2 transient piece-transition reuse: ACCEPTED
optimization 3 inner piece top-K batching: ACCEPTED
optimization 4 composed-path tie-key reuse: ACCEPTED
optimization 5 lazy piece-form construction: ACCEPTED
optimization 6 inner piece-path key reuse: ACCEPTED
optimization 7 canonical form-cache key: ACCEPTED (small)
local frozen representative benchmark: COMPLETE / VALIDATED
representative cross-frontend script-neutral identity: PASS
continuous runtime target: NOT READY / NEXT GATE IS VM READINESS
production storage gate: PROJECTED BELOW 300 GiB / VM NOT MEASURED
optimization 8 shared token-local form-prefix DP: ACCEPTED (training marginals)
optimization 9 shared inspection marginals/top-K: ACCEPTED
optimization 10 shared bounded piece-prefix top-K: ACCEPTED
optimization 11 token-local lexical-form interning: REJECTED / REVERTED
optimization 12 exact bounded Cartesian top-K merge: ACCEPTED
factorized local representative benchmark: COMPLETE / RECONCILED
bounded streaming artifact comparator: SCHEMA-TYPED KEYED DISK-BACKED / FOCUSED PASS
optimization 13 ordered SQLite inspection-shard reduction: ACCEPTED
optimization 14 completed-state storage compaction: ACCEPTED
optimization 15 bounded transient-state lifetime: ACCEPTED
Opt16 compile-once immutable topology reuse: ACCEPTED
generic Windows Codex automation framework: COMPLETE / INFRASTRUCTURE REPAIRED
S1M2 Pre-VM Closure: NOT STARTED / INSTALLED PRE-THREAD FAILURE / RECOVERABLE BY RESEARCHER
```

P1c uses direct exact position DP under P0 legal support and P1a fixed-pass
scores, composed with P1b lazy spans. The streaming trainer now makes the piece
state authoritative, updates it transactionally between passes, retains
lexical counts as diagnostics, and exports the required exact scientific and
bounded inspection artifacts. Document-interruption resume and one/two-worker
scientific outputs are byte-identical. The focused pieces/latent suite passes
(`89 passed`) and the trainer full-repository gate passes (`633 passed, 2
warnings`). No full-corpus S1M2 run has started.

The historical deletion-readiness manifest remains provenance for the 12
files classified `SAFE_TO_DELETE_REGENERABLE`. A read-only path check now finds
all 12 absent after the separately researcher-authorized manual cleanup. Do
not recreate them, rerun their hashes, or delete anything else.

Do not rerun frozen S1M1 work or M0-prime generation/validation. `notes/**`
remains strictly local/read-only and must never be modified, created, moved,
copied, deleted, tracked, staged, restored, checked out, or force-added.

## Completed representative gate

Detached attempt `s1m2_continuous_representative_local_v1_attempt01` completed
at `765742a1037ff2e1ef5dc267d300742ad84ef0c8`; both stderr logs are empty and
all identities validate. It measured 2.882/2.876 hours for only one training
pass plus exact inspection. A reconstructed three-pass-plus-inspection sample
is 4.754/4.738 hours. Central phoneme-scaled full-corpus projections are
481/480 hours and conservative squared-span projections are 627/625 hours.
The exact frontends have identical span/state/transition work and byte-identical
piece inventory, lexical diagnostics, and rule usage.

Final output is 2.43/2.52 GB for this roughly one-percent workload, with
3.75/3.89 GB transient output. Simple phoneme scaling exceeds the 300 GiB host
for transient output, so storage is also not ready. The benchmark must not be
rerun. The stress and cloud scaling gates are deferred because they would only
measure the already-decisive bad structural regime.

## Factorized representative result

Detached attempt `s1m2_continuous_representative_factorized_v2_attempt01`
completed at `8f694d64d350b1e7e2c882de3556d69bcda2b8db`, with exit code zero
and empty stderr logs. One pass plus exact inspection now takes 1.488 hours
for M0-prime IAST and 1.308 hours for M0 Devanagari, improvements of
48.4%/54.5% over the frozen optimization-7 representative. Shared states fall
83.7% and transitions 80.4%, with identical frontend structural counts and no
shared fallback.

The reconstructed three-pass-plus-inspection samples are 2.299/2.043 hours.
Full-corpus central phoneme projections remain 232.8/206.8 hours, and
conservative squared-span projections remain 303.2/269.4 hours. Runtime is
therefore decisively not ready. Artifact/SQLite sizes are scientifically
unchanged; phoneme scaling still projects 354.1/366.8 GiB transient output and
147.8/156.5 GiB SQLite. Storage is not ready.

## Next task: structural optimization decision and VM-readiness gate

The fixed probe accepts optimization 8: training states fall 81.5%, transitions
and score calls 78.3%, training inference 70.3%/73.2%, and complete wall
19.0%/18.3%. All seven artifacts pass semantic comparison, with maximum
absolute/relative differences `7.11e-14`/`2.84e-14`.

Optimization 10 is accepted at candidate SHA `b19df311e3ca15cba40d9a2c29b993434ebb1d19`.
All seven canonical artifacts compare exactly against optimization 9 for both
frontends (`10,252` numeric values each; zero numeric difference). The targeted
inner piece top-K phase improves `57.3%`/`58.0%`, lazy-token top-K improves
`42.0%`/`52.1%`, and Devanagari wall time improves `17.3%`. IAST total wall is
flat within cheap-probe precision (`0.25%` improvement), while its inspection
inference still improves `7.9%`; this noise is recorded rather than promoted
as a total-wall claim. No shared-bound fallback occurs.

Optimization 11 was scientifically exact but failed its performance gate and
was reverted. It reduced `PhonologicalForm` construction calls by `13.9%`, but
tuple-key interning made the profiled span path `9.5%`/`27.1%` slower and the
shared evaluator `4.4%`/`3.7%` slower. Total wall improved `7.7%` in IAST but
regressed `5.5%` in Devanagari, so the conflicting noisy totals do not override
the repeated targeted-path regression. Do not repeat this timing or restore
the interner.

Continue with a different measured exact structural target, preferably
bounded outer composed-path selection or direct shared-prefix construction.
Require focused equivalence plus the fixed cheap probe. Do not rerun
representative, stress, cloud, or full-M0 until the regime materially changes.

Optimization 12 is accepted at `b0ed64869d1976e51aa841603dec6e5d63cc9a43`.
Both frontends preserve all seven artifacts exactly (`10,252` values each,
zero difference). Lazy-token top-K improves `57.4%`/`47.5%`, inspection
inference improves `5.3%`/`16.0%`, and profiled calls fall `4.0%`. Opposing
subsecond total-wall changes are recorded as noise, not evidence against the
reproduced target-phase result.

Audit attempt 01
`s1m2_continuous_representative_factorized_audit_v1_attempt01` failed in 1.9
seconds before scanning the large outputs. The failure was an audit-only
regression: the streaming rewrite compared TSV rows positionally, while the
established comparator treats the first column as identity and intentionally
allows tied inventory rows to occur in a different order. The preserved state
and stderr hashes are `56c1f10af244f5be83d2d091cfbb178795b0efc73f4c1f98805f934c0caf5e38`
and `adc562dcca519f787e4acf1636e197b3534a855442a6ef70a1eb55aed7b967ef`.
No benchmark, training, inference, or complete large-artifact scan ran.

Audit attempt 02
`s1m2_continuous_representative_factorized_audit_v1_attempt02` ran for 9m17s
and failed while comparing the keyed piece inventory. Generic numeric coercion
had interpreted the literal piece spelling `nan` (`C_N.V_A.C_N`) as IEEE NaN;
the matching old/new rows differ only by numerical roundoff in their actual
numeric columns. Its preserved state and stderr hashes are
`50c2bf80034e1bd611d2e44aed1855103fa2f9960b30b4ba0fa49268af77fabc` and
`08a7a6cc4c2adefa545b0e1e5793ae952dda6a31f9f19486f6f7a994cbf724d0`.
It ran no training or inference and did not complete a large-artifact scan.

The comparator now applies floating-point tolerance only to explicitly numeric
TSV columns selected by header; text columns remain exact. Matching numeric
nonfinite sentinels are supported, but text `nan` and `NaN` remain distinct.
Together with the temporary SQLite `WITHOUT ROWID` keyed join, input iteration
and insertion batches remain bounded, JSONL remains line-streamed and
order-sensitive, and duplicate/missing identities fail closed. Three focused
tests cover reordered keyed rows, numeric nonfinite values, and nonfinite-like
text.

Attempt 03 and the subsequent manual continuation/diagnostic scans are now
reconciled in
`evidence/s1m2_factorized_representative_reconciliation_v1.json`.
Across IAST and Devanagari there is no substantive structural divergence and
no scientific non-entropy numeric failure. The remaining differences are
derived segmentation-entropy roundoff, bounded K=8 exact/near-tie inspection
presentation, and engineering-only `lazy_span_traversals`. The global frozen
numeric tolerance and strict JSONL comparator remain unchanged.

The factorized representative is therefore scientifically complete and must
not be rerun merely to obtain a green strict-wrapper exit code. Continue only
with a genuinely structural exact optimization candidate or proceed to the
VM scaling/readiness gate when the local optimization stopping rule is met.

## Opt13 accepted; Opt14 is the only remaining round

Opt13 replaces the parallel inspection reducer's four aggregate TSV shard
streams with one ordered append-only SQLite shard per document. The parent
retains canonical document and JSONL order but performs one in-engine SQL merge
instead of parsing millions of rows into central Python objects. Legacy
schema-v1 TSV shards remain readable for interrupted-run compatibility.

The focused pieces/latent suite passes (`93 passed`), including inspection
crash/resume and serial/parallel byte identity. A single 400,000-row bounded
reducer measurement is exactly table-equivalent and improves 11.885 to 5.429
seconds (`54.3%`); its shard is `11.4%` smaller. The single fixed Devanagari
probe preserves all seven canonical artifacts exactly (`10,252` values, zero
difference) and improves wall time `2.2%`, so training and cheap total wall do
not regress. Evidence is `evidence/s1m2_local_optimization_13_v1.json`.

This Opt13-only handoff is superseded by the completed Opt14 section below.

## Opt14 accepted; bounded task complete

Opt14 retains only SQLite metadata/checkpoint state and the authoritative
active `piece_lexicon` after every canonical S1M2 artifact has been written.
Final-pass diagnostic and inspection tables are declared reconstructible and
removed, the database is compacted, and `storage_manifest.json` records the
layout. No required canonical artifact is dropped or changed.

The focused pieces/latent suite passes (`93 passed`). The single fixed
Devanagari probe preserves all seven canonical artifacts exactly (`10,252`
numeric values, zero difference), reduces final artifact bytes `38.8%`, and
does not regress wall time. A single disposable-copy measurement of the
existing factorized Devanagari representative database preserves all
1,470,657 active-piece rows with identical digest and reduces completed
SQLite state from 1,221,271,552 to 69,447,680 bytes (`94.3%`) in 74.5 seconds.

Using the unchanged phoneme multiplier, compacted completed SQLite projects to
`6.55 GiB` and total completed output to `129.17 GiB`. These are projections,
not VM/full-corpus measurements. The pre-compaction transient projection stays
`366.69 GiB`, so production storage remains `NOT_READY` despite the accepted
persistent-storage improvement. Evidence is
`evidence/s1m2_local_optimization_14_v1.json`.

## Opt15 accepted; Opt16 is the only remaining round

Opt15 retires final-pass `piece_inventory` and `lexical_diagnostics` in the
same SQLite transaction that installs the authoritative active piece state and
completed-pass checkpoint. Parallel inspection now retires each reconstructible
worker shard immediately after successful canonical reduction, so shard bytes
are bounded by the rolling pending window rather than corpus size. Interrupted
runs regenerate already-retired shards from frozen inputs and durable active
parameters; focused resume and serial/parallel exactness tests pass.

A 24-document/two-worker bounded Devanagari measurement reduces peak bytes
from 3,738,727 to 2,247,509 (`39.9%`) with all seven artifacts byte-identical
and no targeted runtime regression. A read-only selective-compaction audit of
the existing representative database measures 533,065,728 training-diagnostic
bytes and 930,493,404 accumulated inspection-shard bytes. With an unchanged
historical WAL allowance and a conservative eight-worker pending-shard bound,
the transient projection falls from `366.69 GiB` to `229.86 GiB`. This is
`PROJECTION_NOT_VM_OR_FULL_CORPUS_MEASUREMENT`, not a production measurement.

The single fixed Devanagari probe passes all seven artifacts and 10,252 numeric
values with zero difference. Its one-shot wall changes from 0.790 to 0.985
seconds; the +0.195 second subsecond shift is recorded without a repeat, while
the targeted lifecycle measurement improves 26.0%. Evidence is
`evidence/s1m2_local_optimization_15_v1.json`.

Proceed only to Opt16: first measure how much immutable topology is rebuilt and
the bytes of a compact representation, then implement only if exact reweighting
can materially reduce the target phase without materially worsening the new
229.86 GiB transient projection. Do not rerun representative/stress/full-M0.

```text
S1M2_CONTINUOUS_CHEAP_PROFILE=COMPLETE
CONTINUOUS_SCRIPT_NEUTRAL_PROBE=PASS
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=COMPLETE_BOUNDED_LOCAL
S1M2_OPTIMIZATION_1=ACCEPTED
S1M2_OPTIMIZATION_2=ACCEPTED
S1M2_OPTIMIZATION_3=ACCEPTED
S1M2_OPTIMIZATION_4=ACCEPTED
S1M2_OPTIMIZATION_5=ACCEPTED
S1M2_OPTIMIZATION_6=ACCEPTED
S1M2_OPTIMIZATION_7=ACCEPTED_SMALL
S1M2_CONTINUOUS_REPRESENTATIVE_LOCAL=COMPLETE_VALIDATED
CONTINUOUS_SCRIPT_NEUTRAL_REPRESENTATIVE=PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
S1M2_CONTINUOUS_STRESS=DEFERRED_PENDING_STRUCTURAL_OPTIMIZATION
S1M2_CONTINUOUS_STRUCTURAL_FACTORIZATION=COMPLETE_BOUNDED_LOCAL
S1M2_OPTIMIZATION_8=ACCEPTED_TRAINING_ONLY
S1M2_OPTIMIZATION_9=ACCEPTED
S1M2_OPTIMIZATION_10=ACCEPTED
S1M2_OPTIMIZATION_11=REJECTED_REVERTED
S1M2_OPTIMIZATION_12=ACCEPTED
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_RECONCILED
S1M2_BOUNDED_ARTIFACT_COMPARATOR=SCHEMA_TYPED_KEYED_DISK_BACKED_FOCUSED_PASS
S1M2_FACTORIZED_REPRESENTATIVE_SCIENTIFIC_EQUIVALENCE=PASS_WITH_BOUNDED_PRESENTATION_CAVEATS
S1M2_REPRESENTATIVE_RERUN=FORBIDDEN_WITHOUT_NEW_CONTRADICTORY_EVIDENCE
S1M2_REPRESENTATIVE_AUDIT_RERUN=NOT_REQUIRED
S1M2_OPTIMIZATION_13=ACCEPTED
S1M2_OPTIMIZATION_14=ACCEPTED
S1M2_OPTIMIZATION_15=ACCEPTED
S1M2_OPTIMIZATION_16=ACCEPTED
PRODUCTION_STORAGE_GATE=PROJECTED_BELOW_300_GIB_NOT_VM_MEASURED
S1M2_LOCAL_OPTIMIZATION_TASK=COMPLETE
S1M2_LOCAL_OPTIMIZATION_RECOMMENDATION=STOP_LOCAL_OPTIMIZATION
```

## Opt16 accepted; stop local optimization

Opt16 compiles the verified immutable candidate/form/piece-prefix topology once
in training pass 1 and stores compact, reconstructible document-local records.
Passes 2/3 and final inspection stream one segment record at a time. Each phase
recomputes piece scores, segmentation-prior weights, forward/backward vectors,
posteriors, expected counts, and top-K score state from the current
authoritative piece parameters; none of that mutable state is cached.

The focused pieces/latent suite passes (`96 passed in 17.69s`), including an
explicit changed-piece-parameter reweight-versus-fresh-rebuild test,
interrupted resume, pass/shard retirement resume, and serial/parallel
scientific identity. The final bounded 3-document/64-line measurement compares
154,136 values exactly. Avoidable topology lifecycle overhead falls from
1.368 to 0.520 seconds (`61.99%`), while the all-in
compile/archive/decode/reweight pair improves `21.26%`; piece-score calls fall
`83.80%`.

The bounded compiled archive is 995,862 bytes (3.149 bytes/transition). Its
phoneme-scaled full-corpus projection is `11.60 GiB`, raising the accepted
Opt15 transient projection from `229.86` to `241.46 GiB`. This is
`PROJECTION_NOT_VM_OR_FULL_CORPUS_MEASUREMENT` and remains below the 300 GiB
host limit.

The one fixed Devanagari Opt16 probe passes all seven canonical artifacts
exactly (10,252 numeric values, zero difference). Its one-shot wall is 1.007
seconds versus 0.985 for Opt15; the +0.022 second subsecond shift was not
repeated. Evidence is `evidence/s1m2_local_optimization_16_v1.json`. No
representative, stress, VM, cloud, six-cell, or full-M0 run was performed.

Both authorized rounds are resolved. There is no remaining obvious structural
local target supported by current profiling evidence; do not open Opt17.
`STOP_LOCAL_OPTIMIZATION`. Any next session requires explicit authorization
and should address VM worker scaling, scheduling, and production readiness.

## Generic Windows Codex automation repaired; PreVM recovery remains researcher-controlled

The reusable framework is tracked in `.codex/automation/`. New and exact-ID
resume invocations now use the legal Codex CLI 0.153.2 unattended policy
`--approve-for-me` without a conflicting `--sandbox`. Exact TaskName/runtime
collisions still fail closed, while historical one-shot tasks and idle generic
peers can coexist. The runner retains its per-task lock and adds a canonical
repository mutex so only one generic runner can invoke Codex in one worktree;
contention safely skips a wake and different repositories remain independent.

`control_task.ps1` retains `Status`, `Wake`, and `ResumeExternal` and adds the
restricted `RecoverPreThread` action. It requires a disabled pre-thread
`LAUNCHER_ERROR`, empty thread identity, no `thread.started` evidence or last
message, intact frozen prompt hashes, normal clean branch/HEAD/remote gates,
and exact task action/config/repo/fixed-trigger identity. It preserves the
existing trigger and adds an immediate wake only with explicit `-StartNow`.
The Windows PowerShell 5.1 static parse and one focused suite pass 12 contract
groups in 4.096 seconds. The repair created no task and started no Codex.

The existing `SKTLM-S1M2-PreVM-Closure` task was inspected read-only. It is
Disabled in `LAUNCHER_ERROR`, has null `thread_id`, empty JSONL, no last message,
matching prompt hashes, and matching action/config/repo/trigger identity. After
the repair commit is clean and pushed, the sole next action is an explicit
researcher `RecoverPreThread` command without `-StartNow` unless the researcher
also wants an immediate extra wake. Do not edit state, inject a thread ID,
reinstall, or alter the fixed trigger. S1M2 Pre-VM Closure remains not started.

```text
GENERIC_CODEX_WINDOWS_AUTOMATION=COMPLETE_REPAIRED
S1M2_PREVM_CLOSURE=NOT_STARTED_INSTALLED_PRETHREAD_FAILURE
S1M2_PREVM_NEXT_ACTION=RESEARCHER_RECOVER_PRETHREAD
ACTUAL_SCHEDULED_TASK_CREATED_BY_REPAIR=NO
CODEX_AUTOMATION_STARTED_BY_REPAIR=NO
```

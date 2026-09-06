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
continuous runtime target: NOT READY
production storage gate: NOT READY
optimization 8 shared token-local form-prefix DP: ACCEPTED (training marginals)
optimization 9 shared inspection marginals/top-K: ACCEPTED
optimization 10 shared bounded piece-prefix top-K: ACCEPTED
optimization 11 token-local lexical-form interning: REJECTED / REVERTED
optimization 12 exact bounded Cartesian top-K merge: ACCEPTED
factorized local representative benchmark: COMPLETE / RECONCILED
bounded streaming artifact comparator: SCHEMA-TYPED KEYED DISK-BACKED / FOCUSED PASS
optimization 13 ordered SQLite inspection-shard reduction: ACCEPTED
optimization 14 artifact/storage architecture: READY
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

Proceed only to Opt14 storage/artifact architecture. Do not run another local
optimization, representative, stress, VM, cloud, or full-M0 workload.

```text
S1M2_CONTINUOUS_CHEAP_PROFILE=COMPLETE
CONTINUOUS_SCRIPT_NEUTRAL_PROBE=PASS
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
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
S1M2_CONTINUOUS_STRUCTURAL_FACTORIZATION=IN_PROGRESS
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
S1M2_OPTIMIZATION_14=READY
```

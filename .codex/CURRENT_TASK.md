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
optimization 11 token-local lexical-form interning: IMPLEMENTED / EQUIVALENT
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

## Next task: fixed cheap probe for optimization 11

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

Optimization 11 replaces the shared evaluator's separate unique-form table
with a token-local interner keyed by the already-required phoneme tuple. All
span positions and evidence remain distinct, but repeated equal lexical forms
reuse one immutable `PhonologicalForm`; the already-enumerated identity span is
also reused. The structure dies with the token and has the same unique-form
cardinality as the removed table. Focused P1c and pieces/latent tests pass (`90
passed`). Commit and push this coherent candidate, then run the fixed paired
probe exactly once. Compare all canonical artifacts plus `PhonologicalForm`
construction counts and shared-batch/span timings against optimization 10.
Reject it if the measured construction mechanism does not improve. Do not
rerun representative, stress, cloud, or full-M0 yet.

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
S1M2_OPTIMIZATION_11=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
```

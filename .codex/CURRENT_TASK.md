# CURRENT_TASK.md

## Authoritative current status (2026-09-09)

Branch: `exp/s1m2-reusable-pieces`.

```text
S1M1=FROZEN
M0_PRIME=COMPLETE_VALID
S1M2_METHOD=COMPLETE
S1M2_LOCAL_OPTIMIZATION=COMPLETE
S1M2_OPTIMIZATION_16=ACCEPTED
OPT16_TOPOLOGY_RECONSTRUCTIBILITY=PASS
OPT17=EXACTNESS_PASS_RAM_FAIL_DURING_INSPECTION
OPT18A=RAM_VALIDATED
OPT18B=RAM_VALIDATED_RUNTIME_FAIL
OPT19=IMPLEMENTED_AWAITING_MANUAL_RAM_RUNTIME_VALIDATION
POST_OPT16_ENGINEERING_OPTIMIZATION=AUTHORIZED
SINGLE_WORKER_PEAK_RSS_TARGET=IDEAL_LE_1.25_GIB_PRIMARY_LE_1.5_GIB
CURRENT_OPTIMIZATION=OPT19_COMPLETE_AWAITING_MANUAL_VALIDATION
S1M2_SIX_CELL_CONTRACT=FROZEN
ROUND1_INTERFACE=READY
ROUND1_AGGREGATOR=READY
ROUND2_INTERFACE=READY
ROUND2_GATES=READY
PROVENANCE=READY
FINAL_SIX_CELL_GENERATOR=READY
S1M2_SIX_CELL_BOUNDED_VALIDATION=PASS
FULL_REPO_GATE=PENDING_ONE_FINAL_RUN
PRE_VM_INTERFACE_STATE=READY
ROUND1_STATUS=FAILED_OOM
ROUND2_STATUS=NOT_STARTED
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=COLLABORATOR_VALIDATE_OPT19_INSPECTION_ONLY_W1
```

The authoritative machine-readable contract is
`configs/production/s1m2_six_cell.json`; the deployment contract is
`configs/cloud/s1m2_prevm.yaml`. Both Round 1 and Round 2 are six-way parallel
on `core-01` through `core-06`; S1M2 production deployment is verified
`git_bundle` at the explicit branch and SHA.

The external Opt17 exact artifact comparison passed. Its single-worker stress
run completed its requested training pass, then inspection RSS exceeded 6.5
GiB and was manually interrupted while still rising. The retained SQLite and
JSON checkpoints are identical (`completed_passes=1`, `active_pass=null`),
`piece_lexicon` exactly matches the final history totals, no next-pass table
exists, and canonical inspection completion was not claimed. This directory is
therefore a legal Opt18 inspection-only input:

`artifacts/s1m2_benchmarks/s1m2_continuous_stress_m0_devanagari_opt17_2369312_w1_p1_a01`

Opt18 separates durable training from reconstructible final inspection through
`--stop-after-training`, `--inspection-only`, and execution-only
`--inspection-workers`. Inspection-only validates frozen/config/provenance
identity, exact DB/JSON checkpoint equality, completed pass history, and the
final learned table before touching inspection state. It never enters a
training pass and preserves `provenance.json`; a separate atomic
`inspection_provenance.json` records implementation commit, worker count,
attempt, training commit, and canonical hashes.

Inspection RAM is now bounded by compact shared top-K backpointers, a bounded
token-local top-segmentation cache, deferred factor-local posterior evaluation,
immediate factor payload release, and reconstruction of legal-piece support
instead of retaining every form-to-piece tuple. Scoring, support, ordering,
posterior, and artifact semantics are unchanged. Training keeps its original
single inference pass, so the RAM fix does not double full-corpus training CPU.

The archived record immediately after the 19 completed inspection rows proves
the stress-specific trigger: line 39 has one factor, 88,398 prefix nodes,
34,602 forms, and depth sum 16,069,373. The old eager representation estimated
128,554,984 retained piece references, tripped the 4,194,304 gate, and fell
back to the legacy occurrence/top-K materialization path. The new shared
backpointer representation requires 707,184 actual one-piece path records and
therefore remains on the bounded shared exact path. The all-factor summary
tuple was a general retention risk, but not the multiplicative stress trigger
because this continuous segment has only one factor.

The archived record immediately after the 19 completed inspection rows proves
the stress-specific trigger: line 39 has one factor, 88,398 prefix nodes,
34,602 forms, and depth sum 16,069,373. The old eager representation estimated
128,554,984 retained piece references, tripped the 4,194,304 gate, and fell
back to the legacy occurrence/top-K materialization path. The new shared
backpointer representation requires 707,184 actual one-piece path records and
therefore remains on the bounded shared exact path. The all-factor summary
tuple was a general retention risk, but not the multiplicative stress trigger
because this continuous segment has only one factor.

Exactly one focused pytest invocation was made: 6 passed and 2 failed because
the new scalar prepass initially used a different floating-point association
for `prior + piece_score`. The implementation was corrected to match the
original evaluator operation exactly; the suite was intentionally not rerun to
respect the one-invocation cap. Static compilation and diff checks pass after
the correction. No stress, representative, Round 1/2, VM/cloud, 72-document,
three-pass, production-like, or full-M0 workload ran in this session.

The collaborator's Opt18 inspection-only attempt completed pathological line
39 with peak process-tree RSS about 0.747 GiB and later RSS about 0.438 GiB,
confirming the bounded-memory repair. It was manually stopped after more than
two hours before the first stress document completed; the active process used
about 96% of one CPU core. Opt18 is therefore RAM-valid but runtime-invalid.

Opt19 implements deterministic adaptive factor retention. During inspection,
each factor with a trusted structural estimate is fully evaluated once and its
`_FactorSummary` retained when it fits the remaining segment-local 320 MiB
logical budget. The retained payload is limited to final factor scalar and
posterior summaries, compact form/coordinate occurrence support, boundary/rule
maps, and bounded final top paths. Shared-batch alpha/transition arrays, prefix
backpointers, and span tables remain factor-local and are released before the
summary returns. Factors with missing/untrusted topology, incompatible shared
conditions, arithmetic overflow, or insufficient remaining budget use the
unchanged Opt18 score-only prepass followed by exact posterior recomputation
and immediate release.

The fixed `sktlm-opt19-factor-summary/v1` estimate is:

`4096 + 8*Nprefix + 4*Ntransition + Dprefix + 320*Nform + 160*Npiece + 80*Noccurrence_upper + 192*Nlattice_node + 64*K*(1+max_form_depth)` bytes.

Admission is canonical factor order with `estimate <= 320 MiB - cumulative`.
The budget is execution-only and absent from `TrainingConfig.payload()`, so the
existing Opt17 final learned state remains directly reusable. Inspection
provenance records the formula and budget. Telemetry records fast-path,
two-pass, recomputed factors, and retained-budget peak.

The sole focused pytest invocation passed (`3 passed in 2.49s`). Post-test
Python compilation and `git diff --check` passed. No stress, representative,
full-M0, VM/cloud, training, or other long workload ran.

The sole next action is the single-worker inspection-only RAM/runtime benchmark
against the preserved Opt17 training state:

```powershell
.\.venv\Scripts\python.exe -m sktlm.latent.benchmark --benchmark s1m2_continuous_stress_m0_devanagari --run-id s1m2_continuous_stress_m0_devanagari_opt17_2369312_w1_p1_a01 --output-root artifacts/s1m2_benchmarks --passes 1 --workers 1 --inspection-only --inspection-workers 1 --inspection-retained-factor-bytes 335544320
```

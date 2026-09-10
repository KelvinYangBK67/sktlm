# CURRENT_TASK.md

## Authoritative current status (2026-09-10)

Branch: `exp/s1m2-reusable-pieces`.

```text
S1M1=FROZEN
M0_PRIME=COMPLETE_VALID
S1M2_METHOD=COMPLETE
S1M2_LOCAL_OPTIMIZATION=COMPLETE
OPT17=TRAINING_RAM_PASS_INSPECTION_RAM_FAIL_STATE_REUSABLE
OPT18=RAM_PASS_RUNTIME_FAIL
OPT19=LOCAL_EXACTNESS_PASS_RAM_GATE_PASS_RUNTIME_GATE_PASS
S1M2_EXECUTION_BUNDLE_AUDIT=PASS
S1M2_EXECUTION_BUNDLE_SCHEDULER=IMPLEMENTED_TINY_VALIDATION_PASS
S1M2_EXECUTION_BUNDLE_PLAN=CANDIDATE_008192
ROUND1_STATUS=MANUALLY_TERMINATED_AFTER_DIAGNOSTIC_CONVERGENCE
ROUND1_FORMAL_WINNER=UNRESOLVED
ROUND1_WORKER_SEARCH_LOWER_BOUND=12
ROUND1_NEXT_WORKER_CANDIDATES=12_16_24
OLD_ROUND2_READINESS=RETIRED
ROUND2_MODE=BUNDLE_WORKER_RECALIBRATION
ROUND2_PRIMARY_WORKERS=12_16_24
ROUND2_WORKER_20_STATUS=RESERVED_IF_DECISION_CRITICAL
ROUND2_REPRESENTATIVE_PLAN=MATERIALIZATION_REQUIRED
ROUND2_STRESS_PLAN=MATERIALIZATION_REQUIRED
ROUND2_STATUS=NOT_STARTED
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=RESEARCHER_PRE_ROUND2_MATERIALIZATION
```

The authoritative production contract is
`configs/production/s1m2_six_cell.json`; the deployment contract is
`configs/cloud/s1m2_prevm.yaml`. The former six-science-workload Round2
readiness gate is superseded by Decision 114 and has no active compatibility
path or replacement stage.

## Active Round2 contract

Round2 is the final engineering worker-selection stage before the unchanged
full six-cell production plan:

```text
core-01  M0 Devanagari continuous  representative  workers=12
core-02  M0 Devanagari continuous  representative  workers=16
core-03  M0 Devanagari continuous  representative  workers=24
core-04  M0 Devanagari continuous  stress          workers=12
core-05  M0 Devanagari continuous  stress          workers=16
core-06  M0 Devanagari continuous  stress          workers=24
```

Every job uses `model=reusable_pieces_v1`, three passes, exact inference, and
bundle execution. Representative and stress retain their frozen tracked
document lists. Their subset bundle plans must use:

```text
target_pressure=279047
max_segments_per_bundle=256
max_segment_tokens=128
ObservedSegment atomicity=unchanged
```

The planner accepts `--document-list` in exact listed order and
`--target-pressure`. It writes one co-located materialization containing
`scan_summary.json`, `summary.json`, `bundles.jsonl`, and `documents.tsv`.
Plan generation fails closed until both materializations exist and bind their
manifest, document-list, representation sequence, segment sequence, plan, and
materialization identities. Generated trainer commands include
`--execution-bundle-plan` and the per-job worker count.

## Selection and full dependency

A worker candidate is eligible only when both representative and stress pass
completion, artifact, provenance, zero-overflow, memory, and storage gates.
Each workload keeps the existing 10% practical wall-time threshold. A practical
tie prefers lower process-tree peak RSS, lower canonical reducer stall, then
fewer workers. Agreement produces `ROUND2_STATUS=PASS` and
`WINNER_WORKERS`. A decision-critical workload disagreement produces
`ROUND2_STATUS=NEEDS_W20_INTERPOLATION` and two prepared w20 follow-up job
specifications; it never runs them automatically.

The final six-cell generator depends only on a bound Round2 PASS result and its
eligible `WINNER_WORKERS`. It no longer depends on a Round1 formal winner or
the retired readiness matrix. Full science cells remain unchanged.

## What has not run

No representative/stress subset plan has been materialized. No pytest, unit,
synthetic, exactness, resume, scheduler, corpus smoke, training, Round2, VM,
RAM/runtime benchmark, profiling, or full-M0 workload ran in PRE-ROUND2.

## Next action

The researcher should materialize the representative and stress plans with the
commands in
`reports/core_methods/reusable_pieces/s1m2_pre_round2_bundle_worker_recalibration_20260910.md`
or the final PRE-ROUND2 handoff, inspect their compact summaries, then generate
the Round2 plan. Do not launch until both materialization identities are bound.

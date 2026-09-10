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
ROUND2_WORKER_20_STATUS=NOT_REQUIRED
ROUND2_REPRESENTATIVE_PLAN=MATERIALIZED
ROUND2_STRESS_PLAN=MATERIALIZED
ROUND2_EXECUTION=COMPLETE
ROUND2_FORMAL_SCIENTIFIC_STATUS=FAIL_CANDIDATE_OVERFLOW
ROUND2_FORMAL_WINNER=NONE
ROUND2_ENGINEERING_SCALING=CLOSED
ROUND2_ENGINEERING_PREFERENCE_WORKERS=12
ROUND2_WORKER_COUNT_SCIENTIFIC_EQUIVALENCE=PASS
ROUND2_OLD_NEW_INSPECTION_EQUIVALENCE=PASS_RESEARCHER_MANUAL
FULL_M0_PROCESS_RUNNING=NO
FULL_M0_AUTHORIZED=NO
NEXT_ACTION=BOUNDED_CANDIDATE_OVERFLOW_FORENSIC
```

The authoritative production contract is
`configs/production/s1m2_six_cell.json`; the deployment contract is
`configs/cloud/s1m2_prevm.yaml`. The former six-science-workload Round2
readiness gate is superseded by Decision 114 and has no active compatibility
path or replacement stage.

## Executed Round2 contract

Round2 executed the following six-job worker matrix:

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
document lists. Their materialized subset bundle plans use:

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

## Outcome and full dependency

All six jobs completed three passes and inspection. Representative has zero
candidate overflow at every worker count. Stress has 34 overflowed tokens in
each training pass and 34 in inspection at every worker count. Overflow clears
the affected internal match list after raw matches exceed 512, so it is true
candidate-space truncation. No worker passes both frozen workloads; Round2 is
formally FAIL with no scientific winner, and Full production is not authorized.

Worker-count scientific artifacts are identical within each workload. The
inspection-only bundle calibration has no greater-than-10% wall-time winner;
the existing RSS/stall/worker-count tie-break makes 12 workers the engineering
preference. The researcher manually confirmed all six old-vs-new inspection
artifact comparisons as `ALL_IDENTICAL`; this closure did not rerun them.

The full evidence and typed result are recorded in
`reports/core_methods/reusable_pieces/s1m2_round2_closure_20260910.md`.

## Closure boundary

No pytest, benchmark, production command, VM/cloud workload, or experiment was
run for documentation closure. Existing Round2 evidence was read only.

## Next action

Run a separately authorized bounded forensic on the 34 stress overflow cases.
Do not relax the zero-overflow gate, change `max_internal_matches`, or begin
Full-production wiring as part of this documentation handoff.

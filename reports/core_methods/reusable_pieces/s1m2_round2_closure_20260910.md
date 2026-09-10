# S1M2 Round 2 closure

Date: 2026-09-10

This checkpoint closes the bounded Round 2 worker-calibration record. It does
not change the model, candidate generator, trainer, schedulers, production
contract, or frozen data. No experiment was rerun for this report.

## Result classification

| Class | Result | Meaning |
|---|---|---|
| **Formal scientific result** | **FAIL / no formal winner** | All three stress runs violate the frozen zero-candidate-overflow gate. No worker is eligible across both workloads. |
| **Engineering scaling result** | **CLOSED; 12 workers preferred** | The six completed runs and the later inspection-only calibration give useful scaling evidence. No candidate gains more than 10% in inspection wall time; the existing tie-break selects 12 workers for lower RSS, then stall and worker count. |
| **Diagnostic finding** | **34 stress overflows per phase** | The limit path discards all internal matches when the raw count exceeds 512. This is genuine candidate-space truncation, not retention of the first 512 candidates. |

The formal and engineering results must not be collapsed into a single PASS.
The engineering preference is not a frozen-contract production winner.

## Experimental design

Round 2 used deployment baseline
`fc67797a238d5d6701f7157a31fef1f95438025d`, production-plan SHA-256
`0f2f15ff3d9aaedbeb432af20866fd246b786bf0fd3cd9479ec4d0674a58c456`,
and production-contract SHA-256
`f8684597c061f6608569042e69fa8a0fed9badd14a413976abcd12a8d62cd92d`.
All jobs used M0 Devanagari `continuous`, `reusable_pieces_v1`, three passes,
exact inference, `max_internal_matches=512`, and complete ObservedSegment
bundles. Worker count was the only calibration variable.

| Host | Workload | Workers |
|---|---|---:|
| core-01 | representative | 12 |
| core-02 | representative | 16 |
| core-03 | representative | 24 |
| core-04 | stress | 12 |
| core-05 | stress | 16 |
| core-06 | stress | 24 |

The representative workload is the frozen three-document list at
`configs/benchmarks/s1m2_continuous_representative_documents.txt`; the stress
workload is the frozen two-document list at
`configs/benchmarks/s1m2_continuous_stress_documents.txt`.

## Bundle plans

Both plans use deterministic, contiguous, document-local packing with complete
ObservedSegments, target pressure 279,047, at most 256 segments per bundle,
and maximum 128 tokens per segment.

| Workload | Documents | Segments | Bundles | Max bundles/document | Oversized singleton bundles | Plan SHA-256 | Materialization SHA-256 |
|---|---:|---:|---:|---:|---:|---|---|
| representative | 3 | 12,306 | 64 | 42 | 0 | `428cdc53169e5d5c518e3c1fcff86218fedd90cf5e761bb0e8848a5cd57554d7` | `88195f7f97cf14965a6ce28616809e44647f7e2ef31b33b1ef9e3e5c1c9f5d80` |
| stress | 2 | 241 | 73 | 45 | 30 | `f2d5a35d7afaef3c39c8efca6872898be8b0d35330aeb72554a26919c9c7b72a` | `f32b377b082861006617dfd3b10dcc1aa23c2ae32e4ff49480409a239ea18fff` |

The stress plan's oversized singleton bundles follow from ObservedSegment
atomicity; they are not split to satisfy the pressure target.

## Six-cell Round 2 results

The formal attestations record completed three-pass training and inspection
for every job. RSS is the sampled simultaneous process-tree peak.

| Host | Workload | Workers | Wall seconds | Peak RSS GiB | Reducer stall seconds | Candidate overflow | Formal audit |
|---|---|---:|---:|---:|---:|---:|---|
| core-01 | representative | 12 | 3159.473 | 1.272 | 2015.503 | 0 | PASS |
| core-02 | representative | 16 | 3175.010 | 1.644 | 1954.215 | 0 | PASS |
| core-03 | representative | 24 | 3178.806 | 2.289 | 1867.100 | 0 | PASS |
| core-04 | stress | 12 | 4797.169 | 4.570 | 3662.447 | 34 | FAIL |
| core-05 | stress | 16 | 4814.433 | 5.488 | 3665.529 | 34 | FAIL |
| core-06 | stress | 24 | 4993.705 | 6.631 | 3755.834 | 34 | FAIL |

The representative runs pass every recorded formal gate. The stress runs
finish and remain deterministic, but each fails `require_zero_candidate_overflow`.
Consequently `ROUND2_STATUS=FAIL`, `WINNER_WORKERS=null`, and
`WINNER_REASON=no_worker_passed_both_workloads`. Worker 20 is not required by
this result.

## Training bundle scheduler

Training schedules complete ObservedSegment bundles dynamically. Completed
futures leave true inflight capacity immediately; ready-but-canonically-blocked
results are held separately while later work continues to refill the pool.
Disk-backed bundle results are coalesced in canonical document/segment order,
and topology archives remain reconstructible execution caches. This changes
execution granularity only, not scientific reduction order or identity.

## Inspection underparallelization and repair

The deployed Round 2 baseline still scheduled one inspection Future per
document. With only three representative documents and two stress documents,
12/16/24 workers could not be meaningfully exercised during the heavy
inspection phase. Commit `ff2f076d6273bbb9ac67bd77392f983ce738b336`
subsequently extended the existing execution-bundle design to inspection:
complete within-document ObservedSegment bundles execute dynamically and are
coalesced back into the unchanged document-level outputs in canonical order.
This is execution-only and supports inspection-only reuse of completed learned
state and topology archives.

## Inspection-only calibration

The six inspection-only runs used commit
`ff2f076d6273bbb9ac67bd77392f983ce738b336`. The process-tree wall clock below
includes wrapper/finalization overhead; `inspection parallel wall` and reducer
stall come from the run timing artifact.

| Host | Workload | Workers | Process-tree wall seconds | Inspection parallel wall seconds | Peak RSS GiB | Reducer stall seconds |
|---|---|---:|---:|---:|---:|---:|
| core-01 | representative | 12 | 609.575 | 460.579 | 1.298 | 187.084 |
| core-02 | representative | 16 | 610.664 | 460.039 | 1.657 | 162.380 |
| core-03 | representative | 24 | 598.114 | 447.677 | 2.317 | 95.179 |
| core-04 | stress | 12 | 917.191 | 749.175 | 5.146 | 589.112 |
| core-05 | stress | 16 | 846.032 | 679.869 | 6.271 | 521.336 |
| core-06 | stress | 24 | 849.492 | 686.248 | 7.881 | 474.574 |

No worker count has a greater-than-10% inspection wall-time advantage. For
representative, 12 is 1.9% slower than the fastest 24-worker run; for stress,
12 is 8.4% slower than the fastest 16-worker run. All remain in the practical
tie envelope. Applying the frozen ordering—lower process-tree peak RSS, then
lower reducer stall, then fewer workers—makes 12 the engineering preference
for both workloads. More workers reduce reducer stall but increase RSS without
a qualifying wall-time gain.

## Scientific equivalence

Within each workload, all seven recorded scientific artifacts have identical
SHA-256 values at 12, 16, and 24 workers:
`iteration_metrics.json`, `piece_inventory.tsv`, `lexical_diagnostics.tsv`,
`analyses.jsonl`, `boundary_posteriors.jsonl`, `rule_usage.tsv`, and
`summary.json`. This establishes worker-count determinism for the observed
runs. It does not make the truncated stress result formally valid.

The calibration collection retains `scientific_equivalence_valid=false`, so
that generated summary is not itself authority for old-scheduler/new-scheduler
equivalence. The researcher separately ran the six old-vs-new artifact
comparisons manually and reports `ALL_IDENTICAL`. This closure records that
manual confirmation as PASS and does not rerun it or rewrite the historical
generated JSON.

## Candidate-overflow diagnostic

Representative has zero overflow in all passes and inspection. Stress records
34 overflowed tokens in pass 1, 34 in pass 2, 34 in pass 3, and 34 in final
inspection for every worker count. The implementation computes all raw
internal matches, tests whether their count exceeds 512, and on overflow sets
the retained match list to empty. It therefore removes the entire internal
candidate set for the affected token rather than retaining a deterministic
first 512. The resulting analyses are stable across workers but use a
truncated candidate space.

This is the blocking scientific fact. The frozen exact-science contract and
zero-overflow gate remain unchanged; this report neither raises the limit nor
relaxes the gate.

## Conclusions and next boundary

**Formal scientific result:** Round 2 fails. There is no eligible
frozen-contract worker winner, and Full production is not authorized by this
Round 2 result.

**Engineering scaling result:** dynamic ObservedSegment bundles work for both
training and inspection. The measured 12/16/24 inspection runs are a practical
tie, with 12 workers preferred for substantially lower memory. This preference
is useful engineering evidence only.

**Diagnostic finding:** the stress workload reliably exposes 34 affected
tokens and a fail-closed exact-science boundary. The next task is a bounded
candidate-overflow forensic that determines how the exact candidate support
can be represented without truncation. Full-production wiring may be revisited
only after that boundary is resolved. Neither task is started here.

## Evidence read for this closure

- `artifacts/s1m2_production/round2_plan.json`
- `artifacts/s1m2_production/round2_result_20260910T103847Z.json`
- `artifacts/s1m2_vm/round2_attestation_collection_20260910T103847Z.json`
- `artifacts/s1m2_vm/round2_attestations_20260910T103847Z/`
- `artifacts/s1m2_vm/round2_compact_evidence_20260910T103847Z/`
- `artifacts/s1m2_vm/inspection_calibration_final_20260910T105928Z/`
- `artifacts/s1m2_execution_bundle_plans/round2_representative_tp279047/`
- `artifacts/s1m2_execution_bundle_plans/round2_stress_tp279047/`

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
OPT17=IMPLEMENTED_AWAITING_MANUAL_VALIDATION
POST_OPT16_ENGINEERING_OPTIMIZATION=AUTHORIZED
SINGLE_WORKER_PEAK_RSS_TARGET=<10GiB
CURRENT_OPTIMIZATION=COMPLETE_AWAITING_MANUAL_VALIDATION
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
NEXT_ACTION=COLLABORATOR_RUN_EXACTNESS_AND_SINGLE_WORKER_MEMORY_PROBES
```

The authoritative machine-readable contract is
`configs/production/s1m2_six_cell.json`; the deployment contract is
`configs/cloud/s1m2_prevm.yaml`. Both Round 1 and Round 2 are six-way parallel
on `core-01` through `core-06`; S1M2 production deployment is verified
`git_bundle` at the explicit branch and SHA.

Round 1 stopped on single-worker OOM. Opt17 now keeps shared zero-epsilon
occurrences as compact form-level integer support and defers per-piece
cardinality aggregation. The weighted legacy threshold route and merged-word
support remain unchanged.

The one focused local command passed four selected tests. No Round 1, Round 2,
VM/cloud, representative, stress, full-M0, or production-like RAM probe ran.
After push, the collaborator must run the fixed artifact exactness and
single-worker memory probes; the less-than-10-GiB target is not yet validated.

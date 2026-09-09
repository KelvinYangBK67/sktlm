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
OPT17=AUTHORIZED
POST_OPT16_ENGINEERING_OPTIMIZATION=AUTHORIZED
SINGLE_WORKER_PEAK_RSS_TARGET=<10GiB
CURRENT_OPTIMIZATION=OPT17_COMPACT_OCCURRENCE_SUPPORT
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
NEXT_ACTION=IMPLEMENT_OPT17_THEN_DETACH_FOR_MANUAL_VALIDATION
```

The authoritative machine-readable contract is
`configs/production/s1m2_six_cell.json`; the deployment contract is
`configs/cloud/s1m2_prevm.yaml`. Both Round 1 and Round 2 are six-way parallel
on `core-01` through `core-06`; S1M2 production deployment is verified
`git_bundle` at the explicit branch and SHA.

Round 1 stopped on single-worker OOM. The authorized next step is only Opt17:
compact the production shared zero-epsilon occurrence-support representation
without changing candidate support, scoring, posterior equations, support
semantics, or observable output.

Do not run Round 1, Round 2, VM/cloud, representative, stress, full-M0, or a
production-like RAM probe in this session. After one focused local test, commit
and push Opt17, then detach for collaborator-run exactness and memory validation.

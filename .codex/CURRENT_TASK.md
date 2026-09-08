# CURRENT_TASK.md

## Authoritative current status (2026-09-08)

Branch: `exp/s1m2-reusable-pieces`.

```text
S1M1=FROZEN
M0_PRIME=COMPLETE_VALID
S1M2_METHOD=COMPLETE
S1M2_LOCAL_OPTIMIZATION=COMPLETE
S1M2_OPTIMIZATION_16=ACCEPTED
OPT16_TOPOLOGY_RECONSTRUCTIBILITY=PASS
OPT17=NOT_AUTHORIZED
S1M2_SIX_CELL_CONTRACT=FROZEN
ROUND1_INTERFACE=READY
ROUND1_AGGREGATOR=READY
ROUND2_INTERFACE=READY
ROUND2_GATES=READY
PROVENANCE=READY
FINAL_SIX_CELL_GENERATOR=READY
S1M2_SIX_CELL_BOUNDED_VALIDATION=PASS
FULL_REPO_GATE=PENDING_ONE_FINAL_RUN
PRE_VM_INTERFACE_STATE=REFREEZE_IN_PROGRESS
ROUND1_STATUS=NOT_STARTED
ROUND2_STATUS=NOT_STARTED
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=COMPLETE_CHEAP_LOCAL_CLOSURE
```

The authoritative machine-readable contract is
`configs/production/s1m2_six_cell.json`; the deployment contract is
`configs/cloud/s1m2_prevm.yaml`. Both Round 1 and Round 2 are six-way parallel
on `core-01` through `core-06`; S1M2 production deployment is verified
`git_bundle` at the explicit branch and SHA.

The earlier bounded six-cell interface evidence remains valid and is not being
rerun. Finish the focused control-plane gates, the single permitted full-suite
gate, clean-SHA plan inspection, evidence/state refresh, push, and verified
bundle creation. No representative, stress, VM, cloud, Round 1, Round 2, or
full-M0 workload may run during this closure.

The generic cloud framework from published `main` is merged. The tracked
six-host helper provides preflight, bundle deploy, idempotent Python 3.11
environment setup, validate-before-sync frozen inputs, remote validation, and
detached plan-driven Round 1 launch. The operator must not use it until the
closing session reports the new clean pushed `PRE_VM_S1M2_SHA` and bundle hash.

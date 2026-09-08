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
FULL_REPO_GATE=PASS_669_TESTS
PRE_VM_INTERFACE_STATE=READY
ROUND1_STATUS=NOT_STARTED
ROUND2_STATUS=NOT_STARTED
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=MANUAL_VM_ROUND1
```

The authoritative machine-readable contract is
`configs/production/s1m2_six_cell.json` (canonical SHA-256
`5e5591d844e7181a8fc51f405d1ad1c8a73ce99809f24e6096dd75a722e9df29`).
The implementation/config/interface candidate was tested cleanly at
`dd19b3bfea314ff83f3298dba46d4bc6b1d1f7de`; use the final pushed HEAD
reported by the closing session as `PRE_VM_S1M2_SHA`.

Focused validation: `76 passed in 13.73s`. Full repository validation:
`669 passed, 2 warnings in 61.74s`. The clean bounded six-cell run passed all
six artifact/config/checkpoint/provenance/storage audits and all three matched
script-neutral production-path comparisons. Evidence is
`evidence/s1m2_prevm_closure_v1.json`. No representative, stress, VM, cloud,
or full-M0 workload ran.

The only next action requires the researcher/VM. Deploy the final clean pushed
`PRE_VM_S1M2_SHA` using the established verified Git-bundle workflow, activate
the repository Python environment on Linux, validate the contract, and create
the immutable Round 1 plan:

```text
python -m sktlm.production.s1m2 validate-contract
python -m sktlm.production.s1m2 plan-round1 --output artifacts/s1m2_production/round1_plan.json
```

Then execute the six `launch_command_shell` values sequentially in plan order.
Do not run them concurrently on the single `s1m2-vm-01` role. The exact worker
vector is `4,8,12,16,20,24`; all six jobs use the same frozen Devanagari
continuous representative workload and scientific configuration. After all
jobs report `result_status=PASS`, run:

```text
python -m sktlm.production.s1m2 aggregate-round1 --plan artifacts/s1m2_production/round1_plan.json --output artifacts/s1m2_production/round1_result.json
```

PASS requires six valid jobs, exact artifact/provenance audits, zero candidate
overflow, memory/storage safety, and a machine-readable `ROUND1_STATUS=PASS`
with `WINNER_WORKERS`. Do not proceed to Round 2 on any failure. Round 2, its
gate evaluator, and the gated final six-cell generator are documented in
`docs/workflows/s1m2_prevm.md`.

Do not open Opt17, tune candidates, alter exact inference, change the fixed
1,218-rule grammar, rerun frozen local representative evidence, launch a full
cell, or touch `notes/**`.

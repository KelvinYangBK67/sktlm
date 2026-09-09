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
OPT17=TRAINING_RAM_PASS_INSPECTION_RAM_FAIL_STATE_REUSABLE
OPT18=RAM_PASS_RUNTIME_FAIL
OPT19=LOCAL_EXACTNESS_PASS_RAM_GATE_PASS_RUNTIME_GATE_PASS
POST_OPT16_ENGINEERING_OPTIMIZATION=COMPLETE
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
PRE_VM_ENGINEERING_STATE=READY
ROUND1_STATUS=MANUALLY_TERMINATED_AFTER_DIAGNOSTIC_CONVERGENCE
ROUND1_FORMAL_WINNER=UNRESOLVED
ROUND1_WORKER_SEARCH_LOWER_BOUND=12
ROUND1_NEXT_WORKER_CANDIDATES=12_16_24
ROUND1_STRAGGLER=DOCUMENT_INDEX_50_CONFIRMED
ROUND1_EVIDENCE_CLASSIFICATION=DIAGNOSTIC_VALID
ROUND2_STATUS=NOT_STARTED
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=PRE_FULL_UNIT_GRANULARITY_AUDIT
```

The authoritative machine-readable contract is
`configs/production/s1m2_six_cell.json`; the deployment contract is
`configs/cloud/s1m2_prevm.yaml`. Both Round 1 and Round 2 are six-way parallel
on `core-01` through `core-06`; S1M2 production deployment is verified
`git_bundle` at the explicit branch and SHA.

## Consolidated Opt17 / Opt18 / Opt19 engineering record

### Opt17

Opt17 solved the training-memory problem. On the Devanagari-continuous stress
workload, training stayed around 0.2--0.3 GiB RSS with a transient peak around
0.79 GiB. Final inspection remained unbounded: RSS continued climbing past
6.5 GiB and the run was manually interrupted. The completed training state was
audited as internally consistent and remains directly reusable.

### Opt18

Opt18 decoupled durable training from reconstructible inspection and repaired
the inspection working set with bounded shared top-K backpointers, bounded
token-local caches, factor-local posterior recomputation, immediate release,
and compact occurrence support. The pathological line 39 completed.

At line 47 the recorded state was:

```text
elapsed=00:22:33
RSS=0.708 GiB
peak RSS=0.747 GiB
```

RSS later returned to about 0.44 GiB, confirming bounded-memory behavior.
Runtime remained unacceptable: after more than two hours the first stress
document was still incomplete. Opt18 conclusion: `RAM PASS / runtime FAIL`.

### Opt19

Opt19 implements adaptive one-pass/two-pass inspection retention. Small factors
whose deterministic structural estimate fits the remaining segment-local
budget retain their complete posterior summary through the outer DP; other
factors use the Opt18 score-only prepass, posterior recomputation, and immediate
release.

Manual synthetic mixed-path validation passed:

```text
factors=4
fast_path=1
two_pass=3
recomputed=3
budget=32678
retained_budget_peak=32678
scientific_outputs=EXACT_EQUAL_TO_FORCED_TWO_PASS
```

The targeted stress run reached line 47 with:

```text
elapsed=00:10:39
RSS=0.362 GiB
peak RSS=0.659 GiB
```

Relative to Opt18 at line 47, observed wall time fell by about 52.8%. Opt18 ran
with profiling while Opt19 did not, so this closes an engineering runtime gate
rather than constituting a rigorously isolated speedup measurement.

Opt19 conclusion: `local exactness PASS / RAM gate PASS / runtime gate PASS`.
The pre-VM engineering state was `READY`. Round1 was subsequently terminated
normally after diagnostic convergence without selecting a formal worker
winner. Its evidence is valid for engineering diagnosis: workers 4 and 8 are
below the retained search range, while document index 50 repeatedly blocked
canonical reduction for higher-worker configurations. The current next action
is an independent pre-full unit-granularity audit.

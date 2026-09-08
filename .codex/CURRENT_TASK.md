# CURRENT_TASK.md

## Current status

S1M1 is scientifically and archivally frozen. Its freeze commit is on
`exp/s1m1-core-methods` and has been fast-forwarded into `main`.

```text
formal four-cell/two-N/A analysis: VALID
association microanalysis: VALID / SHA256 VERIFIED
direct association-level evidence: YES (weighting-qualified)
selective archival: COMPLETE
deletion gate: READY (classification only; no deletion authorized or done)
S1M1: FROZEN
M0-prime implementation/config/cheap validation: COMPLETE
M0-prime formal generation/validation: VALID
S1M2 P1c: NOT STARTED
```

Do not rerun any S1M1 learner, formal aggregation, 91 GB source inventory,
raw SQLite identity hash, compact export, or association scan. Do not delete
any artifact. `notes/**` may be read/searched when useful but must never be
modified, moved, copied, deleted, tracked, staged, committed, restored,
checked out, or force-added.

## Next task

The generic cloud experiment contract and configurable Git deployment
transport are complete on `main`. Merge the published `main` into
`exp/s1m2-reusable-pieces`, retain S1M2 scientific semantics and bundle
deployment, and replace the obsolete single-VM Round 1/Round 2 control plane
with the researcher-decided six-host parallel mapping. Do not run any VM,
representative, stress, Round 1, Round 2, Final, or full-M0 workload.

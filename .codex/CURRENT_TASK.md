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

Commit and push the tracked M0-prime formal checkpoint on `main`. Then build a
clean S1M2 branch from updated `main` and preserve the existing P0 and P1a/P1b
work by cherry-picking commits `f95bc5f` and `3d4c512`. Do not check out or
carry forward the old branch's historically tracked `notes/reviewer/*` files;
the two S1M2 commits themselves do not touch `notes/**`.

Resolve durable state and `pyproject.toml` against current `main`, run the
focused P0/P1a/P1b and M0-prime interface tests, audit the untyped exact-
concatenation/no-morphology contract, and push the synchronized branch. Do not
implement P1c and do not launch an S1M2 full-corpus experiment.

The exact stop condition remains:

```text
S1M2 P1c READY TO START
```

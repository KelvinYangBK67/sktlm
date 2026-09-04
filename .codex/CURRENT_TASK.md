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
M0-prime formal generation/validation: NOT LAUNCHED
S1M2 P1c: NOT STARTED
```

Do not rerun any S1M1 learner, formal aggregation, 91 GB source inventory,
raw SQLite identity hash, compact export, or association scan. Do not delete
any artifact. `notes/**` may be read/searched when useful but must never be
modified, moved, copied, deleted, tracked, staged, committed, restored,
checked out, or force-added.

## Next task

Commit and push the prepared generic/public-facing and M0-prime changes on
`main`. From that clean committed worktree, launch exactly one genuinely
detached Windows job that runs these exact commands sequentially:

```powershell
python -m sktlm.representations.m0_prime generate --config configs/representations/m0_prime_iast_continuous.json
python -m sktlm.representations.m0_prime validate --config configs/representations/m0_prime_iast_continuous.json
```

The second command may run only if generation succeeds. Record the task name,
command, log, expected output paths, and terminal result under ignored
`artifacts/m0_prime/`; immediately after scheduling it, return without polling.
On a later invocation, inspect the completion evidence once. If successful,
validate and freeze formal hashes/provenance, then synchronize S1M2 P0/P1a/P1b
onto the updated common state without implementing P1c.

The exact stop condition remains:

```text
S1M2 P1c READY TO START
```

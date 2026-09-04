# CURRENT_TASK.md

## Current status

S1M1 is scientifically and archivally frozen on `exp/s1m1-core-methods`.

```text
formal four-cell/two-N/A analysis: VALID
association microanalysis: VALID / SHA256 VERIFIED
direct association-level evidence: YES (weighting-qualified)
selective archival: COMPLETE
deletion gate: READY (classification only; no deletion authorized or done)
S1M1: FROZEN
M0-prime: NEXT
S1M2 P1c: NOT STARTED
```

Do not rerun any S1M1 learner, formal aggregation, 91 GB source inventory,
raw SQLite identity hash, compact export, or association scan. Do not delete
any artifact. `notes/**` may be read/searched when useful but must never be
modified, moved, copied, deleted, tracked, staged, committed, restored,
checked out, or force-added.

## Next task

Integrate the generic/public-facing repository updates and the derived
M0-prime IAST-continuous generator/validator on `main`. M0-prime must use
frozen M0 Devanagari `continuous` as source, preserve document/segment/split
identity, and distinguish both lexical diphthongs from hiatus and aspirated
consonants from plain consonant+`h` sequences. Frozen M0 itself remains
untouched.

After implementation/configuration and cheap validation are committed in a
clean worktree, launch the exact formal M0-prime generation followed by
validation exactly once as a genuinely detached Windows job. Record durable
launch/log/result state and do not poll after launch. On a later invocation,
inspect completion evidence once, validate the formal outputs, freeze their
provenance/hashes, then synchronize S1M2 P0/P1a/P1b onto the updated common
state without implementing P1c.

The exact stop condition remains:

```text
S1M2 P1c READY TO START
```

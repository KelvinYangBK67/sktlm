# CURRENT_TASK.md

## Current status

Branch: `exp/s1m2-reusable-pieces`.

```text
S1M1: FROZEN
direct association-level evidence: YES (weighting-qualified)
selective archival/deletion gate: COMPLETE / READY (no deletion performed)
M0-prime formal substrate: COMPLETE / VALID
S1M2 P0 reference oracle: COMPLETE
S1M2 P1a production scoring: COMPLETE
S1M2 P1b lazy candidates: COMPLETE
S1M2 P1c: READY TO START
```

The branch is synchronized onto updated `main`, contains no tracked
`notes/**`, inherits the validated corrected six-cell M0/M0-prime substrate,
and passes the focused integration and full repository suites. No P1c code or
full-corpus S1M2 run has started.

Do not rerun S1M1 heavy work or M0-prime generation/validation. Do not delete
artifacts. `notes/**` may be read/searched when useful but must never be
modified, moved, copied, deleted, tracked, staged, committed, restored,
checked out, or force-added.

## Next task: P1c only

Implement exact shared/composed piece inference over the existing lazy spans.
Keep P0 unchanged as the numerical oracle. Do not build an independent P0
piece lattice for every lexical form and do not introduce a beam or early hard
decoding.

Required tiny equivalence gates:

1. per-form prior normalizer, log score, and expected piece counts versus P0;
2. lazy versus materialized outer partition and lexical expected counts;
3. composed expected piece counts;
4. identity/latent mass, expected lexical tokens, boundary posteriors, rule
   usage, and total posterior mass;
5. deterministic traversal/state/transition and scoring/cache/store counters,
   with explicitly bounded pass-local cache state.

Reusable pieces remain untyped and must concatenate exactly to the
grammar-licensed lexical form. Do not add morphology/gold resources, a learned
internal rewrite, a Sanskrit-specific suffix inventory, or a reward for using
sandhi. Full trainer integration and corpus execution remain later work.

```text
S1M2 P1c READY TO START
```

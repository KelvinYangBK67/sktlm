# CURRENT_TASK.md

## Current status

Branch: `exp/s1m2-reusable-pieces`.

```text
S1M1: FROZEN
researcher-authorized S1M1 regenerable-file cleanup: COMPLETE (12/12 absent)
M0-prime formal substrate: COMPLETE / VALID
S1M2 P0 reference oracle: COMPLETE
S1M2 P1a production scoring: COMPLETE
S1M2 P1b lazy candidates: COMPLETE
S1M2 P1c exact composed inference: COMPLETE
P1c/P0 and lazy/materialized equivalence gates: PASS
S1M2 streaming trainer integration: COMPLETE
resume and serial/parallel scientific equivalence: PASS
continuous profiling/benchmark freeze: READY TO START
continuous benchmark selection rule: FROZEN
continuous static corpus scan: COMPLETE / VALIDATED
continuous representative/stress workloads: FROZEN
continuous detailed profiling telemetry: IMPLEMENTED / VALIDATED
paired fixed cheap profile: COMPLETE
probe script-neutral workload identity: PASS
```

P1c uses direct exact position DP under P0 legal support and P1a fixed-pass
scores, composed with P1b lazy spans. The streaming trainer now makes the piece
state authoritative, updates it transactionally between passes, retains
lexical counts as diagnostics, and exports the required exact scientific and
bounded inspection artifacts. Document-interruption resume and one/two-worker
scientific outputs are byte-identical. The focused pieces/latent suite passes
(`76 passed`) and the trainer full-repository gate passes (`633 passed, 2
warnings`). No production-shaped S1M2 benchmark or full-corpus S1M2 run has
started.

The historical deletion-readiness manifest remains provenance for the 12
files classified `SAFE_TO_DELETE_REGENERABLE`. A read-only path check now finds
all 12 absent after the separately researcher-authorized manual cleanup. Do
not recreate them, rerun their hashes, or delete anything else.

Do not rerun frozen S1M1 work or M0-prime generation/validation. `notes/**`
remains strictly local/read-only and must never be modified, created, moved,
copied, deleted, tracked, staged, restored, checked out, or force-added.

## Next task: measure the frozen continuous workloads

Implement and equivalence-test the measured first optimization: retain the
already-validated `PhonologicalForm` in each transient lazy span instead of
reconstructing it on every access. Re-run the same fixed paired probe only
after a clean committed optimization checkpoint. Accept it only if scientific
outputs remain equivalent and the measured object churn/time improves. Use
only the frozen representative/stress lists for later timing, and detach either
full workload if plausibly longer than five minutes. Do not rerun the static
scan or launch full-M0.

```text
S1M2_CONTINUOUS_CHEAP_PROFILE=COMPLETE
CONTINUOUS_SCRIPT_NEUTRAL_PROBE=PASS
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
```

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
S1M2 streaming trainer integration: READY TO START
```

P1c uses direct exact position DP under P0 legal support and P1a fixed-pass
scores, composed with P1b lazy spans. It creates neither per-form P0 lattice
objects nor persistent lexical-edge rows. Its form and piece-score caches have
explicit entry and estimated-byte bounds. The focused pieces/latent suite
passes (`70 passed`) and the P1c full-repository gate passes (`627 passed, 2
warnings`). No full-corpus S1M2 run has started.

The historical deletion-readiness manifest remains provenance for the 12
files classified `SAFE_TO_DELETE_REGENERABLE`. A read-only path check now finds
all 12 absent after the separately researcher-authorized manual cleanup. Do
not recreate them, rerun their hashes, or delete anything else.

Do not rerun frozen S1M1 work or M0-prime generation/validation. `notes/**`
remains strictly local/read-only and must never be modified, created, moved,
copied, deleted, tracked, staged, restored, checked out, or force-added.

## Next task: streaming trainer integration

Integrate the P1c engine into the existing full-corpus-capable streaming
trainer. Preserve streaming documents, bounded memory, deterministic canonical
reduction, SQLite durability, checkpoint/resume, and crash-safe document
transactions. Piece parameters must be authoritative for scoring; lexical
counts remain diagnostics.

Implement fixed active piece state within each pass, expected piece and
occurrence-support accumulation, between-pass activation, durable piece state,
resume identity validation, required S1M2 artifacts, and tiny uninterrupted
versus resumed equivalence. Run only cheap bounded work inline; detach any
workload plausibly exceeding five minutes. Do not launch full-M0.

```text
S1M2_TRAINER_INTEGRATION=READY_TO_START
```

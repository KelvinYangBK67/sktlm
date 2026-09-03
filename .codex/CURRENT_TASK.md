# CURRENT_TASK.md

## Current status

Branch: `exp/s1m1-core-methods`.

S1M1 scientific analysis is complete. Formal aggregation
`s1m1-final-four-cell-20260903` is valid with four `AVAILABLE` cells and two
typed N/A cells. Source inventory `s1m1-final-source-inventory-20260903` is
valid for all twelve large scientific sources.

```text
scientific analysis: COMPLETE
archival compact state: PENDING
deletion gate: NOT_READY
freeze: PENDING
M0-prime: NOT_STARTED
S1M2 P1c: BLOCKED
```

The final analysis is
`reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md`.

## Remaining blocker

The four completed-cell source-VM `learner.sqlite` databases were not included
in local scientific collections. Other local smoke/medium databases are not
substitutes. The only remaining archival work is to produce and return the
four compact exports with SQLite/WAL source size and SHA-256, exact final
scorer/reuse state, compact hashes, and passing read-back consistency.

When the researcher explicitly authorizes source-host access, follow the four
existing `export_s1m1_compact.py` commands in
`docs/workflows/s1m1_final_human_run.md`. Do not rerun source inventory or
formal aggregation. After the compact directories are returned, the next
small Codex task is limited to validating them and reconsidering deletion
readiness/freeze; deletion and tagging still require separate authority.

Do not access `notes/**`. Do not delete scientific sources. Do not start
M0-prime or S1M2 P1c while this archival blocker remains.

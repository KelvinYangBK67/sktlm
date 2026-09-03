# CURRENT_TASK.md

## Current status

Branch: `exp/s1m1-core-methods`.

S1M1 formal scientific analysis remains complete and unchanged. SQLite-derived
association state is supplementary microscopic evidence, not a prerequisite
for the valid four-AVAILABLE/two-N/A representation analysis.

```text
selective SQLite archival interface: IMPLEMENTED
pre-execution audit safeguards: IMPLEMENTED
external real-data execution: PENDING
deletion gate: NOT_READY
freeze: PENDING
M0-prime: NOT_STARTED
S1M2 P1c: BLOCKED
```

Retention policy:

- Devanagari `surface_word`: raw SQLite/WAL if present plus compact state;
- Devanagari `legacy_joined`: compact state only;
- completed IAST cells: no SQLite microstate archival requirement;
- continuous partial databases: excluded from completed-state retention.

## NEXT OPERATOR STEP

1. The researcher starts only the two required current source VMs, stops and
   confirms termination of each source learner, and verifies that its DB/WAL
   are quiescent.
2. Without switching/pulling/resetting the scientific source checkout, the
   researcher fetches and checks out the exact reported archival-export commit
   in a separate detached worktree, then runs the corresponding SQLite-only
   export commands in `docs/workflows/s1m1_sqlite_retention.md`.
3. The researcher pulls:
   - Devanagari `surface_word`: raw `learner.sqlite`, non-empty
     `learner.sqlite-wal` if present, and the complete compact state;
   - Devanagari `legacy_joined`: the complete compact state only.
4. The researcher runs the documented local checksum/manifest checks, including
   Devanagari `surface_word` source size/SHA-256 and exporter-commit identity.
5. The researcher returns control to Codex with those paths.

Do not rerun formal aggregation or the 91 GB source inventory. Do not use an
unverified historical host address. Do not access `notes/**`.

## Next Codex task after return

- validate the returned identities, compact hashes, and read-back checks;
- perform SQLite-derived association analysis if supported by the returned
  compact state;
- update the final M1 report and deletion-readiness classifications;
- use only `PENDING`, `RETAIN`, `SAFE_TO_DELETE_REGENERABLE`, or `NOT_SAFE` for
  artifact classifications; reserve `NOT_READY` for the deletion gate;
- never execute deletion;
- after researcher-authorized manual deletion, perform the final M1 audit and
  only then decide whether S1M1 is `READY_TO_FREEZE`.

M0 must remain unchanged. Do not generate M0-prime or start S1M2 P1c during
this archival checkpoint.

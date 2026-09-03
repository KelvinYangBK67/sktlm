# CURRENT_TASK.md

## Current status

Branch: `chore/shared-analysis-protocol`.

S1M1 is `FINAL_ANALYSIS_PENDING_HUMAN_ARCHIVAL_GATE`, not frozen. Its final
cell framing is four complete scientific cells plus two typed N/A cells:

- `AVAILABLE`: IAST/Devanagari × `surface_word`/`legacy_joined`;
- `NA_SCIENTIFICALLY_EXCLUDED`: IAST `continuous` (non-injective hiatus vs
  lexical-diphthong spelling; manually terminated; partial state excluded);
- `NA_EXECUTION_INCOMPLETE`: Devanagari `continuous` (valid representation,
  computational/finalization failure; manually terminated; partial state
  excluded).

The formal manifest is `configs/analysis/s1m1_final_v2.json`. The checkpoint
and machine gate are
`reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md` and
`s1m1_deletion_readiness_20260903.json`.

## Work completed in this checkpoint

The generic validator gained an explicit compatibility mode for the accepted
historical IAST anchor whose config predates script/condition fields; default
and v1 validation remain strict. Its acceptance envelope preserves the
historical obsolete-audit failure and independently accepted replica hashes.

The read-only compact exporter can stream exact final scorer state, inspection
lexicon state, surface/context usage, segment metrics, boundaries, passes,
rules, runtime, document/length/reuse tables, output hashes, and read-back
consistency into an atomic non-overwritten directory. It opens SQLite with
`mode=ro` and `query_only`.

No real compact export or formal v2 aggregation ran. Twelve local large
scientific files total 91,193,439,274 bytes, so both aggregation and local
rehashing exceed the five-minute Codex limit. Their historical audit/replica
hashes are recorded; local revalidation is pending. The four completed-cell
SQLite databases are not locally collected, so training-final scorer and
exact reuse exports are also pending.

Deletion gate: `NOT_READY`. `SAFE_TO_DELETE_REGENERABLE` is empty. Both
continuous termination evidence sets are `RETAIN`; all large completed-cell
sources and source-host SQLite states remain `NOT_READY`/retention-required.

## Human-only next commands

Follow `docs/workflows/s1m1_final_human_run.md` exactly:

1. `bash scripts/analysis/HUMAN_RUN_S1M1_FINAL_SHA256.sh`
2. run `aggregate_representations.py` with
   `configs/analysis/s1m1_final_v2.json`;
3. run the four explicit `export_s1m1_compact.py` commands on the source hosts;
4. return the completed hash, aggregation, and four compact directories.

The next Codex task is then limited to validating those returned outputs,
finalizing report/gate state, and deciding `READY_TO_FREEZE`. Do not delete
anything automatically and do not tag or merge without explicit authority.

M0 is unchanged. M0-prime was not generated. S1M2 P1c was not started. No
VM/cloud operation or long process was run in this checkpoint.

Validation: focused tests `18 passed`; full repository suite `551 passed` with
four existing warnings; Python compilation, Bash syntax, and diff checks pass.

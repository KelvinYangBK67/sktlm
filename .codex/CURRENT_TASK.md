# CURRENT_TASK.md

## Current status

Branch: `exp/s1m1-core-methods`.

S1M1 formal scientific analysis remains complete and unchanged. SQLite-derived
association state is supplementary microscopic evidence.

```text
selective SQLite compact states: RETURNED / METADATA-PREFLIGHT-VALID
association microanalysis implementation: IMPLEMENTED
full association microanalysis: PENDING EXTERNAL RESEARCHER RUN
direct association-level scientific claim: NOT YET ASSESSED
deletion gate: NOT_READY
freeze: PENDING
M0-prime: NOT_STARTED
S1M2 P1c: BLOCKED
```

The generic streaming mechanism, S1M1 manifest, focused tests, and workflow are
complete. The full 45M-form/association scan was deliberately not launched.

## NEXT OPERATOR STEP

From the repository root, the researcher runs exactly:

```bash
PYTHONPATH="$PWD/src" python3 scripts/analysis/analyze_association_specialization.py \
  --manifest configs/analysis/s1m1_association_microanalysis.json \
  --output-dir artifacts/s1m1_final/association_microanalysis
```

The output directory must not already exist. Expected outputs are
`per_form_metrics.tsv.gz`, `comparison.tsv.gz`, `cell_summary.json`,
`comparison_summary.tsv`, `comparison_strata.tsv`, `length_bins.tsv`,
`count_bins.tsv`, `joint_bins.tsv`, `relationship_summary.tsv`,
`diagnostic_examples.tsv`, `manifest.json`, and `SHA256SUMS`.

Do not run this command as a smoke test. Do not rerun formal aggregation, the
91 GB source inventory, a learner, or raw SQLite hashing. Do not access
`notes/**`.

## Next Codex task after return

- validate output checksums, provenance, row counts, and summaries;
- decide whether the association evidence supports upgrading the conservative
  aggregate-level mechanism statement;
- only then update the final M1 report and deletion-readiness classifications;
- use only `PENDING`, `RETAIN`, `SAFE_TO_DELETE_REGENERABLE`, or `NOT_SAFE`
  for artifact classifications; reserve `NOT_READY` for the deletion gate;
- never execute deletion.

M0 remains unchanged. Do not generate M0-prime or start S1M2 P1c during this
checkpoint.

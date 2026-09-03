# CURRENT_TASK.md

## Current status

Branch: `chore/shared-analysis-protocol`.

Generic representation-analysis protocol v2 and generic read-only archival
inventory/deletion-readiness tooling are implemented. The v2 protocol accepts
a declared cell universe with zero or more supplied scientific cells. Missing,
scientifically excluded, incomplete, and non-applicable cells produce explicit
JSON `null` / TSV-Markdown `N/A`; only `AVAILABLE` cells enter scientific
aggregation. Supplied corrupt, incomplete, mismatched, duplicate, or
unapproved inputs fail closed. Pair directions are manifest-declared and are
computed only for two available endpoints.

The historical strict six-cell v1 implementation and command remain intact;
its CLI also dispatches v2 manifests. The public schemas and commands are in
`docs/workflows/representation_analysis_v2.md`.

The archival helper inventories only explicitly named paths with streaming
SHA-256, deterministic ordering, non-overwriting atomic JSON/TSV publication,
and a READY/NOT_READY evidence gate. It implements no destructive operation.

## Validation and boundaries

Focused analysis tests pass (`15 passed`). No formal S1M1 artifact was scanned,
no formal large-file SHA-256 was computed, no artifact was deleted, no final
S1M1 report was generated, no M0-prime work was started, and S1M2 P1c was not
started. No VM/cloud operation occurred.

## Next task

After a human prepares an explicit formal manifest, run only the generic entry
point into a new directory:

    python scripts/analysis/aggregate_representations.py --manifest <manifest.json> --output-dir <new-output-dir>

Formal S1M1 analysis and any large-artifact inventory remain separate,
explicitly authorized follow-up work. Do not infer missing cell status from
directory names and do not start deletion from this tooling.

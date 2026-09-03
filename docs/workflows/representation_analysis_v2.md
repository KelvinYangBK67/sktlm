# Generic representation-analysis protocol v2

This protocol aggregates a declared universe of representation cells without
requiring every cell to be supplied. It is local-only. Absence is represented
explicitly; corruption in any supplied scientific cell fails validation.

## Representation manifest

Use schema `sktlm-representation-analysis-input/v2`:

```json
{
  "schema_version": "sktlm-representation-analysis-input/v2",
  "analysis_id": "example-analysis",
  "approved_scientific_commits": ["0123456789abcdef0123456789abcdef01234567"],
  "cell_universe": [
    {
      "cell_id": "iast_word",
      "script": "iast",
      "representation": "surface_word",
      "status": "AVAILABLE"
    },
    {
      "cell_id": "dev_continuous",
      "script": "devanagari",
      "representation": "continuous",
      "status": "NA_EXECUTION_INCOMPLETE",
      "reason": "bounded execution did not complete",
      "provenance_evidence": {"expected_commit": "0123456789abcdef0123456789abcdef01234567"},
      "runtime_evidence": {"wall_seconds": 123.0},
      "termination_evidence": {"kind": "timeout"}
    }
  ],
  "supplied_cells": [
    {
      "cell_id": "iast_word",
      "run_id": "run-id",
      "metrics_id": "metrics-id",
      "scientific_commit": "0123456789abcdef0123456789abcdef01234567",
      "run_dir": "relative/run",
      "metrics_dir": "relative/metrics",
      "audit_path": "relative/audit.json"
    }
  ],
  "pairwise_comparisons": [
    {"pair_id": "declared-direction", "kind": "script", "cell_a": "iast_word", "cell_b": "dev_word"}
  ],
  "top_k_values": [100, 1000, 10000]
}
```

Supported statuses are `AVAILABLE`, `NA_NOT_PROVIDED`,
`NA_SCIENTIFICALLY_EXCLUDED`, `NA_EXECUTION_INCOMPLETE`, and
`NA_NOT_APPLICABLE`. Every N/A declaration needs a reason. Only `AVAILABLE`
cells may occur in `supplied_cells`, and every `AVAILABLE` cell must be
supplied. The approved commit list exactly matches supplied provenance; a
multi-commit input additionally requires an approved
`cross_commit_compatibility` object with an explicit basis and evidence list.

Supplied cells reuse the strict completed-run checks from the historical gate:
run/config/audit identity, unrestricted/full scope, common scientific config,
completion, process success, required artifacts, and bytes/SHA identity. An
N/A cell is never loaded as a scientific result. Its optional runtime and
termination metadata is retained separately.

JSON uses `null` for unavailable values. TSV and Markdown use `N/A`.
Scientific cell output retains lexical structure/count/mass/ambiguity,
complexity, candidate graph, overflow, external-rule, and
90/95/99/99.9/99.99% mass-support metrics. Runtime/resource metrics remain a
separate group. A declared pair is computed only when both endpoints are
`AVAILABLE`; otherwise every comparison has `comparison_status: "N/A"` and a
reason. Available pairs include signed/absolute differences, ratios, rule TV,
rule Jensen-Shannon divergence in nats, and declared top-k overlap.

Run locally into a new output directory:

```bash
python scripts/analysis/aggregate_representations.py \
  --manifest <representation-manifest.json> \
  --output-dir <new-output-directory>
```

The historical `aggregate_six_representation.py` entry point still runs its
strict v1 behavior and dispatches v2 manifests to this generic engine.

## Artifact inventory and deletion-readiness gate

Use schema `sktlm-artifact-inventory-input/v1`. `base_dir` constrains all
relative paths. `retained_evidence` has separate `provenance`, `config`, and
`runtime_termination` path lists. Each artifact declares:

```json
{
  "path": "derived/large.tsv",
  "expected_sha256": "optional-known-sha256",
  "artifact_role": "derived-detail",
  "regenerability": "REGENERABLE",
  "replacement_compact_artifact": "compact/summary.tsv",
  "retention_required": false,
  "runtime_evidence_required": true,
  "consistency_checks": [
    {"kind": "row_count"},
    {"kind": "numeric_sum", "source_column": "mass", "absolute_tolerance": 1e-9}
  ]
}
```

Consistency checks support `row_count`, `numeric_sum`, and `json_fields`.
Inventory hashing is streaming and deterministic. Output records source and
replacement sizes/hashes and assigns `PENDING`, `RETAIN`,
`SAFE_TO_DELETE_REGENERABLE`, or `NOT_SAFE`; the overall gate is `READY` or
`NOT_READY`. A regenerable artifact is safe only with a compact replacement,
at least one passing declared consistency check, retained provenance and
config, and retained runtime/termination evidence when required. Publication
uses a temporary directory and atomic rename and refuses overwrite.

```bash
python scripts/analysis/inventory_artifacts.py \
  --manifest <inventory-manifest.json> \
  --output-dir <new-inventory-directory>
```

The inventory tool has no delete/unlink operation. A human makes every actual
retention or deletion decision.

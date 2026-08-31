# Full-M0 replica launch plan

Status: **PREPARED, NOT AUTHORIZED, NOT STARTED**.

This plan prepares four independent full-corpus replicas of the frozen
IAST `surface_word` latent-lexicon condition. It does not authorize any
process launch, SSH operation, input transfer, audit, or result collection.

## Durable assignments

| Machine | Replica | Run ID | Metrics ID | Workers | State |
|---|---|---|---|---:|---|
| `core-01` | `rep01` | `cloud_full_m0_iast_surface_word_p10_rep01_w8_p3` | `full_m0_iast_surface_word_p10_rep01_w8_p3` | 8 | PREPARED |
| `core-02` | `rep02` | `cloud_full_m0_iast_surface_word_p10_rep02_w8_p3` | `full_m0_iast_surface_word_p10_rep02_w8_p3` | 8 | PREPARED |
| `core-03` | `rep03` | `cloud_full_m0_iast_surface_word_p10_rep03_w8_p3` | `full_m0_iast_surface_word_p10_rep03_w8_p3` | 8 | PREPARED |
| `core-04` | `rep04` | `cloud_full_m0_iast_surface_word_p10_rep04_w8_p3` | `full_m0_iast_surface_word_p10_rep04_w8_p3` | 8 | PREPARED |

`core-05` and `core-06` remain unassigned READY/STANDBY capacity.

The scientific implementation checkpoint is
`fbd0a499701d6a13dcbf8374d5b5ce3a357a7b04`. At execution time each
machine must run the exact published branch HEAD selected by the human
operator; the normal provenance writer will record that actual Git commit.

## Supported full-corpus entry point

`sktlm.latent.benchmark` supports only `smoke` and `medium`; there is no
`--benchmark full` mode. The full run therefore uses the existing
`sktlm.experiments.training.latent_lexicon` entry point. Omitting
`--document-list`, `--max-documents`, and `--max-lines-per-document`
selects all 240 frozen IAST `surface_word` rows from
`data/manifests/representations.csv`.

On each assigned machine, set the two values from the table above and run this
template exactly once:

```bash
SKTLM_RUN_ID='cloud_full_m0_iast_surface_word_p10_rep01_w8_p3'
SKTLM_METRICS_ID='full_m0_iast_surface_word_p10_rep01_w8_p3'

./.venv/bin/python scripts/cloud/run_with_metrics.py \
  --output-dir "artifacts/cloud_metrics/${SKTLM_METRICS_ID}" \
  -- \
  ./.venv/bin/python -m sktlm.experiments.training.latent_lexicon \
  --manifest data/manifests/representations.csv \
  --output-root artifacts/latent_benchmarks \
  --run-id "${SKTLM_RUN_ID}" \
  --passes 3 \
  --workers 8 \
  --equivalence-diagnostics
```

For `core-02` through `core-04`, replace both assignments with the exact
rep02/rep03/rep04 values in the table. Do not batch the four machines into one
local shell command.

The wrapper and trainer both refuse silent overwrite. If a process is
interrupted, preserve its run and metrics directories; a resume attempt needs
an explicitly prepared new metrics-attempt ID and the trainer's `--resume`
flag rather than reusing this initial launch command.

## Lightweight monitor

While the foreground job is running on its assigned host:

```bash
tail -n 1 "artifacts/cloud_metrics/${SKTLM_METRICS_ID}/process_tree_samples.csv"
```

This reads the latest one-second process-tree sample and does not alter the
run.

## Final audit

The direct full-corpus trainer writes `timing_metrics.json` but not the
`benchmark_metrics.json` required by the existing
`audit_latent_run.py`. Because this task is documentation/configuration only,
the implementation is unchanged. After natural completion, create the small
non-scientific audit envelope from existing run/resource metadata:

```bash
SKTLM_RUN_DIR="artifacts/latent_benchmarks/${SKTLM_RUN_ID}"
SKTLM_METRICS_DIR="artifacts/cloud_metrics/${SKTLM_METRICS_ID}"

./.venv/bin/python - "${SKTLM_RUN_DIR}" "${SKTLM_METRICS_DIR}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
metrics_dir = Path(sys.argv[2])
config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
timing = json.loads((run_dir / "timing_metrics.json").read_text(encoding="utf-8"))
summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
resources = json.loads(
    (metrics_dir / "process_tree_summary.json").read_text(encoding="utf-8")
)

training_characters = sum(
    int(row["characters"]) for row in checkpoint["history"]
)
training_segments = sum(int(row["segments"]) for row in checkpoint["history"])
inspection_characters = int(summary["characters"])
inspection_segments = int(summary["segments"])
character_visits = training_characters + inspection_characters
segment_visits = training_segments + inspection_segments
wall_seconds = float(resources["wall_seconds"])

payload = {
    "schema_version": 1,
    "benchmark": "full_m0_direct",
    "document_list": None,
    "passes": int(config["passes"]),
    "workers": int(config["workers"]),
    "wall_seconds": wall_seconds,
    "cpu_seconds": float(resources["sampled_process_tree_cpu_seconds"]),
    "training_characters": training_characters,
    "inspection_characters": inspection_characters,
    "character_visits": character_visits,
    "training_segments": training_segments,
    "inspection_segments": inspection_segments,
    "segment_visits": segment_visits,
    "chars_per_second": character_visits / max(wall_seconds, 1e-12),
    "segments_per_second": segment_visits / max(wall_seconds, 1e-12),
    "peak_rss_bytes": None,
    "process_tree_peak_rss_bytes": int(
        resources["peak_process_tree_rss_bytes"]
    ),
    "runtime": timing,
}
with (run_dir / "benchmark_metrics.json").open(
    "x", encoding="utf-8", newline=""
) as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write("\n")
PY
```

The exclusive `"x"` write refuses to replace any existing metrics file. It
does not inspect or hash a scientific artifact. Then run the existing bounded
final audit:

```bash
./.venv/bin/python scripts/cloud/audit_latent_run.py \
  "${SKTLM_RUN_DIR}" \
  --output "${SKTLM_METRICS_DIR}/audit.json"
```

The audit itself performs the completion, SQLite, residue, provenance, and
canonical scientific-artifact hash checks. It is expected to be a long
post-run operation and remains human-operated.

## Mainland Git transport fallback

Direct GitHub access can be unreliable from mainland cloud hosts. The
preferred fallback is to create a Git bundle locally, transfer that bundle over
SSH, and fast-forward the remote checkout from the bundle with exact-HEAD
verification; do not copy a working tree or weaken the fast-forward rule.

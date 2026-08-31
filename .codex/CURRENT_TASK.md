# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`

The scientific checkpoint remains frozen: GRETIL M0 freeze
`9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`,
240 canonical documents, 1,440 representations, and 1,218 external-sandhi
rules. Formal v1 remains IAST `surface_word`, exact inference, lexical alpha
0.1, complexity lambda/tau 0.5/1.0, whitespace penalty 8.0, and three passes.
Do not change candidate, grammar, scoring, EM, inference, representation, or
scientific output semantics.

## Cloud medium scaling is closed

The authoritative closure is
`reports/core_methods/latent_lexicon/cloud_scaling_checkpoint_20260831.md`;
the script-readable records are in
`configs/cloud/experiment_registry.toml`.

All four Ubuntu 22.04 medium runs are DONE and remotely audited as valid under
scientific checkpoint
`fbd0a499701d6a13dcbf8374d5b5ce3a357a7b04`. Their wall-time ranking is:

1. w8: 740.9371817360001 s
2. w16: 849.243166304 s
3. w12: 853.409434638 s
4. w4: 972.1771821109978 s

The w8 run is approximately 12.8% faster than the w16 runner-up, so the
preregistered >=10% rule selects 8 workers directly. Eight workers are now the
frozen cloud production setting for the next full-M0 stage. All six canonical
scientific artifacts are byte-for-byte and SHA-256 identical across w4, w8,
w12, and w16.

Do not poll these completed medium runs, run a tie-break, or launch another
medium scaling benchmark.

## Next scientific execution gate

Four full-M0 replicas are PREPARED at 8 workers; none has started:

| Machine | Replica | Run ID | Metrics ID |
|---|---|---|---|
| `core-01` | `rep01` | `cloud_full_m0_iast_surface_word_p10_rep01_w8_p3` | `full_m0_iast_surface_word_p10_rep01_w8_p3` |
| `core-02` | `rep02` | `cloud_full_m0_iast_surface_word_p10_rep02_w8_p3` | `full_m0_iast_surface_word_p10_rep02_w8_p3` |
| `core-03` | `rep03` | `cloud_full_m0_iast_surface_word_p10_rep03_w8_p3` | `full_m0_iast_surface_word_p10_rep03_w8_p3` |
| `core-04` | `rep04` | `cloud_full_m0_iast_surface_word_p10_rep04_w8_p3` | `full_m0_iast_surface_word_p10_rep04_w8_p3` |

`core-05` and `core-06` remain unassigned READY/STANDBY.

The benchmark harness has no full mode. On each assigned host, set the exact
run/metrics IDs from the table and use the existing full-corpus trainer:

```bash
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

Omitting document/max limits selects the complete frozen 240-document IAST
`surface_word` condition. Lightweight monitoring is:

```bash
tail -n 1 "artifacts/cloud_metrics/${SKTLM_METRICS_ID}/process_tree_samples.csv"
```

After natural completion, first run the exclusive metrics-envelope block in
`reports/core_methods/latent_lexicon/full_m0_launch_plan.md`, then audit:

```bash
./.venv/bin/python scripts/cloud/audit_latent_run.py \
  "artifacts/latent_benchmarks/${SKTLM_RUN_ID}" \
  --output "artifacts/cloud_metrics/${SKTLM_METRICS_ID}/audit.json"
```

The full plan, audit compatibility explanation, and mainland Git-bundle
fallback are in `full_m0_launch_plan.md`. Preparation does not authorize
launch; wait for an explicit user instruction.

## Multi-host bridge

`scripts/cloud/sktlm_bridge.py` preserves the legacy single `[bridge]`
configuration and supports optional ignored `[host_profiles.<id>]` overlays
selected with `--host-profile`. Receipts/status record logical profile and
machine ID. Multi-profile result operations check the selected profile,
machine, run ID, and metrics ID against the tracked registry before SSH.

Real IPs/hosts and identity paths remain only in ignored
`.sktlm-bridge.toml`. Never commit that file. The bridge is a deterministic
code/input/result transport and audit control plane; it does not launch
benchmarks.

## Local-only research state

The bounded inventory is
`reports/core_methods/latent_lexicon/research_output_inventory_20260831.md`.
The minimum tracked formal-run evidence and established hash manifest are in
`reports/core_methods/latent_lexicon/evidence/`.
Raw P10/cloud outputs, generated cleaning audits, old notes, interrupted
diagnostics, operational receipts, and private bridge configuration remain
ignored/local. Do not delete or bulk-add them.

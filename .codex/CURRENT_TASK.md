# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`

The scientific checkpoint remains frozen: GRETIL M₀ freeze
`9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`,
240 canonical documents, 1,440 representations, and 1,218 external-sandhi
rules. Formal v1 remains IAST `surface_word`, exact inference, lexical alpha
0.1, complexity lambda/tau 0.5/1.0, whitespace penalty 8.0, and three passes.
Do not change candidate, grammar, scoring, EM, inference, representation, or
scientific output semantics.

## Cloud scaling checkpoint

The authoritative status is
`reports/core_methods/latent_lexicon/cloud_scaling_checkpoint_20260831.md` and
the script-readable assignment is `configs/cloud/experiment_registry.toml`.

- `core-01`: cloud medium P10 w4 DONE and remotely audited;
  `cloud_medium_p10_w4_p3`, wall 972.1771821109978 s, throughput
  17409.851117105878 chars/s.
- `core-02`: cloud medium P10 w8 RUNNING.
- `core-03`: cloud medium P10 w12 RUNNING.
- `core-04`: cloud medium P10 w16 RUNNING.
- `core-05`, `core-06`: standby.

Do not poll these machines, collect pending runs merely to inspect them, rerun
w4, start a tie-break, or start full M₀. When the human provides completed
outputs, update the registry/report from those artifacts and apply the recorded
worker-selection rule.

## Multi-host bridge

`scripts/cloud/sktlm_bridge.py` preserves the old single `[bridge]` config and
adds optional ignored `[host_profiles.<id>]` overlays selected after a command
with `--host-profile`. Receipts/status record logical profile and machine ID.
For multi-profile collection, the bridge checks the selected profile, machine,
run ID, and metrics ID against the tracked registry before SSH.

Real IPs/hosts and identity paths remain only in ignored
`.sktlm-bridge.toml`. The current local config still contains only the legacy
single `[bridge]` table; the human must add `core-01` through `core-04` profiles
before profiled collection. Do not commit that file.

Future collection forms, only after the corresponding run is confirmed done:

```bash
python3 scripts/cloud/sktlm_bridge.py collect cloud_medium_p10_w8_p3 \
  --metrics-id medium_p10_w8_p3 --host-profile core-02
python3 scripts/cloud/sktlm_bridge.py collect cloud_medium_p10_w12_p3 \
  --metrics-id medium_p10_w12_p3 --host-profile core-03
python3 scripts/cloud/sktlm_bridge.py collect cloud_medium_p10_w16_p3 \
  --metrics-id medium_p10_w16_p3 --host-profile core-04
```

## Local-only research state

The bounded inventory is
`reports/core_methods/latent_lexicon/research_output_inventory_20260831.md`.
Cloud w4 performance, aggregate RSS, audit status, and scientific hashes were
promoted into the tracked cloud checkpoint. Local P10 artifacts, generated
cleaning audits, old notes, interrupted diagnostics, and operational receipts
remain ignored/local. Do not delete or bulk-add them.

# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`

The scientific checkpoint remains frozen: GRETIL M0 freeze
`9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`,
240 canonical documents, 1,440 representations, and 1,218 external-sandhi
rules. Formal v1 remains IAST `surface_word`, exact inference, lexical alpha
0.1, complexity lambda/tau 0.5/1.0, whitespace penalty 8.0, and three passes.
Do not change the frozen unrestricted candidate, grammar, scoring, EM,
representation, or scientific output semantics. The optional fixed-vocabulary
condition described below is separate; `vocab_budget=None` preserves the
unrestricted configuration signature and inference behavior.

## Highest priority: active unrestricted full-M0 runs are hands-off

The user reports that `core-01` through `core-04` are currently running the
four prepared unrestricted full-M0 replicas. This state was not queried from
the hosts and must be treated as authoritative.

Do not SSH to, poll, attach to, stop, restart, resume, clean, overwrite, or
modify anything on those hosts or in their run/metrics directories. Do not
change their configs, checkpoints, SQLite databases, shards, logs, or
artifacts. Do not perform cloud Git operations that could affect them.
`core-05` and `core-06` remain READY/STANDBY and must not be launched by
Codex. Cloud synchronization, launch, medium/full validation, and collection
remain manual user operations.

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

## Optional fixed-vocabulary condition

The local branch now implements `--vocab-budget K` for future capacity-matched
BPE/Unigram comparisons. It is not applied to the active unrestricted runs.

- one distinct latent `form_key` consumes one slot;
- surface realizations and sandhi rules consume no slots;
- all 50 `Phoneme` singleton base units are forced into the vocabulary;
- after neutral Pass 1, multi-phoneme identities are ranked by
  `expected_count DESC, form_key ASC`, and the first `K-50` are frozen;
- Pass 2, Pass 3, and inspection reuse the same durable SQLite vocabulary;
- an OOV multi-phoneme form scores and counts as its constituent singleton
  base tokens, and decoded sequences use the same projection;
- `vocabulary_budget.json` and `vocabulary.tsv` are the audit artifacts;
- checkpoint/provenance store and validate the frozen allowed-key SHA-256.

The single focused validation command passed 8 tests. No smoke, medium, full,
cloud, or running-job validation was performed. A minimal user-run check, if
desired on a disposable tiny/document-limited run, is:

```bash
./.venv/bin/python -m sktlm.experiments.training.latent_lexicon \
  --document-list configs/benchmarks/latent_smoke_documents.txt \
  --output-root artifacts/latent_lexicon \
  --run-id vocab_budget_manual_smoke_k16384 \
  --passes 3 --workers 1 --vocab-budget 16384
```

This command is a handoff only; Codex did not run it. Use a unique run ID and
do not point it at any active full-M0 directory.

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

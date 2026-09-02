# M0 formal aggregation and validity gate

Schema: `m0-baseline-aggregate-v1`.

`sktlm.experiments.baselines.aggregate` emits no partial formal result. It first
requires exactly one seed-0 `formal_production` bundle for every one of the 18
valid manifest cells and rejects missing, duplicate, extra, wrong-seed, bounded,
or retired artifact directories.

Each bundle must end in `COMPLETED.json`, written only after all other files.
The completion inventory covers every tokenizer model/metadata file, common LM
checkpoint, config, metrics, predictions, logs, fingerprints, Git identity,
environment JSON, and requirements freeze; any missing, added, or hash-mismatched
file fails validation.

The gate cross-checks condition identity/status, manifest version, M0 freeze ID,
both tracked manifest hashes, effective config and hash, data and tokenizer
fingerprints, clean Git commit, deterministic environment fingerprint,
requirements digest, exact artifact location, fresh-per-cell initialization,
unique training instance, common downstream completion, finite normalized
metrics, and runtime/peak-memory fields. Commit, environment, manifest hashes,
and seed must agree across all 18 cells.

The output separates orthographic diagnostics, segmentation statistics, unknown
behavior, inventory/occupancy, method-specific likelihood, common downstream LM
utility, and runtime/resources. Its comparison declaration permits script pairs
only for `surface_word` and `legacy_joined`; IAST spacing comparisons contain
only those two conditions, while Devanagari also contains `continuous`.
Tokenizer comparisons are constructed only within the same valid script/spacing
condition. No IAST/Devanagari continuous pair can be emitted.

After all production cells are present, run:

```bash
python -m sktlm.experiments.baselines.aggregate \
  --artifact-root artifacts/baselines/m0 \
  --output reports/baselines/generated/m0_aggregate.json
```

The generated aggregate is not committed unless separately approved.

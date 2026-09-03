# Human-run S1M1 final aggregation and archival sequence

These commands are intentionally not run by Codex because the inputs are tens
of gigabytes. Run them from a clean checkout of the committed
`chore/shared-analysis-protocol` checkpoint. Stop safely with `Ctrl-C`; atomic
outputs ensure an interrupted job is not presented as final. None of these
commands deletes source data.

## 1. Revalidate local large-source hashes

From the repository root in Bash/WSL/Linux:

```bash
bash scripts/analysis/HUMAN_RUN_S1M1_FINAL_SHA256.sh
```

The resumable parts are written under
`artifacts/s1m1_final/source_hashes/parts/`. The final
`SHA256SUMS.tsv` appears only after all twelve explicit files finish.

## 2. Run the formal four-cell/two-N/A aggregation

```bash
python scripts/analysis/aggregate_representations.py \
  --manifest configs/analysis/s1m1_final_v2.json \
  --output-dir artifacts/s1m1_final/aggregation
```

This validates and scans the four supplied cells. It emits available
scientific comparisons and explicit N/A rows for every continuous-dependent
pair.

## 3. Export exact compact state on each completed cell's source host

The source-host checkout must contain the same committed exporter. Each output
directory must be absent before the command. Run the corresponding command on
the host that retains that run's `learner.sqlite` and scientific outputs.

IAST `surface_word`:

```bash
python scripts/analysis/export_s1m1_compact.py \
  --cell-id iast__surface_word --script iast --representation surface_word \
  --run-dir artifacts/latent_benchmarks/cloud_full_m0_iast_surface_word_p10_rep01_w8_p3 \
  --metrics-dir artifacts/cloud_metrics/full_m0_iast_surface_word_p10_rep01_w8_p3 \
  --database artifacts/latent_benchmarks/cloud_full_m0_iast_surface_word_p10_rep01_w8_p3/learner.sqlite \
  --output-dir artifacts/s1m1_final/compact/iast__surface_word
```

IAST `legacy_joined`:

```bash
python scripts/analysis/export_s1m1_compact.py \
  --cell-id iast__legacy_joined --script iast --representation legacy_joined \
  --run-dir artifacts/latent_benchmarks/cloud_full_m0_iast_legacy_joined_p10_w8_p3 \
  --metrics-dir artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3 \
  --database artifacts/latent_benchmarks/cloud_full_m0_iast_legacy_joined_p10_w8_p3/learner.sqlite \
  --output-dir artifacts/s1m1_final/compact/iast__legacy_joined
```

Devanagari `surface_word`:

```bash
python scripts/analysis/export_s1m1_compact.py \
  --cell-id devanagari__surface_word --script devanagari --representation surface_word \
  --run-dir artifacts/latent_benchmarks/cloud_full_m0_devanagari_surface_word_p10_w8_p3 \
  --metrics-dir artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3 \
  --database artifacts/latent_benchmarks/cloud_full_m0_devanagari_surface_word_p10_w8_p3/learner.sqlite \
  --output-dir artifacts/s1m1_final/compact/devanagari__surface_word
```

Devanagari `legacy_joined`:

```bash
python scripts/analysis/export_s1m1_compact.py \
  --cell-id devanagari__legacy_joined --script devanagari --representation legacy_joined \
  --run-dir artifacts/latent_benchmarks/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3 \
  --metrics-dir artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3 \
  --database artifacts/latent_benchmarks/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3/learner.sqlite \
  --output-dir artifacts/s1m1_final/compact/devanagari__legacy_joined
```

Each successful directory contains its own `manifest.json`, read-back results,
and `SHA256SUMS`. Copy the four complete compact directories back beneath
`artifacts/s1m1_final/compact/` without deleting the source-host copies.

## 4. Return for the small finalization pass

After steps 1–3 complete, do not delete anything. Return the following paths
to the next Codex session:

```text
artifacts/s1m1_final/source_hashes/SHA256SUMS.tsv
artifacts/s1m1_final/aggregation/
artifacts/s1m1_final/compact/iast__surface_word/
artifacts/s1m1_final/compact/iast__legacy_joined/
artifacts/s1m1_final/compact/devanagari__surface_word/
artifacts/s1m1_final/compact/devanagari__legacy_joined/
```

That follow-up validates the returned outputs, finalizes the scientific report
and machine-readable deletion gate, and decides whether S1M1 is
`READY_TO_FREEZE`. Deletion remains a separate human decision.

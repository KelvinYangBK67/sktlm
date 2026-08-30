# Controlled experiments

These directories contain configs and aggregated result tables only. Library
code lives under `src/sktlm`.

Run a diagnostic/provenance pass with:

```bash
sktlm-experiment --config configs/experiments/matrices/script_control/iast_character.yaml --dry-run
```

Omit `--dry-run` for configs that include `training`; the tiny controlled
backend then reports bits per Unicode character and bits per UTF-8 byte.
Aggregate completed runs with `sktlm.evaluation.reporting.collect_metrics` and
`write_result_table`.

The five `*_continuous.yaml` configs under `tokenizer_baselines/` are the
matched, leakage-controlled tokenizer diagnostics: BPE and Unigram are fitted
from the same selected train segments used to fit the character and grapheme
vocabularies. The `*_legacy.yaml` configs instead load tracked historical 24k
models. They exist only for artifact compatibility and legacy preprocessing
regression; do not mix them into the matched controlled result table.

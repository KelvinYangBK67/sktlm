# sktlm

`sktlm` is a reproducible framework for controlled Sanskrit representation,
tokenization, and small language-model experiments. The experimental path keeps
one canonical text identity and fixed train/dev/test membership, then varies
only explicit script, spacing, tokenizer, or model configuration.

The current framework provides:

- a whitelist-only formal GRETIL canonical IAST corpus builder with provenance,
  hashes, cleaning audit, and unknown-character reporting;
- canonical physical-line segments with stable `document_id`, `segment_id`, and
  split metadata;
- independent `iast`/`devanagari` script transforms and `observed`,
  `continuous`, or compatibility-only `legacy_joined` spacing transforms;
- a common tokenizer interface for SentencePiece BPE, SentencePiece Unigram,
  Unicode characters, UTF-8 bytes, and extended grapheme clusters;
- token span, orthographic-boundary, and explicitly heuristic sandhi-fragment
  diagnostics;
- segment-safe tiny Transformer training and likelihood reported as bits per
  Unicode character (BPC) and bits per UTF-8 byte (BPB); and
- config-driven runs with data, tokenizer, Git, metric, preview, and log
  artifacts.

## Setup and validation

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Build and validate the formal GRETIL canonical corpus from the exact paths in
`notes/whitelist.txt`:

```bash
sktlm-build-gretil-canonical
sktlm-validate-gretil-canonical
```

This formal path writes `data/manifests/canonical_corpus.csv` and preserves
source-provided IAST word boundaries and accents. It does not use the legacy
pilot cleaning, spacing, transliteration, tokenizer, or model pipeline. See
`docs/canonical_corpus.md` for the construction and QC contract.

Run a provenance and tokenizer-diagnostics pass without model training:

```bash
sktlm-experiment --config experiments/script_control/iast_character.yaml --dry-run
```

Run the controlled tiny backend:

```bash
sktlm-experiment --config configs/tiny_controlled.yaml
```

Each run writes `config.yaml`, `metrics.json`, `result.csv`, data and tokenizer
fingerprints, `git_commit.txt`, `predictions.jsonl`, and `logs.txt` below its
artifact directory. Experiment matrices live under `experiments/`; reusable
condition fragments live under `configs/`.

The historical paths under `scripts/`, `tokenizer/`, `model/`, and `train/`
remain as compatibility layers. Likewise, the old tiny-training configuration
shape is still accepted by `sktlm-train-tiny`, but new experiments should use
the controlled configuration shape shown in `configs/tiny_controlled.yaml`.

See `docs/migration_round2.md` before comparing new runs with the tracked 24k
SentencePiece models. Those models encode the historical joined-text condition
and must not be presented as clean observed-spacing Devanagari baselines.

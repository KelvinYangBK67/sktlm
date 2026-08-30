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
- independent `iast`/`devanagari` script transforms and `surface_word`,
  `continuous`, or source-whitespace `lexical_boundary` datasets, while
  retaining `observed` and `legacy_joined` as compatibility conditions;
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

Build and validate the formal GRETIL extraction candidate from the exact paths in
`configs/corpus/gretil_whitelist.txt`:

```bash
sktlm-build-gretil-extraction
sktlm-validate-gretil-extraction
```

This extraction stage writes under `data/intermediate/gretil/` and produces
`data/manifests/gretil_extraction_manifest.csv`. It preserves source-provided
IAST word boundaries and accents. See
`docs/methodology/canonical_corpus.md` for the construction and QC contract.

After extraction, run document-structure cleanup, strict projection and strict
validation in that order with sktlm-clean-gretil-document-structure,
sktlm-project-gretil-strict-final and sktlm-validate-gretil-strict. The freeze
command refuses any nonzero invalid-character or invalid-apostrophe count.
Then freeze and derive the six representation datasets:

```bash
sktlm-freeze-gretil-canonical
sktlm-validate-gretil-freeze
sktlm-generate-representations
sktlm-validate-representations
```

`lexical_boundary` offsets reproduce source-provided whitespace only. They are
explicitly a proxy, not inferred or gold Sanskrit segmentation. See
`docs/methodology/representations.md`.

Run a provenance and tokenizer-diagnostics pass without model training:

```bash
sktlm-experiment --config configs/experiments/matrices/script_control/iast_character.yaml --dry-run
```

Run the controlled tiny backend:

```bash
sktlm-experiment --config configs/experiments/tiny_controlled.yaml
```

Each run writes `config.yaml`, `metrics.json`, `result.csv`, data and tokenizer
fingerprints, `git_commit.txt`, `predictions.jsonl`, and `logs.txt` below its
artifact directory. Experiment matrices live under
`configs/experiments/matrices/`; reusable condition fragments live under the
other stage-specific `configs/` directories.

Corpus cleaning, representation generation, tokenizers, experiments, and
evaluation are physically separate packages. Generated data progresses through
`data/intermediate`, `data/canonical`, and `data/representations`; generated
reports live under `reports/`. See `docs/workflows/repository_layout.md` and
`docs/workflows/corpus_cleaning.md`.

Historical pilot scripts, models, checkpoints, tokenizer artifacts, superseded
cleaning passes, and migration notes are preserved under `archive/legacy/` and
do not participate in the main pipeline. The archived 24k SentencePiece models
encode a historical joined-text condition and must not be presented as clean
observed-spacing Devanagari baselines.

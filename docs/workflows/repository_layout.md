# Repository layout

The main pipeline is organized by research stage:

```text
src/sktlm/corpus/            canonical construction and cleaning
src/sktlm/representations/   spacing and script derivation
src/sktlm/tokenizers/        tokenizer implementations and review
src/sktlm/experiments/       controlled models, training, and runs
src/sktlm/evaluation/        comparable metrics and reports
```

Tests mirror these package boundaries under `tests/`. Configuration lives under
`configs/corpus`, `configs/representations`, `configs/tokenizers`, and
`configs/experiments`.

Generated data progresses through `data/raw`, `data/intermediate`,
`data/canonical`, and `data/representations`. Manifests remain in
`data/manifests`. Reports are written to `reports/`, never back into `data/`.
Extraction and cleanup code may only write intermediate candidates; canonical
data is written by the explicit freeze stage.

Superseded pilot code and artifacts live under `archive/legacy/` and do not
participate in the main pipeline.

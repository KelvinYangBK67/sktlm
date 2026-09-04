# Repository layout

The main pipeline is organized by research stage:

```text
src/sktlm/corpus/            canonical construction and cleaning
src/sktlm/representations/   spacing and script derivation
src/sktlm/tokenizers/        tokenizer implementations and review
src/sktlm/experiments/       controlled models, training, and runs
src/sktlm/evaluation/        comparable metrics and reports
src/sktlm/latent/            script-neutral latent lexical induction
src/sktlm/pieces/            reusable untyped compositional pieces
src/sktlm/analysis/          generic scientific reduction and audit mechanisms
```

Tests mirror these package boundaries under `tests/`. Configuration lives under
`configs/corpus`, `configs/representations`, `configs/tokenizers`, and
`configs/experiments`.

Generated data progresses through `data/raw`, `data/intermediate`,
`data/canonical`, and `data/representations`. Manifests remain in
`data/manifests`. Reports are written to `reports/`, never back into `data/`.
Extraction and cleanup code may only write intermediate candidates; canonical
data is written by the explicit freeze stage.

Derived post-freeze substrates live under `data/derived` and carry explicit
source-freeze manifests. They never rewrite frozen M0 paths or metadata.

Superseded pilot code and artifacts live under `archive/legacy/` and do not
participate in the main pipeline.

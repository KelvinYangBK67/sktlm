# Formal M₀ baseline matrix

`m0_matrix.yaml` fixes the frozen manifests, 24k vocabulary budget, seed, and
artifact root shared by the 22 independently addressed formal cells.

Validate and print the complete matrix without training:

```bash
python -m sktlm.experiments.baselines.matrix --check-inputs
```

Run a deliberately bounded smoke check for any of the 22 implemented cells:

```bash
python -m sktlm.experiments.baselines.runner \
  --condition unicode_codepoint__devanagari__continuous \
  --max-train-segments 10 \
  --max-eval-segments 5
```

The runner consumes the frozen representation paths directly, fits every cell
from its own train split, streams both training preparation and evaluation, and
requires a clean Git worktree. It also refuses to overwrite an existing
cell/seed artifact directory. Omitting both segment limits requests the full
selected train/test data and must only be done when a formal production run has
been explicitly authorized.

The approved Akṣara-safe BPE and Surface-lattice semantics, including their
atomizers, barriers, likelihood, decoding, and reproducibility requirements,
are fixed in `reports/baselines/m0_method_contracts.md`. Neither method uses the
generic grapheme tokenizer or latent/core internals as a substitute.

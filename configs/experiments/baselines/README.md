# Formal M₀ baseline matrix

`m0_matrix.yaml` fixes the frozen manifests, 24k vocabulary budget, seed, and
artifact root shared by the 22 independently addressed formal cells.

Validate and print the complete matrix without training:

```bash
python -m sktlm.experiments.baselines.matrix --check-inputs
```

Run a deliberately bounded smoke check for one of the 18 currently supported
BPE, Unigram, or Unicode code-point cells:

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

Akṣara-safe BPE and Surface-lattice cells deliberately fail closed until the
method contracts in `reports/baselines/m0_method_contracts.md` are approved and
implemented. The existing grapheme tokenizer is not used as a substitute.

# Formal M₀ baseline matrix

`m0_matrix.yaml` is the versioned condition manifest. It retains the historical
22-cell design while marking 18 representation-valid production cells and four
IAST `continuous` cells as retired. It also fixes the frozen manifests, 24k
vocabulary budget, seed, and artifact root.

Validate and print the complete matrix without training:

```bash
python -m sktlm.experiments.baselines.matrix --check-inputs
```

Run a deliberately bounded smoke check for any valid cell:

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

Both the runner and the queue generator reject all retired cells before reading
training data or creating artifacts:

```bash
python -m sktlm.experiments.baselines.production
```

The queue command only prints commands; it never launches them. Historical or
diagnostic IAST-continuous artifacts must remain outside
`artifacts/baselines/m0` and cannot be scheduled through these entry points.

The approved Akṣara-safe BPE and Surface-lattice semantics, including their
atomizers, barriers, likelihood, decoding, and reproducibility requirements,
are fixed in `reports/baselines/m0_method_contracts.md`. Neither method uses the
generic grapheme tokenizer or latent/core internals as a substitute.

Formal runner invocations also train and score the common downstream tiny
Transformer contract. Add `--tokenizer-only` only for bounded diagnostics;
formal aggregation rejects such artifacts. Local smoke can use
`--downstream-device cpu --downstream-max-steps 1` without changing the frozen
production config. See `reports/baselines/m0_common_downstream_lm_contract.md`.

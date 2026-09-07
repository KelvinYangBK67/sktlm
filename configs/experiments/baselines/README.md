# Formal M₀ baseline matrix

`full_m0_matrix.yaml` is the current production contract. It adds four explicit
M0-prime corrected-continuous replacements to the 18 unchanged valid M0 cells,
for exactly 22 runnable cells. Its read-only M0-prime manifest identity is
`3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`.
The original four M0 IAST-continuous cells remain scientifically excluded and
cannot be selected through this config.

`m0_matrix.yaml` remains the historical `m0-baselines-v2` contract described
below; it is not rewritten or reinterpreted by the new production view.

Print the new plan without loading ignored payloads, or fail closed while
checking every formal input:

```bash
python -m sktlm.experiments.baselines.full_m0 \
  --config configs/experiments/baselines/full_m0_matrix.yaml
python -m sktlm.experiments.baselines.full_m0 \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --check-inputs
```

The second command is expected to fail on a checkout where the validated,
ignored M0-prime manifest and payload have not been provisioned. Deployment,
smoke, first-cell gating, production, analysis, and collection commands are in
`reports/baselines/full_m0_vm_runbook.md`.

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

A bounded diagnostic requires both segment limits. An unbounded cell additionally
requires `--production`; this flag rejects limits, tokenizer-only mode, runtime
overrides, and dirty Git state. Completed production bundles are aggregated only
through the fail-closed validator documented in
`reports/baselines/m0_aggregation_and_validity_gate.md`.

The non-blocking TransLIST interface is documented in
`reports/baselines/m0_translist_adapter.md`. The exact first-cell production and
audit procedure is `reports/baselines/m0_first_production_cell_audit.md`; no
command in that section was executed during local pre-cloud closure.

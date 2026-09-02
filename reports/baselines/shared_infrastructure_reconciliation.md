# Shared infrastructure reconciliation

Audit base: refreshed `origin/main` at `bdfc230`; baseline branch merge base
`bdfc230`.

There are no post-divergence commits on `origin/main`: the baseline branch is
strictly ahead. Consequently no commit was merged or cherry-picked and no
change below is represented as copied from `main`.

## Implemented locally

- Cross-platform Python 3.10/3.11 CI installs the declared project/test
  dependencies and runs the complete test suite.
- `scripts/repro/capture_environment.py` writes deterministic
  `environment.json` and sorted `requirements-freeze.txt` through the reusable
  `sktlm.experiments.environment` module.
- Reproducibility tests require byte-identical repeated capture and verify the
  requirements digest.
- NumPy is now an explicit dependency because the supported Torch runtime uses
  it; the inherited local venv lacks it and therefore continues to warn until
  that external environment is recreated or updated.

## Already equivalent on baseline

Commit `44f4402` already prefers SentencePiece 0.2.2 `offset_mapping` and falls
back to immutable proto offsets for older APIs. No second offsets patch was
applied.

## Not adopted

- The visible `origin/exp/m0-core-methods` cloud bootstrap, bridge, latent audit,
  n-gram, sandhi, and `src/sktlm/latent/` changes are branch-specific and outside
  baseline ownership.
- The obsolete 22-runnable-cell guidance is superseded by the versioned 22/18/4
  validity manifest, not reconciled back into production.

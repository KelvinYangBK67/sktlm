# Repository layout

This document describes the current tracked tree and the generated directories
used by the pipeline. A clean clone contains tracked metadata and code, but not
the ignored corpus or experiment payloads.

## Source packages

```text
src/sktlm/corpus/            corpus extraction, cleaning, and canonical freeze
src/sktlm/representations/   script/spacing derivation and M₀′ representation
src/sktlm/tokenizers/        tokenizer implementations and adapters
src/sktlm/experiments/       controlled models, training, and run entry points
src/sktlm/evaluation/        tokenizer, orthography, likelihood, and report metrics
src/sktlm/sandhi/            fixed-rule loading, realization, inversion, and exact DP
src/sktlm/latent/            script-neutral latent lexical induction
src/sktlm/pieces/            reusable untyped compositional-piece inference
src/sktlm/analysis/          scientific reduction, protocol, archival, and inventory audits
src/sktlm/review/            frozen-packet construction and verification support
```

Tests live under `tests/` and follow the corresponding package or workflow
boundaries. Operational and analysis entry points live under `scripts/`; source
packages remain the implementation authority.

## Configuration

The tracked configuration areas are:

```text
configs/corpus/              corpus membership and adjudicated cleaning decisions
configs/representations/     representation and M₀′ contracts
configs/tokenizers/          tokenizer conditions
configs/experiments/         experiment conditions and matrices
configs/analysis/            scientific reduction and retention manifests
configs/benchmarks/          fixed benchmark/workload definitions
configs/cloud/               credential-free deployment/run registry material
```

Real addresses, credentials, and machine-local bridge values are not stored in
these tracked files.

## Data lifecycle

| Path | Role | Repository state |
|---|---|---|
| `data/raw/` | Retained source material, including GRETIL input. | Generated/provisioned and ignored. |
| `data/intermediate/` | Stage-specific extraction, cleaning checkpoints, and candidates. | Generated and ignored. |
| `data/canonical/` | Frozen canonical corpus bytes. | Generated, ignored, and immutable after freeze. |
| `data/representations/` | Six generated frozen M₀ script/spacing datasets. | Generated and ignored. |
| `data/derived/` | Post-freeze derived substrates such as M₀′. | Generated and ignored; never rewrites M₀. |
| `data/manifests/` | Corpus and representation identities, membership, hashes, and checkpoints. | Tracked. |
| `data/rules/` | Fixed machine-readable linguistic rule inventories. | Tracked. |

Consequently, a clean worktree normally contains only `data/manifests/` and
`data/rules/` under `data/`. The other paths exist in a provisioned research
checkout after their documented inputs or generators have supplied them. Their
absence from a clean clone is not evidence that the tracked manifests or
reports are missing.

The pipeline direction is:

```text
data/raw
    → data/intermediate
    → data/canonical
    → data/representations
    → data/derived (only for explicit post-freeze derivations)
```

Representation generation never writes back into `data/canonical/`, and M₀′
never overwrites a frozen M₀ representation.

## Reports, artifacts, and archive

- [`reports/`](../../reports/README.md) contains tracked durable research,
  provenance, and navigation documents. `reports/cleaning/generated/` is the
  explicit ignored exception for reproducible detailed cleaning audits.
- `artifacts/` contains generated run outputs, databases, profiles, logs, and
  local evidence. It is ignored and is not the durable narrative when a
  tracked report exists.
- `archive/legacy/` contains superseded pilot code and historical material that
  does not participate in the current pipeline. Heavy pilot checkpoints and
  tokenizer model/vocabulary outputs remain ignored.

The tracked report tree currently contains `cleaning/`, `representations/`,
`baselines/`, `core_methods/`, and `reviews/`. There is no tracked
`reports/evaluation/` directory at this checkpoint; evaluation reporting code
lives under `src/sktlm/evaluation/`, while durable results belong in the
appropriate existing report area when produced.

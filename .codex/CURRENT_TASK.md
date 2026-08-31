# CURRENT_TASK.md

Current branch: `exp/m0-baseline-validation`

This branch owns baseline production and validation. It does not own the latent lexical core method.

## Completed implementation

- Workspace setup: `926429b`.
- SentencePiece 0.2.2 offsets: `44f4402`.
- `SHARED INTERFACE CHANGE`: `ae6835c` makes tokenizer evaluation accept an `Iterable`; behavior remains backward-compatible.
- Frozen direct-loader and initial matrix runner: `59d60ce`.
- Approved remaining four methods: `449adde`.
- Handoff before the four-method implementation: `0958afc`.

The formal matrix now reports exactly 22 implemented cells and zero pending method contracts:

- BPE: 6;
- Unigram: 6;
- Unicode code point: 6;
- Akṣara-safe BPE v1: Devanagari `continuous`;
- Surface-lattice v1: IAST `surface_word`, `legacy_joined`, and `continuous`.

Akṣara-safe BPE uses explicit Devanagari orthographic atoms, deterministic private-use surrogates, and barrier-safe BPE. Surface-lattice uses recorded-version IAST grapheme atoms, a train-only Unigram surface inventory, a trie-built complete DAG, deterministic Viterbi diagnostics, and complete-path log-sum-exp BPC/BPB. Neither imports or modifies `src/sktlm/latent/`.

## Verification

- `python -m pytest -q`: 346 passed; only the pre-existing missing-NumPy PyTorch warning and two nested-tensor warnings remain.
- `sktlm-validate-gretil-freeze`: 240 files, exact M₀ ID, zero invalid characters/apostrophes.
- `sktlm-validate-representations`: 1,440 files, exact M₀ ID.
- Formal plan check: 22 cells, 22 implemented, 0 pending, 240 documents, 1,440 frozen representation files.
- Read-only full train inventory per condition: 832,012 non-empty segments.
- Akṣara inventory: 16,730,381 atoms, 11,373 types, 6 barrier types, 11,378 minimum vocabulary slots.
- Each Surface-lattice inventory: 40 atom types, 3 barrier types, 45 minimum vocabulary slots; atom totals are recorded in `reports/baselines/m0_method_contracts.md`.
- The formal 24,000-piece budget fits all four new cells.
- Synthetic tests prove atom/barrier rules, exact known-token decoding, span coverage, lattice connectivity/ambiguity, unknown arcs, and repeat-fit byte determinism at a stable location.
- Clean-worktree frozen smoke runs passed for all four new cells using 20 train and 3 test segments, temporary vocab 512, and commit `449adde8382dab5f1fbe7e25adbc80b533193809`.
- The three smoke Surface-lattice cells produced finite positive BPC/BPB and nonzero ambiguous-node counts.
- All smoke artifacts are under `/tmp`; no formal full-corpus run was launched and no frozen file changed.

## Exact next task

The remaining implementation blocker is closed. Do not start the expensive formal full-corpus matrix without explicit user authorization.

Before a production launch:

1. run both frozen validators and the 22-cell plan check from a clean worktree;
2. confirm whether production scope is tokenizer/model artifacts only or also the common downstream language-model stage;
3. confirm available compute/storage and whether cells should run sequentially or under an external scheduler;
4. run one full cell first and audit its runtime, memory, unknown rate, artifacts, and provenance before scheduling the remaining 21; and
5. aggregate only complete, freeze-matched, independently trained cell results.

Read-only readiness command:

```bash
source .venv/bin/activate
python -m sktlm.experiments.baselines.matrix --check-inputs
```

Example bounded verification command:

```bash
source .venv/bin/activate
python -m sktlm.experiments.baselines.runner \
  --condition surface_lattice__iast__continuous \
  --max-train-segments 20 \
  --max-eval-segments 3
```

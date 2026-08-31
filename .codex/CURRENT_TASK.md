# CURRENT_TASK.md

Current branch: `exp/m0-baseline-validation`

This branch owns baseline production and validation. It does not own the latent lexical core method.

## Completed implementation

- Workspace setup commit: `926429b`.
- SentencePiece 0.2.2 offset compatibility commit: `44f4402`.
- `SHARED INTERFACE CHANGE` commit: `ae6835c` widens `evaluate_tokenizer` from a `list` input to an `Iterable`. The behavior is backward-compatible and enables bounded-memory baseline evaluation.
- Formal matrix/runner commit: `59d60ce`.
- The exact 22-cell matrix enumerates 18 runnable BPE/Unigram/Unicode code-point cells plus four fail-closed pending-method cells.
- Frozen representation access validates 240 canonical manifest members and exactly 1,440 files across the six formal conditions.
- The runner fits each supported cell independently from frozen train paths, streams evaluation, refuses dirty Git state and artifact overwrite, and emits complete provenance/fingerprints.
- `reports/baselines/m0_method_contracts.md` records the unresolved Akṣara-safe BPE and Surface-lattice semantics as a proposal, not a frozen decision.

## Verification

- `python -m pytest -q`: 337 passed; only the pre-existing missing-NumPy PyTorch warning and two nested-tensor warnings remain.
- `sktlm-validate-gretil-freeze`: 240 files; exact frozen M₀ ID; zero invalid characters/apostrophes.
- `sktlm-validate-representations`: 1,440 files; exact frozen M₀ ID.
- Real frozen-input bounded smoke runs passed for Unicode code point and BPE. A post-commit clean-worktree run recorded commit `59d60ce771063d0c4ddde13c7b74e4345877ff3b`.
- No formal full-corpus matrix was launched, and generated smoke artifacts exist only under `/tmp`.

## Exact next task

Obtain research-owner approval or replacement definitions for the two proposed method contracts in `reports/baselines/m0_method_contracts.md`:

1. Akṣara atomization, merge barriers, deterministic BPE rules, and span/decoding policy.
2. Surface-lattice nodes/arcs, surface-only candidate source, objective/decoding, common likelihood interface, and leakage policy.

After approval:

1. record the approved semantics in `.codex/DECISIONS.md`;
2. implement and test Akṣara-safe BPE without treating generic grapheme clusters as an automatic substitute;
3. implement and test Surface-lattice without importing, copying, or modifying `src/sktlm/latent/`;
4. rerun the exact 22-cell completeness and provenance tests;
5. request explicit authorization before launching any formal full-corpus production run.

Useful read-only plan command:

```bash
source .venv/bin/activate
python -m sktlm.experiments.baselines.matrix --check-inputs
```

Example bounded supported-cell smoke command (only when the target artifact directory does not already exist):

```bash
source .venv/bin/activate
python -m sktlm.experiments.baselines.runner \
  --condition unicode_codepoint__devanagari__continuous \
  --max-train-segments 10 \
  --max-eval-segments 5
```

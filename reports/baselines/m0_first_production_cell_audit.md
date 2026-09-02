# First production cell audit procedure

Recommended first cell:
`unicode_codepoint__devanagari__surface_word`.

It is a valid cross-script/common-spacing condition, has no SentencePiece fit,
and has a small transparent vocabulary. It therefore exposes frozen I/O,
downstream LM, unknown, resource, environment, and provenance failures with the
least tokenizer-specific operational risk. It does not receive privileged
initialization or a different scientific budget.

## Preflight (read-only)

From the clean pre-cloud production commit on the prepared CUDA host:

```bash
sktlm-validate-gretil-freeze
sktlm-validate-representations
python -m sktlm.experiments.baselines.matrix --check-inputs
python scripts/repro/capture_environment.py --output-dir /tmp/m0-preflight-environment
python -m sktlm.experiments.baselines.production \
  --condition unicode_codepoint__devanagari__surface_word \
  --output /tmp/m0-first-cell-queue.json
```

Confirm 240 frozen documents, 1,440 frozen representation files, 22 historical
records, 18 valid cells, 4 retired cells, one queued job, a clean worktree,
available CUDA, sufficient storage, and the intended commit. The queue command
does not launch training.

## Explicit launch (not run during local pre-cloud closure)

```bash
python -m sktlm.experiments.baselines.runner \
  --condition unicode_codepoint__devanagari__surface_word \
  --production
```

The `--production` gate requires complete train/test splits, the frozen CUDA
device and 20-step common LM contract, clean Git, no tokenizer-only mode, and no
runtime override. The artifact is complete only after `COMPLETED.json` exists.

## Audit before scheduling another cell

```bash
python -m sktlm.experiments.baselines.audit \
  --condition unicode_codepoint__devanagari__surface_word \
  --artifact-dir artifacts/baselines/m0/unicode_codepoint__devanagari__surface_word/seed_0 \
  --output reports/baselines/generated/first_cell_audit.json
```

The audit checks the completion hash inventory, checkpoint, runtime, process
peak RSS, unknown count/rate/semantics, common BPC/BPB/canonical-unit score,
script-diagnostic scope, fresh initialization, freeze/data/tokenizer/code/
environment provenance, and artifact location.

`engineering_failure` means the bundle, resources, software, paths, hashes, or
execution contract are incomplete. Preserve and quarantine the partial bundle
outside the formal root, correct infrastructure, and rerun from a clean state;
do not aggregate it. `scientific_semantics_failure` means engineering checks
passed but an unknown/likelihood/scope invariant failed. Stop the queue and
review the frozen contract; do not tune, substitute, or silently retry. Only
`pass` authorizes scheduling the remaining 17 valid cells.

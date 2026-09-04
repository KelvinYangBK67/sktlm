# AGENTS.md

This repository contains the `sktlm` Sanskrit corpus/tokenization research project.

## Before doing any work

1. Read `.codex/PROJECT_STATE.md`.
2. Read `.codex/DECISIONS.md`.
3. Read `.codex/CURRENT_TASK.md`.
4. Inspect the actual repository/branch before modifying code. Do not rely only on handoff text if the code has moved.
5. Treat `PROJECT_STATE.md` and `DECISIONS.md` as authoritative unless the user explicitly changes a decision.

## Frozen data

Do not modify the frozen M₀ corpus, manifest, formal representations, freeze metadata, or the `m0` tag.

Do not rewrite `data/rules/external_sandhi.tsv` unless the user explicitly requests a rule-inventory change.

`notes/**` is strictly local-only. Read, inspect, or search it only when useful
for the current research or implementation task. Never modify, create, move,
rename, delete, copy, overwrite, track, stage, commit, restore, checkout, or
force-add anything under `notes/`; never weaken ignore/tracking policy to make
it trackable.

## Research guardrails

- Do not equate lexical boundary with whitespace, `#`, apostrophe, or avagraha.
- Do not use raw IAST characters as the final linguistic representation.
- Do not use dictionaries, gold segmentation, morphological analyzers, or pretrained Sanskrit models to make a surface-only induction task easier unless explicitly authorized.
- Do not turn the old character n-gram toy prototype into the final method by incremental patching.
- Preserve genuine ambiguity; do not hard-decode early when a posterior/lattice representation is intended.
- Keep the fixed external-sandhi grammar separate from the learned latent lexicon.
- Do not introduce a generic learned or hand-set reward merely for “using more sandhi”.

## Engineering style

Follow the repository's existing package, test, config, and artifact conventions after inspecting them.

Use focused tests for core invariants. Do not create a large test suite for every small helper.

For full-corpus work, use streaming/sharded bounded-memory processing. Do not materialize the entire corpus or all candidate lattices in RAM.

Do not launch a long full-corpus experiment automatically unless the user explicitly asks to run it.

## End-of-task handoff

Before finishing a substantial task:

- update `.codex/PROJECT_STATE.md` with durable new state;
- update `.codex/DECISIONS.md` only when a research/design decision has actually changed;
- replace or revise `.codex/CURRENT_TASK.md` so the next Codex session knows what remains;
- report changed files, tests/sanity checks, and exact next command(s).

# AGENTS.md

This repository contains the `sktlm` Sanskrit corpus, tokenization, and language-model research project.

## Before doing any work

1. Read `.codex/PROJECT_STATE.md`.
2. Read `.codex/DECISIONS.md`.
3. Read `.codex/CURRENT_TASK.md`.
4. Inspect the actual repository and current branch before modifying code.

Do not rely only on handoff text when repository state can be checked directly.

## Frozen data

M₀ is frozen. Do not modify the frozen canonical corpus, formal representations, tracked manifests, freeze metadata, or the `m0` tag. Do not regenerate or reclean M₀ to repair a mismatch. Report an exact blocker instead.

Do not reopen corpus QA unless the user explicitly reopens corpus scope.

## Branch responsibility

- `exp/m0-baseline-validation` owns baseline production and validation.
- `exp/m0-core-methods` owns the latent/sandhi core method.

The baseline branch must not merge, cherry-pick, copy, or reimplement latent core code and must not modify `src/sktlm/latent/`.

## Engineering

- Reuse existing package, test, configuration, and artifact conventions.
- Keep full-corpus work reproducible, deterministic, and bounded-memory.
- Do not commit large generated artifacts, the local `.venv`, archives, canonical data, or representations.
- Do not launch an expensive full-corpus experiment without explicit user authorization.
- Prefer baseline-specific modules over adding baseline-only behavior to shared interfaces.
- Keep necessary shared changes backward-compatible, isolated in their own commit, and label them `SHARED INTERFACE CHANGE` in the handoff.

## End of task

Before finishing a substantial task:

- put durable state in `.codex/PROJECT_STATE.md`;
- record only durable decision changes in `.codex/DECISIONS.md`;
- put immediate next work in `.codex/CURRENT_TASK.md`;
- report changed files, tests, failures, and exact next commands.

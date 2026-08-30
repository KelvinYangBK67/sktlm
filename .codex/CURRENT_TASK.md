# CURRENT_TASK.md

## Current status

The full-corpus-ready v1 `IAST + surface_word` latent lexical learner has been implemented on:

`exp/m0-core-methods`

A bounded sanity run completed at:

`artifacts/latent_lexicon/sanity_v1d/`

The expensive full M₀ run has **not** been launched. Do not launch it without an explicit user request.

Read `AGENTS.md`, `.codex/PROJECT_STATE.md`, and `.codex/DECISIONS.md` before continuing. Inspect the actual branch and worktree, and do not treat any pre-existing local changes as disposable output.

## Next task

After explicit user authorization, run the first full M₀ `IAST + surface_word` experiment, monitor checkpoints, validate artifact completeness, and interpret the learned lexicon without reducing the result to one score.

Before the full run, rerun the focused latent/sandhi tests. Do not modify the frozen M₀ corpus, manifest, freeze metadata, `m0` tag, or the 1218-rule inventory.

## Full-run command

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m sktlm.experiments.training.latent_lexicon `
  --manifest data/manifests/representations.csv `
  --output-root artifacts/latent_lexicon `
  --run-id m0_iast_surface_word_v1 `
  --passes 3
```

Resume the same run by adding:

```text
--resume
```

## Required post-run audit

Confirm that the output contains the learned lexicon, analyses, boundary posteriors, rule usage, ambiguity/confidence statistics, identity-vs-latent mass, complexity summary, configuration/provenance, checkpoints, and inspection report.

In addition to the four primary research questions in `PROJECT_STATE.md`, explicitly audit:

1. posterior mass conservation on ambiguous lexical alternants;
2. whether frequent latent forms gain support across multiple surface and sandhi environments;
3. whether low-count types reveal identity collapse, overanalysis, or legitimate ambiguity;
4. whether `om` / `oṃ` remains symmetric outside the bounded sanity sample.

For `om` / `oṃ`, preserve the distinct phonological keys and report context-conditioned evidence. The sanity-run equality is already diagnosed as fixed-grammar ambiguity (`EXT_0795` before `n`, `EXT_0793` before `b`), not duplicate counting. Do not introduce a special case, collapse `m` with anusvāra, or alter the rule inventory without an explicit durable research decision.

## Known validation state

- focused latent/sandhi suite: `84 passed`;
- repository suite excluding known SentencePiece compatibility failures: `428 passed, 3 deselected`;
- the three known full-suite failures come from the untouched SentencePiece wrapper calling the removed `encode_as_immutable_proto` API.

## End-of-task handoff

After the authorized full run or any substantial follow-up change:

- update `.codex/PROJECT_STATE.md` with durable results;
- update `.codex/DECISIONS.md` only if the user actually changes a durable research/design decision;
- revise this file to state the next concrete task;
- report changed files, checks, artifact path/schemas, and exact continuation commands.

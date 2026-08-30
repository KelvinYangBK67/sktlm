# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`

The exact latent/sandhi core workflow has completed its cheap single-process and deterministic multiprocessing optimization round. Accepted commits through `3da7ad1` preserve scientific outputs. The final repeated 3-pass smoke median is 13.305 seconds with four workers versus 19.268 seconds serial (1.45x end to end).

The completed medium reference remains:

`artifacts/latent_benchmarks/medium_reference_p1/`

Do not rerun that reference. No post-optimization medium or full M₀ run has been launched.

Current validation: `tests/latent` has `22 passed`; the full suite has `444 passed, 3 failed`. The three failures are the known untouched SentencePiece 0.2.2 `immutable_proto` compatibility failures, not latent-method regressions.

Read `AGENTS.md`, `.codex/PROJECT_STATE.md`, `.codex/DECISIONS.md`, and `reports/core_methods/latent_lexicon/performance_optimization_v1.md` before continuing. Do not discard local work or modify frozen M₀ data/rules.

## Next task: user-run medium scaling validation

This command is expected to exceed five minutes. Codex must not wait for or continuously poll it. The user should launch it manually from the repository root:

```powershell
.\.venv\Scripts\python.exe -m sktlm.latent.benchmark `
  --benchmark medium `
  --run-id medium_optimized_p8_w4_p3 `
  --passes 3 `
  --workers 4
```

Expected output directory:

`artifacts/latent_benchmarks/medium_optimized_p8_w4_p3/`

Completion signal: the process exits successfully and `benchmark_metrics.json`, `timing_metrics.json`, `summary.json`, `latent_lexicon.tsv`, `analyses.jsonl`, and `boundary_posteriors.jsonl` exist. To check whether it is still running, inspect the Python process in Task Manager or run `Get-Process python -ErrorAction SilentlyContinue`; do not infer completion from shard files alone.

After completion, inspect:

- `benchmark_metrics.json` for end-to-end wall/CPU, phase timing, artifact bytes, and worker count;
- `timing_metrics.json` for training/inspection worker CPU, inference, candidate generation, SQLite, and serialization;
- `checkpoint.json` for `completed_passes = 3` and `inspection_complete = true`;
- `summary.json` and the scientific artifacts for completeness;
- any retained `shards/` files, which indicate interrupted cleanup or a failed run.

Compare scientific outputs against the appropriate serial/reference run with `sktlm.latent.equivalence`. Because the old medium reference has only one training pass, it cannot directly establish 3-pass scientific equivalence; if a 3-pass serial medium reference is needed, treat that as a separate user-run long job. Do not silently compare unlike pass counts.

## Memory caveat

`benchmark_metrics.json:peak_rss_bytes` currently covers the main process only. For multiprocessing it excludes worker RSS. Record process-tree memory externally during the medium run, or implement a correct aggregate sampler before making a full-run worker-count decision.

## After the medium artifact returns

1. Validate artifact completeness and exact pass/worker configuration.
2. Report training and inspection scaling separately; do not extrapolate only from Pass 1.
3. Check crash-resume/shard cleanup state.
4. Update the optimization report and these handoff files with measured medium results.
5. Only then prepare the full 3-pass + inspection command and time projection. The user must explicitly authorize and manually manage that long run.

Do not alter the frozen corpus, manifest, `m0` tag, or fixed 1218-rule inventory. Preserve the diagnosed `om` / `oṃ` ambiguity; it is not duplicate counting.

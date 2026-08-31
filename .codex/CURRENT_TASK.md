# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`

The optimized 4-worker, 3-pass medium benchmark completed successfully at:

`artifacts/latent_benchmarks/medium_optimized_p8_w4_p3/`

It ran from commit `049d439` in 2,141.125 seconds (35m41s), with all three training passes and inspection complete. Artifact integrity checks passed: zero candidate overflow, `PRAGMA quick_check = ok`, expected artifact row counts, no retained shard files, and matching SQLite/export count totals within normal floating-point accumulation tolerance. Pass 1 iteration metrics are exactly identical to the old 1-pass medium reference.

The completed artifact projects to about 8.09 hours for full M₀ by character throughput. This is materially faster than the reference but remains about 2.70x short of the approximately 3-hour target. Do not launch the full corpus yet.

Two additional semantics-preserving optimizations are committed after P8:

- `e731d6c`: bounded rolling worker submission, keeping up to `2 * workers` tasks in flight while preserving canonical reduction order and crash-safe shards;
- `dc68089`: direct scalar serialization of boundary posteriors, avoiding recursive dataclass conversion.

P9 reduced repeated 4-worker smoke wall median from 13.305 to 10.322 seconds, with zero scientific mismatches. P10 reduced the targeted inspection-serialization median from 1.841 to 1.683 seconds (8.6%), also with zero mismatches. The focused latent suite reports `22 passed`. Neither P9 nor P10 has yet been measured on medium.

The medium corpus breaks the sanity-run `om` / `oṃ` symmetry: inspection expected counts are 50.809742 and 27.907685 respectively, while final training counts are 47.612692 and 29.976378. Literal `om iti` / `om ity...` contexts and literal `oṃ ...` contexts provide different evidence. The two phonological keys remain intentional, and there is no indication of representation or expected-count duplication.

Read `AGENTS.md`, `.codex/PROJECT_STATE.md`, `.codex/DECISIONS.md`, and `reports/core_methods/latent_lexicon/performance_optimization_v1.md` before continuing. Do not discard local work or modify frozen M₀ data/rules.

## Next task: user-run P10 medium validation

This command is expected to exceed five minutes. Codex must not launch it automatically, wait for it, or continuously poll it. The user should launch it manually from the repository root:

```powershell
.\.venv\Scripts\python.exe -m sktlm.latent.benchmark `
  --benchmark medium `
  --run-id medium_optimized_p10_w4_p3 `
  --passes 3 `
  --workers 4
```

Expected output directory:

`artifacts/latent_benchmarks/medium_optimized_p10_w4_p3/`

Expected completion signal: the process exits successfully; `checkpoint.json` has `completed_passes = 3` and `inspection_complete = true`; `benchmark_metrics.json`, `timing_metrics.json`, `summary.json`, `latent_lexicon.tsv`, `analyses.jsonl`, and `boundary_posteriors.jsonl` exist; and no shard files remain.

To check whether it is still running, use Task Manager or:

```powershell
Get-Process python -ErrorAction SilentlyContinue
```

Do not infer completion from the presence of partial artifacts or directories.

After completion, compare P10 directly against the completed same-pass P8 artifact:

```powershell
.\.venv\Scripts\python.exe -m sktlm.latent.equivalence `
  artifacts/latent_benchmarks/medium_optimized_p8_w4_p3 `
  artifacts/latent_benchmarks/medium_optimized_p10_w4_p3
```

Inspect:

- `benchmark_metrics.json` for wall/CPU time, throughput, artifact bytes, and worker count;
- `timing_metrics.json` for training/inspection phase timings, especially document wall and inspection serialization;
- `checkpoint.json` and `shards/` for completion and crash-cleanup state;
- `summary.json` plus equivalence output for scientific identity;
- process-tree memory measured externally, because `peak_rss_bytes` covers only the main process when multiprocessing is enabled.

Use the new medium result to revise the full-M₀ projection. Do not start a full run until the approximately 3-hour target is credible or the user explicitly accepts a longer run.

Do not alter the frozen corpus, manifest, `m0` tag, or fixed 1218-rule inventory. Preserve the distinct `C_M` and `M_ANUSVARA` representations.

# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`

The P10 4-worker, 3-pass medium benchmark completed successfully at:

`artifacts/latent_benchmarks/medium_optimized_p10_w4_p3/`

It ran from commit `9be29ea` in 1,216.915 seconds (20m17s), versus 2,141.125 seconds for P8: a 1.759x end-to-end speedup. Training document wall fell 29.2% to 625.509 seconds and inspection document wall fell 55.9% to 523.347 seconds. Inspection inference fell 15.0%, candidate generation 18.4%, and serialization 30.0%.

Artifact integrity and identity checks passed:

- three training passes and inspection are complete;
- 20 documents, 95,847 segments, and 4,231,365 characters per pass;
- zero candidate overflow and zero retained shard files;
- `PRAGMA quick_check = ok`;
- 1,888,526 rows in both training and inspection count tables;
- training count sum 394,031.7571645344 and inspection count sum 395,770.48199961643;
- P8 and P10 `iteration_metrics.json`, `summary.json`, `analyses.jsonl`, `boundary_posteriors.jsonl`, `latent_lexicon.tsv`, and `rule_usage.tsv` are byte-for-byte SHA-256 identical.

The conservative full-M₀ projection is now about 4.60 hours by character throughput, or 4.06 hours by document count. This is substantially closer but still requires about 1.53x further speedup to reach three hours under the conservative projection.

The experimental per-token internal-match inventory reuse after P10 was scientifically equivalent but did not show a reproducible phase or wall benefit against a contemporaneous current-host control. It was fully reverted and not committed.

The worktree should be clean at commit `9be29ea` before the documentation commit that records this result. Read `AGENTS.md`, `.codex/PROJECT_STATE.md`, `.codex/DECISIONS.md`, and `reports/core_methods/latent_lexicon/performance_optimization_v1.md` before continuing. Do not modify frozen M₀ data or rules.

## Next task: user-run 8-worker medium scaling

The next measurement is the same P10 code and scientific configuration with eight workers. It is expected to exceed five minutes. Codex must not launch it automatically, wait for it, or continuously poll it. The user should launch it manually from the repository root:

```powershell
.\.venv\Scripts\python.exe -m sktlm.latent.benchmark `
  --benchmark medium `
  --run-id medium_optimized_p10_w8_p3 `
  --passes 3 `
  --workers 8
```

Expected output directory:

`artifacts/latent_benchmarks/medium_optimized_p10_w8_p3/`

Expected completion signal: the process exits successfully; `checkpoint.json` has `completed_passes = 3` and `inspection_complete = true`; the main scientific and metrics files exist; and no shard files remain.

Check whether it is still running, and observe process-tree memory, with Task Manager or:

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Select-Object Id, CPU, WorkingSet64
```

The benchmark's `peak_rss_bytes` remains main-process-only. Record the maximum combined Python working set externally before choosing a worker count for full M₀.

After completion, inspect `benchmark_metrics.json`, `timing_metrics.json`, `checkpoint.json`, `summary.json`, and `shards/`. Compare the six deterministic scientific artifacts against the completed 4-worker P10 run by size and SHA-256:

```powershell
$reference = 'artifacts\latent_benchmarks\medium_optimized_p10_w4_p3'
$candidate = 'artifacts\latent_benchmarks\medium_optimized_p10_w8_p3'
$scientific = @(
  'iteration_metrics.json',
  'summary.json',
  'analyses.jsonl',
  'boundary_posteriors.jsonl',
  'latent_lexicon.tsv',
  'rule_usage.tsv'
)
foreach ($name in $scientific) {
  $left = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $reference $name)
  $right = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $candidate $name)
  [pscustomobject]@{
    Name = $name
    Equal = $left.Hash -eq $right.Hash
    SHA256 = $right.Hash
  }
}
```

The existing `sktlm.latent.equivalence` implementation materializes multi-gigabyte JSONL/TSV files and should not be used for medium/full artifacts until it is made streaming and bounded-memory. Exact hashes are stronger when outputs are expected to be byte-identical.

Use the 8-worker result to decide whether the approximately 3-hour full-M₀ target is credible. Do not launch the full run automatically.

Do not alter the frozen corpus, manifest, `m0` tag, or fixed 1218-rule inventory. Preserve the distinct `C_M` and `M_ANUSVARA` representations.

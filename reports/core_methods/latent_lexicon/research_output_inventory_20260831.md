# Local research-output inventory — 2026-08-31

This is a bounded inventory of small report-like material under `reports/`,
`notes/`, and run-root files under `artifacts/`. Bulk JSONL, SQLite, corpus, and
deep shard contents were neither read nor hashed. No local file was deleted or
blindly added to Git.

Categories: **A PROMOTE**, **B KEEP GENERATED / LOCAL**, **C OPERATIONAL
LOCAL-ONLY**, **D HISTORICAL / SUPERSEDED**, and **E DUPLICATE**.

| Source path | Size observed | Git status | Category / scientific role | Authoritative / promoted to | Action |
|---|---:|---|---|---|---|
| `artifacts/cloud_collected/cloud_medium_p10_w4_p3/benchmark/benchmark_metrics.json` | 2,813 B | ignored | A; cloud w4 performance | `cloud_scaling_checkpoint_20260831.md` | distilled, source retained locally |
| `artifacts/cloud_collected/cloud_medium_p10_w4_p3/remote_audit.json` | 2,566 B | ignored | A; completion, DB integrity, scientific hashes | `cloud_scaling_checkpoint_20260831.md` | distilled, source retained locally |
| `artifacts/cloud_collected/cloud_medium_p10_w4_p3/metrics/process_tree_summary.json` | 756 B | ignored | A; aggregate resource evidence | `cloud_scaling_checkpoint_20260831.md` | peak RSS promoted |
| `artifacts/cloud_collected/cloud_medium_p10_w4_p3/metrics/process_tree_samples.csv` | 106,762 B | ignored | B; reproducible detailed samples | tracked cloud checkpoint summary | keep local |
| `artifacts/latent_benchmarks/medium_optimized_p10_w4_p3/` | root reports 740–40,432 B each; bulk unmeasured | ignored | B; accepted local w4 raw evidence | `medium_scaling_p10.md` | already promoted; keep local |
| `artifacts/latent_benchmarks/medium_optimized_p10_w8_p3_rerun1/` | root reports 747–40,432 B each; bulk unmeasured | ignored | B; accepted local w8 raw evidence | `medium_scaling_p10.md` | already promoted; keep local |
| `artifacts/latent_benchmarks/medium_optimized_p10_w8_p3_interrupted/` | checkpoint 423 B; config 740 B; provenance 1,013 B | ignored | D; crash/partial-run provenance | `medium_scaling_p10.md` | keep; never treat as a result |
| `artifacts/latent_benchmarks/` (85 run directories) | inspected root report files 423–41,680 B each; bulk unmeasured | ignored | B/E; optimization smokes and repeated controls | `performance_optimization_v1.md` where decision-relevant | keep generated; no wholesale promotion |
| `artifacts/latent_lexicon/m0_iast_surface_word_v1_interrupted_20260830_1600/` | SQLite 3,514,896,384 B; WAL 110,436,632 B; other root metadata 422–196,608 B | ignored | D; interrupted full-run diagnostics | `interrupted_m0_20260830_diagnostics.md` | keep local pending any future archival decision |
| `artifacts/latent_lexicon/sanity_v1*` | bulk unmeasured | ignored | B/E; early sanity outputs | later formal reports supersede them | keep local; not authoritative |
| `artifacts/cloud_transfers/` (10 JSON receipts) | 345,012 B total | ignored | C/B; deploy/push/collect operational provenance | not a scientific result | keep local; may contain host identifiers |
| `.sktlm-bridge.toml` | 511 B | ignored | C; real SSH/host configuration | never tracked | contents not copied; add host profiles locally |
| `reports/cleaning/generated/` | observed files 30 B–87,912,084 B | ignored | B/E; reproducible stage audits, occurrence tables, and repeated checkpoints | tracked cleaning closure reports | keep generated; do not add wholesale |
| `notes/baseline_prompt_m0.txt` | 25,378 B | ignored | D; old baseline-branch handoff | superseded by branch state/docs | keep local |
| `notes/IAST_to_Devanagari.txt` | 3,209 B | ignored | D; early conversion sketch | representation implementation/reports | keep local |
| `notes/manual_canonical_check.txt` | 4,044 B | ignored | D; pre-freeze manual cleaning notes | tracked cleaning closure/provenance | keep local |
| `notes/plan.md` | 14,027 B | ignored | D; conceptual research roadmap | `.codex` decisions and tracked method reports | retain for human history |
| `notes/sandhi/sanskrit_external_sandhi_matrix.csv` | 6,792 B | ignored | D/E; working grammar-design note | fixed tracked 1,218-rule inventory is authoritative | keep local; do not merge into rules |
| `notes/sandhi/sanskrit_external_sandhi_relations.csv` | 29,011 B | ignored | D/E; working grammar-design note | fixed tracked 1,218-rule inventory is authoritative | keep local; do not merge into rules |

## Human judgment required before any future cleanup

Do not delete the interrupted-run directories, cloud receipts, old notes, or
generated cleaning stages merely because their conclusions are promoted.
Their archival value and external backup status have not been established.
Repeated smoke directories are scientifically redundant at the conclusion
level, but may still be useful for implementation provenance. This task makes
no deletion recommendation beyond identifying those distinctions.

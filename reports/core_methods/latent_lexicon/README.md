# Latent lexicon research reports

This directory is the tracked, human-readable research record for the Stage 01 latent-lexicon/core-method line.

Raw run outputs under `artifacts/` remain intentionally gitignored. They may be large, host-specific, incomplete, or disposable. **Any result that changes a research conclusion, implementation decision, performance projection, or next-step decision must be promoted into a tracked report here and must not exist only inside `artifacts/`.**

## Source-of-truth hierarchy

1. Frozen corpus/rule/config provenance in tracked repository files.
2. Tracked Markdown reports in this directory for durable experimental conclusions.
3. `artifacts/` for raw machine outputs, detailed diagnostics, large JSONL/SQLite files, shards, and reproducibility evidence that is useful locally but is not itself the durable research narrative.

The artifact path may be cited by a report, but the report must contain enough metadata and results to understand the experiment if the local artifact later disappears.

## Current report index

- `performance_profile_v1.md` — original profiling and bottleneck analysis.
- `performance_optimization_v1.md` — P0–P10 optimization history, accepted/rejected changes, medium measurements, integrity/equivalence results, and scaling projections.
- `interrupted_m0_20260830_diagnostics.md` — diagnosis of the interrupted first full-M₀ attempt and the resume-safety failure class that motivated P0.
- `medium_scaling_p10.md` — audited P10 4-vs-8 local medium scaling, exact scientific hashes, integrity results, interrupted 8-worker diagnostic, and local worker decision.
- `cloud_deployment_ubuntu22.md` — guarded Ubuntu/data-disk bootstrap, provenance checks, resource monitoring, and staged cloud scaling/full-run gate.
- `stage01_checkpoint_20260831.md` — compact Stage 01 checkpoint before cloud deployment/full M₀.

- `cloud_scaling_checkpoint_20260831.md` — authoritative closed cloud w4/w8/w12/w16 comparison, exact scientific equivalence, frozen 8-worker selection, and planned full-M0 replica gate.
- `research_output_inventory_20260831.md` — bounded classification of ignored/local reports, artifacts, notes, promotions, and historical duplicates.

The `evidence/` subdirectory preserves the minimum machine-readable evidence
for accepted formal benchmark decisions and a manifest of established large
artifact hashes.

Future full-corpus results should receive their own tracked report rather than being represented only by the generated `inspection_report.md` or other files inside an artifact directory.

## Promotion checklist for expensive runs

For every medium/full run that informs a decision, promote the following into a tracked Markdown report before the run is treated as a durable project checkpoint:

- run ID and local artifact path;
- code commit/branch;
- frozen corpus condition, freeze ID, rule inventory, and scientific hyperparameters;
- workers/host information relevant to performance interpretation;
- wall time and important phase timings;
- completion state: passes, inspection, overflow, shard cleanup;
- database/integrity checks;
- scientific equivalence evidence, including hashes where available;
- key scientific diagnostics used in interpretation;
- performance projection and the decision made from the run;
- known caveats (for example main-process-only RSS or host-state noise).

Large scientific outputs themselves should not be committed merely to satisfy this rule. Commit summaries, hashes, counts, selected diagnostics, and provenance; keep multi-GB JSONL/SQLite/shard outputs in `artifacts/` or external archival storage.

## Naming convention

Use stable descriptive names rather than artifact run IDs alone, for example:

- `medium_scaling_p10.md`
- `full_m0_iast_surface_word_v1.md`
- `stage01_scientific_audit_v1.md`

If a report is an evolving optimization log, update the existing versioned report. If it is a scientifically meaningful full run or milestone, prefer a dedicated report that can be cited independently.

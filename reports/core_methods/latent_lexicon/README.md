# Latent lexicon research reports

This directory is the tracked, human-readable research record for the Stage 01 latent-lexicon/core-method line.

## Naming clarification

“Stage 01” in this directory and its historical filenames denotes the
latent-lexicon/core-method work line as it was recorded at the time; it is
preserved as provenance and is not retroactively renamed. Under the current
research nomenclature, `M₀` is the frozen common benchmark substrate, while
`full-M₀` describes a run's full frozen-corpus extent for one representation
condition. Neither term names the latent model or declares a completed S1M1.

The current full-M₀ work belongs to pre-S1M1 infrastructure and capacity
calibration. `IAST + surface_word` has been the algorithm/deployment anchor,
not the final selection of a sole S1M1 representation. Historical report
names, `full_m0_*` run IDs, and `stage01_checkpoint_20260831.md` remain
unchanged. The authoritative Stage/Milestone definitions and S1–S3 plan are in
[`../../../docs/research_roadmap.md`](../../../docs/research_roadmap.md).

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
- `pre_s1m1_calibration_checkpoint_20260901.md` — closes unrestricted replica and K16/K32 capacity calibration and records the unrestricted six-representation decision.
- six_representation_gate_launch_plan_20260901.md — exact human-operated deployment/launch record plus post-completion audit commands for the five RUNNING representation cells.
- six_representation_gate_launch_checkpoint_20260901.md — scientific SHA, six-cell status, assignments/PIDs, frozen-input hashes, bundle deployment, and immediate launch verification.
- `post_gate_analysis_protocol.md` — frozen fail-closed six-cell aggregation, paired comparison, mass-support, TV/JSD, and qualitative-inspection contract; it contains no result.
- `continuous_performance_source_analysis.md` — static source-only bottleneck analysis and post-freeze profiling/optimization plan; it changes no runtime semantics.
- [`../../../reviews/protocol/independent_llm_review_protocol.md`](../../../reviews/protocol/independent_llm_review_protocol.md) — five fresh-session reviewers, identical frozen packet, raw preservation, synthesis, and adjudication protocol.

The `evidence/` subdirectory preserves the minimum machine-readable evidence
for accepted formal benchmark decisions and a manifest of established large
artifact hashes.

`full_m0_launch_plan.md` records the prepared four-replica run/metrics IDs,
the supported full-corpus entry point, lightweight monitoring, and final audit
workflow. It is a preserved historical preparation record, not launch
authorization; the dated 2026-09-01 checkpoint and representation-gate plan
supersede it for current work without modifying it.

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

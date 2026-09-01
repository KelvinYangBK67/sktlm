# CURRENT_TASK.md

## Current status

Branch: exp/m0-core-methods.

Pre-S1M1 calibration is CLOSED. The frozen M0 corpus, six representations,
freeze metadata, m0 tag, 1,218-rule inventory, and unrestricted
latent-lexicon-v1 semantics remain unchanged.

The four unrestricted IAST surface_word full-M0 replicas completed
successfully at 8 workers and three passes. Their six canonical scientific
artifacts are byte-identical. Fixed-K sensitivity is also closed: K16 and K32
are appendix stress conditions in the same strong projection-pressure regime,
not an active grid or natural-size search. Do not add K values or execute the
previously contemplated 18-cell matrix.

The representation frontend is ready for all six formal cells. The
script-neutral phonological core preserves existing IAST defaults and now
accepts the repository-generated M0 Devanagari representation. The focused
frontend/training/audit/bridge validation passed 80 tests in 8.33 seconds.

Authoritative closure:

- reports/core_methods/latent_lexicon/pre_s1m1_calibration_checkpoint_20260901.md
- reports/core_methods/latent_lexicon/six_representation_gate_launch_plan_20260901.md
- configs/cloud/experiment_registry.toml

The historical reports/core_methods/latent_lexicon/full_m0_launch_plan.md is
untouched and superseded for current work.

## Five PREPARED representation cells

- core-01: IAST legacy_joined
  - run cloud_full_m0_iast_legacy_joined_p10_w8_p3
  - metrics full_m0_iast_legacy_joined_p10_w8_p3
- core-02: IAST continuous
  - run cloud_full_m0_iast_continuous_p10_w8_p3
  - metrics full_m0_iast_continuous_p10_w8_p3
- core-03: Devanagari surface_word
  - run cloud_full_m0_devanagari_surface_word_p10_w8_p3
  - metrics full_m0_devanagari_surface_word_p10_w8_p3
- core-04: Devanagari legacy_joined
  - run cloud_full_m0_devanagari_legacy_joined_p10_w8_p3
  - metrics full_m0_devanagari_legacy_joined_p10_w8_p3
- core-05: Devanagari continuous
  - run cloud_full_m0_devanagari_continuous_p10_w8_p3
  - metrics full_m0_devanagari_continuous_p10_w8_p3

All five registry rows are PREPARED, not RUNNING, LAUNCHED, or DONE. Core-06
is excluded and must remain unused.

## Human-only next action

Codex has no permission to contact a VM. Do not run bridge status,
deploy-code, push-inputs, verify-remote, SSH, nohup, monitor, collection,
pull-results, or remote audit commands.

The human operator will:

1. deploy the exact published local HEAD reported in the delivery handoff as
   REPRESENTATION_GATE_SHA to core-01 through core-05;
2. run verify-remote on each selected host;
3. execute the five exact detached commands in the dated launch plan;
4. perform its immediate PID/process-sample check on each host;
5. wait for natural completion and then run the documented final audit.

Direct GitHub access may be unreliable on mainland cloud hosts. The preferred
fallback is local git bundle plus SSH transfer and an exact-HEAD fast-forward.

## Deferred work

Do not yet implement or run baseline/tokenizer comparison, common evaluation,
S1M1 specification freeze, aggregation, or paper-facing tables/figures. Resume
from manually completed unrestricted representation artifacts after the human
operator returns; do not rerun or infer remote state.

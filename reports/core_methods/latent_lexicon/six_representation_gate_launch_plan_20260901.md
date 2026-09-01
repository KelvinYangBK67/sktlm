# Six-representation gate launch plan (2026-09-01)

Status: **PREPARED FOR MANUAL EXECUTION; NOTHING LAUNCHED BY CODEX**.

IAST + surface_word is already supplied by the accepted unrestricted
replicas. This plan assigns the five remaining unrestricted M0 cells at the
frozen production setting: 8 workers, 3 passes, no vocabulary budget, and no
document or line limits. Core-06 is excluded.

| Host | Script | Condition | Run ID | Metrics ID | State |
|---|---|---|---|---|---|
| core-01 | iast | legacy_joined | cloud_full_m0_iast_legacy_joined_p10_w8_p3 | full_m0_iast_legacy_joined_p10_w8_p3 | PREPARED |
| core-02 | iast | continuous | cloud_full_m0_iast_continuous_p10_w8_p3 | full_m0_iast_continuous_p10_w8_p3 | PREPARED |
| core-03 | devanagari | surface_word | cloud_full_m0_devanagari_surface_word_p10_w8_p3 | full_m0_devanagari_surface_word_p10_w8_p3 | PREPARED |
| core-04 | devanagari | legacy_joined | cloud_full_m0_devanagari_legacy_joined_p10_w8_p3 | full_m0_devanagari_legacy_joined_p10_w8_p3 | PREPARED |
| core-05 | devanagari | continuous | cloud_full_m0_devanagari_continuous_p10_w8_p3 | full_m0_devanagari_continuous_p10_w8_p3 | PREPARED |

The human operator must use the exact published branch HEAD reported in the
delivery handoff as REPRESENTATION_GATE_SHA. The trainer provenance captures
that actual commit. Preparation does not imply RUNNING, LAUNCHED, or DONE.

## Local code deployment and input verification

From a clean published local checkout, run the following once per selected
profile, substituting core-01 through core-05. Do not use core-06:

    python3 scripts/cloud/sktlm_bridge.py deploy-code --host-profile core-01

Mainland cloud hosts may have unreliable direct GitHub access. The preferred
fallback is a local git bundle transferred over SSH and an exact-HEAD
fast-forward on the host; never copy a working tree or weaken the
fast-forward/exact-HEAD requirement.

After deployment, run the authoritative input check once per profile:

    python3 scripts/cloud/sktlm_bridge.py verify-remote --host-profile core-01 --json

Only proceed on a profile when deploy-code and verify-remote both succeed and
the remote HEAD equals REPRESENTATION_GATE_SHA.

## Exact detached launch commands

Run exactly one block in the repository root on the named host. Each block
refuses any pre-existing run or metrics path, creates only its unique metrics
directory, launches detached, and records the wrapper PID. The deliberate
absence of vocab-budget, document-list, max-documents, and max-lines options
means unrestricted full-corpus training.

### core-01: IAST + legacy_joined

    if [ -e artifacts/latent_benchmarks/cloud_full_m0_iast_legacy_joined_p10_w8_p3 ] || [ -e artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3 ]; then echo 'REFUSING: target exists' >&2; exit 1; fi
    mkdir -p artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3
    nohup ./.venv/bin/python scripts/cloud/run_with_metrics.py --output-dir artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3 -- ./.venv/bin/python -m sktlm.experiments.training.latent_lexicon \
      --manifest data/manifests/representations.csv \
      --output-root artifacts/latent_benchmarks \
      --run-id cloud_full_m0_iast_legacy_joined_p10_w8_p3 \
      --script iast --condition legacy_joined --passes 3 --workers 8 \
      --lexical-alpha 0.1 --complexity-weight 0.5 --complexity-tau 1.0 \
      --whitespace-merge-penalty 8.0 --max-internal-matches 512 \
      --max-segment-tokens 128 --lexicon-cache-size 100000 --flush-types 50000 \
      --analysis-top-k 8 --usage-posterior-threshold 0.01 \
      --high-confidence-threshold 0.8 --low-count-threshold 1.0 \
      --seed 0 --equivalence-diagnostics \
      > artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3/launch.log 2>&1 < /dev/null &
    printf '%s\n' $! > artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3/launch.pid

Immediate verification on core-01:

    sleep 2; pid=$(cat artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3/launch.pid) && kill -0 $pid && test -s artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3/process_tree_samples.csv && tail -n 1 artifacts/cloud_metrics/full_m0_iast_legacy_joined_p10_w8_p3/process_tree_samples.csv

### core-02: IAST + continuous

    if [ -e artifacts/latent_benchmarks/cloud_full_m0_iast_continuous_p10_w8_p3 ] || [ -e artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3 ]; then echo 'REFUSING: target exists' >&2; exit 1; fi
    mkdir -p artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3
    nohup ./.venv/bin/python scripts/cloud/run_with_metrics.py --output-dir artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3 -- ./.venv/bin/python -m sktlm.experiments.training.latent_lexicon \
      --manifest data/manifests/representations.csv \
      --output-root artifacts/latent_benchmarks \
      --run-id cloud_full_m0_iast_continuous_p10_w8_p3 \
      --script iast --condition continuous --passes 3 --workers 8 \
      --lexical-alpha 0.1 --complexity-weight 0.5 --complexity-tau 1.0 \
      --whitespace-merge-penalty 8.0 --max-internal-matches 512 \
      --max-segment-tokens 128 --lexicon-cache-size 100000 --flush-types 50000 \
      --analysis-top-k 8 --usage-posterior-threshold 0.01 \
      --high-confidence-threshold 0.8 --low-count-threshold 1.0 \
      --seed 0 --equivalence-diagnostics \
      > artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3/launch.log 2>&1 < /dev/null &
    printf '%s\n' $! > artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3/launch.pid

Immediate verification on core-02:

    sleep 2; pid=$(cat artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3/launch.pid) && kill -0 $pid && test -s artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3/process_tree_samples.csv && tail -n 1 artifacts/cloud_metrics/full_m0_iast_continuous_p10_w8_p3/process_tree_samples.csv

### core-03: Devanagari + surface_word

    if [ -e artifacts/latent_benchmarks/cloud_full_m0_devanagari_surface_word_p10_w8_p3 ] || [ -e artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3 ]; then echo 'REFUSING: target exists' >&2; exit 1; fi
    mkdir -p artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3
    nohup ./.venv/bin/python scripts/cloud/run_with_metrics.py --output-dir artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3 -- ./.venv/bin/python -m sktlm.experiments.training.latent_lexicon \
      --manifest data/manifests/representations.csv \
      --output-root artifacts/latent_benchmarks \
      --run-id cloud_full_m0_devanagari_surface_word_p10_w8_p3 \
      --script devanagari --condition surface_word --passes 3 --workers 8 \
      --lexical-alpha 0.1 --complexity-weight 0.5 --complexity-tau 1.0 \
      --whitespace-merge-penalty 8.0 --max-internal-matches 512 \
      --max-segment-tokens 128 --lexicon-cache-size 100000 --flush-types 50000 \
      --analysis-top-k 8 --usage-posterior-threshold 0.01 \
      --high-confidence-threshold 0.8 --low-count-threshold 1.0 \
      --seed 0 --equivalence-diagnostics \
      > artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3/launch.log 2>&1 < /dev/null &
    printf '%s\n' $! > artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3/launch.pid

Immediate verification on core-03:

    sleep 2; pid=$(cat artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3/launch.pid) && kill -0 $pid && test -s artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3/process_tree_samples.csv && tail -n 1 artifacts/cloud_metrics/full_m0_devanagari_surface_word_p10_w8_p3/process_tree_samples.csv

### core-04: Devanagari + legacy_joined

    if [ -e artifacts/latent_benchmarks/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3 ] || [ -e artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3 ]; then echo 'REFUSING: target exists' >&2; exit 1; fi
    mkdir -p artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3
    nohup ./.venv/bin/python scripts/cloud/run_with_metrics.py --output-dir artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3 -- ./.venv/bin/python -m sktlm.experiments.training.latent_lexicon \
      --manifest data/manifests/representations.csv \
      --output-root artifacts/latent_benchmarks \
      --run-id cloud_full_m0_devanagari_legacy_joined_p10_w8_p3 \
      --script devanagari --condition legacy_joined --passes 3 --workers 8 \
      --lexical-alpha 0.1 --complexity-weight 0.5 --complexity-tau 1.0 \
      --whitespace-merge-penalty 8.0 --max-internal-matches 512 \
      --max-segment-tokens 128 --lexicon-cache-size 100000 --flush-types 50000 \
      --analysis-top-k 8 --usage-posterior-threshold 0.01 \
      --high-confidence-threshold 0.8 --low-count-threshold 1.0 \
      --seed 0 --equivalence-diagnostics \
      > artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3/launch.log 2>&1 < /dev/null &
    printf '%s\n' $! > artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3/launch.pid

Immediate verification on core-04:

    sleep 2; pid=$(cat artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3/launch.pid) && kill -0 $pid && test -s artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3/process_tree_samples.csv && tail -n 1 artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_p10_w8_p3/process_tree_samples.csv

### core-05: Devanagari + continuous

    if [ -e artifacts/latent_benchmarks/cloud_full_m0_devanagari_continuous_p10_w8_p3 ] || [ -e artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3 ]; then echo 'REFUSING: target exists' >&2; exit 1; fi
    mkdir -p artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3
    nohup ./.venv/bin/python scripts/cloud/run_with_metrics.py --output-dir artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3 -- ./.venv/bin/python -m sktlm.experiments.training.latent_lexicon \
      --manifest data/manifests/representations.csv \
      --output-root artifacts/latent_benchmarks \
      --run-id cloud_full_m0_devanagari_continuous_p10_w8_p3 \
      --script devanagari --condition continuous --passes 3 --workers 8 \
      --lexical-alpha 0.1 --complexity-weight 0.5 --complexity-tau 1.0 \
      --whitespace-merge-penalty 8.0 --max-internal-matches 512 \
      --max-segment-tokens 128 --lexicon-cache-size 100000 --flush-types 50000 \
      --analysis-top-k 8 --usage-posterior-threshold 0.01 \
      --high-confidence-threshold 0.8 --low-count-threshold 1.0 \
      --seed 0 --equivalence-diagnostics \
      > artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3/launch.log 2>&1 < /dev/null &
    printf '%s\n' $! > artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3/launch.pid

Immediate verification on core-05:

    sleep 2; pid=$(cat artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3/launch.pid) && kill -0 $pid && test -s artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3/process_tree_samples.csv && tail -n 1 artifacts/cloud_metrics/full_m0_devanagari_continuous_p10_w8_p3/process_tree_samples.csv

## Lightweight status and final audit

For a single assigned host, the human operator may read the latest sample:

    tail -n 1 artifacts/cloud_metrics/METRICS_ID/process_tree_samples.csv

After natural completion, confirm that process_tree_summary.json reports
return_code 0, then run:

    ./.venv/bin/python scripts/cloud/audit_latent_run.py \
      artifacts/latent_benchmarks/RUN_ID \
      --metrics-dir artifacts/cloud_metrics/METRICS_ID \
      --output artifacts/cloud_metrics/METRICS_ID/remote_audit.json

Replace RUN_ID and METRICS_ID with one exact pair from the table. A valid
audit exits 0 and writes JSON with valid=true. Do not collect, compare, or
mark a registry row DONE until the corresponding job has completed naturally
and this audit succeeds.

No command in this document was executed while preparing this plan.

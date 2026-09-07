# Full-M0 baseline VM runbook

No command in this runbook was executed during pre-production closure. Stages 1
and 2 require explicit human authorization; the queue command only prints jobs.

## Stage 0 — preflight and non-launching checks

On the prepared CUDA host, use the exact pushed branch head and a fresh
environment:

```bash
git fetch origin exp/m0-baseline-validation
git switch exp/m0-baseline-validation
git pull --ff-only origin exp/m0-baseline-validation
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/exp/m0-baseline-validation)"
test ! -e .venv
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python -m pip check
python -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

Provision the already generated and formally validated M0-prime payload at
exactly these ignored paths; do not regenerate it on the baseline branch and do
not substitute a newly hashed manifest:

```text
data/derived/m0_prime/iast/continuous/
artifacts/m0_prime/m0_prime_iast_continuous_v1/manifest.csv
artifacts/m0_prime/m0_prime_iast_continuous_v1/config.snapshot.json
artifacts/m0_prime/m0_prime_iast_continuous_v1/generation.json
artifacts/m0_prime/m0_prime_iast_continuous_v1/validation.json
artifacts/m0_prime/m0_prime_iast_continuous_v1/SHA256SUMS
```

The manifest must hash to
`3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`.
The generic bridge may provision these inputs from a host that already holds
the formal payload:

```bash
python scripts/cloud/sktlm_bridge.py \
  --contract configs/cloud/full_m0_baselines.yaml \
  validate-contract
python scripts/cloud/sktlm_bridge.py \
  --contract configs/cloud/full_m0_baselines.yaml \
  --config .sktlm-bridge.toml \
  --host-profile baseline-01 \
  push-inputs
```

Run every fail-closed input and planning check:

```bash
sktlm-validate-gretil-freeze
sktlm-validate-representations
python scripts/cloud/verify_full_m0_inputs.py \
  --config configs/experiments/baselines/full_m0_matrix.yaml
python -m sktlm.experiments.baselines.full_m0 \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --check-inputs
python -m sktlm.experiments.baselines.production \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --output /tmp/full-m0-production-queue.json
python scripts/repro/capture_environment.py \
  --output-dir /tmp/full-m0-preflight-environment
```

The plan must report 22 historical M0 cells, four historical retired cells, 18
unchanged M0 production cells, four M0-prime replacements, 22 runnable cells,
240 documents, and 1,440 catalog files. Verify that the queue contains no
original M0 IAST-continuous ID:

```bash
python - <<'PY'
import json
from pathlib import Path
queue = json.loads(Path('/tmp/full-m0-production-queue.json').read_text())
retired = {
    'bpe__iast__continuous',
    'unigram__iast__continuous',
    'unicode_codepoint__iast__continuous',
    'surface_lattice__iast__continuous',
}
ids = {job['condition_id'] for job in queue['jobs']}
assert queue['launches_jobs'] is False
assert queue['scheduled_job_count'] == 22
assert not ids & retired
print('FULL_M0_QUEUE_VALID')
PY
```

Run the four M0-prime bounded tokenizer smokes in a separate artifact root:

```bash
test ! -e artifacts/baselines/full_m0_smoke
for cell in \
  bpe__iast_m0_prime__continuous \
  unigram__iast_m0_prime__continuous \
  unicode_codepoint__iast_m0_prime__continuous \
  surface_lattice__iast_m0_prime__continuous
do
  python -m sktlm.experiments.baselines.runner \
    --config configs/experiments/baselines/full_m0_matrix.yaml \
    --condition "$cell" \
    --artifact-root artifacts/baselines/full_m0_smoke \
    --max-train-segments 5000 \
    --max-eval-segments 3 \
    --tokenizer-only
done
```

Re-run bridge contract validation after operational configuration is installed.
Stage 0 must stop on any missing M0-prime file, manifest/hash mismatch, dirty
Git state, failed `pip check`, missing CUDA, or non-22 queue.

## Stage 1 — first-cell gate (explicit authorization required)

Run only the predeclared low-risk first cell:

```bash
python -m sktlm.experiments.baselines.runner \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --condition unicode_codepoint__devanagari__surface_word \
  --production
python -m sktlm.experiments.baselines.audit \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --condition unicode_codepoint__devanagari__surface_word \
  --artifact-dir artifacts/baselines/full_m0/unicode_codepoint__devanagari__surface_word/seed_0 \
  --output artifacts/baselines/full_m0_first_cell_audit.json
```

Continue only when the audit classification is exactly `pass`. Preserve and
quarantine a failed or partial bundle outside the formal root; never overwrite
it and never weaken the validator.

## Stage 2 — remaining 21 cells (separate explicit authorization required)

The tracked queue is a non-launching snapshot. After Stage 1 passes, manually
execute the remaining 21 `command_argv` entries from
`/tmp/full-m0-production-queue.json`, one independently initialized cell at a
time. Do not re-run the first cell and do not run any command containing one of
the four retired original IDs.

## Stage 3 — VM finalization

After all 22 bundles exist at one commit, seed, and environment:

```bash
python -m sktlm.experiments.baselines.aggregate \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --artifact-root artifacts/baselines/full_m0 \
  --output artifacts/baselines/full_m0_aggregate.json
python -m sktlm.analysis.baseline_adapter \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --artifact-root artifacts/baselines/full_m0 \
  --comparisons configs/analysis/full_m0_baseline_comparisons.yaml \
  --output-dir artifacts/analysis/full_m0_baselines
python -m sktlm.experiments.baselines.production \
  --config configs/experiments/baselines/full_m0_matrix.yaml \
  --output artifacts/baselines/full_m0_queue_snapshot.json
test ! -e artifacts/baselines/full_m0_SHA256SUMS
find artifacts/baselines/full_m0 -type f -print0 | sort -z | \
  xargs -0 sha256sum > artifacts/baselines/full_m0_SHA256SUMS
```

The aggregate must report 22 complete cells and the shared analysis must publish
`analysis.json`, `cells.tsv`, `comparisons.tsv`, and `summary.md`. Generate a
non-overwriting SHA-256 inventory and retain the M0-prime validation evidence
with the matrix-level artifacts.

## Stage 4 — audited result collection

Until a separately validated compact collection contract exists, collect the
full profile for every condition. For each queue condition:

```bash
python scripts/cloud/sktlm_bridge.py \
  --contract configs/cloud/full_m0_baselines.yaml \
  --config .sktlm-bridge.toml \
  --host-profile baseline-01 \
  collect \
  --condition unicode_codepoint__devanagari__surface_word \
  --profile full
```

Repeat with each of the other 21 condition IDs and its assigned host profile.
The bridge runs the thin baseline audit remotely, resumes only an exact partial
collection identity, verifies downloaded sizes/hashes against the remote audit,
and writes a redacted transfer receipt. Retain every file declared by each
`COMPLETED.json`, the 22-cell aggregate, shared-analysis outputs, queue snapshot,
host registry, receipts, checksum inventory, and compact M0-prime validation
evidence.

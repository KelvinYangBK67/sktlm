# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`

The formal local P10 medium scaling checkpoint is complete.

The clean 8-worker run is:

`artifacts/latent_benchmarks/medium_optimized_p10_w8_p3_rerun1/`

It completed 3 passes plus inspection at provenance commit `25998f0`. The
checkpoint, metrics consistency, zero-overflow, shard/tmp cleanup, and SQLite
audits pass. Training and inspection count tables match the 4-worker P10 row
counts and totals. The six canonical scientific artifacts are byte-for-byte
identical to `medium_optimized_p10_w4_p3` by streaming SHA-256.

The earlier
`artifacts/latent_benchmarks/medium_optimized_p10_w8_p3_interrupted/` was
manually stopped with Ctrl+C. It has zero completed passes, no benchmark
metrics, and partial shards. It is crash-diagnostic evidence only and is
excluded from performance comparisons.

Local scaling conclusion:

- 4-worker wall: 1,216.915 s;
- 8-worker wall: 1,526.624 s (+25.45%);
- training wall: +13.33%;
- inspection wall: +27.05%;
- benchmark total CPU: +23.81%;
- throughput: -20.29%.

Four workers are the local production sweet spot. Do not run local 12/16-worker
benchmarks. The current local full-M₀ projection remains 4.60 hours by
characters / 4.06 hours by documents. Do not start full M₀.

Durable reports:

- `reports/core_methods/latent_lexicon/medium_scaling_p10.md`;
- `reports/core_methods/latent_lexicon/stage01_checkpoint_20260831.md`;
- `reports/core_methods/latent_lexicon/performance_optimization_v1.md`;
- `reports/core_methods/latent_lexicon/cloud_deployment_ubuntu22.md`.

The provisional remote commits `99df410` and `921bfe1` were audited and
retained by fast-forward. Their promotion policy and checkpoint structure are
useful; the outdated “8-worker still running” statement was corrected by the
follow-up checkpoint commit rather than rewriting public history.

Cloud tooling is under `scripts/cloud/`:

- `host_sanity.sh` — read-only host/disk inventory;
- `bootstrap_repo.sh` — exact-HEAD, data-disk, Python 3.11, dependency bootstrap;
- `verify_inputs.py` — existing-validator-based M₀/representations/rules audit;
- `run_with_metrics.py` — Linux process-tree RSS/CPU/I/O sampler;
- `audit_latent_run.py` — bounded-memory completion/SQLite/hash auditor.

Read `AGENTS.md`, `.codex/PROJECT_STATE.md`, `.codex/DECISIONS.md`, and the
reports above before continuing. Do not alter frozen M₀, its manifest, the
`m0` tag, representations, or the 1,218-rule inventory.

## Next task: cloud host read-only sanity

Target: Ubuntu 22.04, 16 vCPU, 32 GB RAM, 80 GB system SSD, 300 GB fast data
SSD, single node.

The user should run this first command manually on the VM:

```bash
mkdir -p "$HOME/sktlm-cloud-audit"
{
  echo "timestamp_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  hostname
  uname -a
  lscpu
  free -h
  lsblk -e 7 -o NAME,PATH,SIZE,TYPE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
  df -hT
  findmnt -D
  git --version
  command -v python3.11 >/dev/null && python3.11 --version || echo "python3.11: MISSING"
  command -v iostat >/dev/null && iostat -V || echo "iostat: MISSING"
} 2>&1 | tee "$HOME/sktlm-cloud-audit/host_sanity.txt"
```

Expected output:

`$HOME/sktlm-cloud-audit/host_sanity.txt`

Completion signal: the shell command exits and the file includes CPU, memory,
block-device filesystem/UUID/mountpoint data, filesystem capacity, and tool
availability. No long process is involved.

Return that file/output before any mount, `fstab`, formatting, repository
bootstrap, or benchmark action. In particular, do not run `mkfs` until the exact
300 GB device/partition is reviewed and confirmed empty.

After disk review, follow `cloud_deployment_ubuntu22.md` in order: mount the
data disk, clone/fetch and verify the exact handoff HEAD, bootstrap Python 3.11,
transfer/verify frozen inputs, run smoke, then manually run cloud medium at 4
workers. Every medium run remains a user-managed >5-minute command.

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

## Cloud host state

The user has completed the read-only host audit and deliberate data-disk setup:

- Ubuntu 22.04.4 LTS, 16 vCPU, approximately 32 GB RAM;
- `/dev/vda` is the 80 GB system disk;
- `/dev/vdb1` is ext4, labelled `sktlm-data`, and mounted at
  `/mnt/sktlm-data`;
- `/etc/fstab` verification passed without warnings;
- `df` reports approximately 295 GB total / 280 GB available;
- iostat/sysstat is present;
- Git and Python 3.11 are missing;
- no repository bootstrap has started.

Do not partition, format, or remount the data disk. Do not launch any medium or
full benchmark.

## Current task: add the deterministic local/cloud bridge

The local preflight audit found and fixed these deployment-only issues for user
review:

- `host_sanity.sh` now reports `git: MISSING` without aborting;
- `verify_inputs.py --help` now displays help, and unexpected arguments fail;
- `bootstrap_repo.sh` checks Git/Python before layout changes, requires the
  supplied data path itself to be the non-root mount point, and explicitly
  refreshes the remote-tracking branch used by its fast-forward merge.

The preflight fixes have been reviewed and validated. The next implementation
is a deterministic `sktlm_bridge.py` control plane around Git, SSH/rsync,
authoritative input/audit validation, selective result collection, and
machine-readable receipts. It must not make scientific decisions, provide an
arbitrary remote shell, install packages, or launch benchmarks.

Do not bootstrap the VM until the bridge/preflight commits are pushed and their
new full HEAD is recorded. The next independently safe VM prerequisite command
remains:

```bash
sudo apt-get update
sudo apt-get install --yes git
git --version
```

Install Python 3.11 and its venv support only through a user-approved source;
Ubuntu 22.04 source selection is intentionally not automated by the repository.
Verify `python3.11 --version` before clone/bootstrap. The bootstrap dependency
installation itself may exceed five minutes and remains user-managed.

Then follow `cloud_deployment_ubuntu22.md`: clone the approved HEAD, bootstrap,
transfer/verify the frozen inputs, run the short smoke gate, and only then run
cloud medium at 4 workers manually.

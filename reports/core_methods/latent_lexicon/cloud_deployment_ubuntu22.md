# Ubuntu 22.04 cloud deployment and scaling gate

Target host:

- single node, Ubuntu 22.04, CPU only;
- 16 vCPU, 32 GB RAM;
- 80 GB system SSD;
- 300 GB fast data SSD;
- branch `exp/m0-core-methods`.

The local host's 4-worker sweet spot is not assumed to transfer to this host.
Cloud worker scaling starts again at 4, then 8, and reaches 12/16 only if the
preceding result is beneficial and memory-safe. No full-M₀ run may start
automatically.

## Current host checkpoint

The user has manually established the following state on the target host:

- Ubuntu 22.04.4 LTS, 16 vCPU, and approximately 32 GB RAM;
- `/dev/vda` is the 80 GB system disk;
- `/dev/vdb1` is the deliberately created ext4 data partition, labelled
  `sktlm-data`, mounted at `/mnt/sktlm-data`;
- `/etc/fstab` verification passed, and the data filesystem reports about
  295 GB total / 280 GB available;
- `iostat`/`sysstat` is installed;
- Git and Python 3.11 are not yet installed;
- no repository clone/bootstrap has been performed.

Do not repeat partitioning, formatting, or mount setup on this host. The next
host-level prerequisites are Git and an approved Python 3.11 installation with
venv support.

## Deterministic local/cloud bridge

The deployment boundary is now explicit:

- Git/GitHub is authoritative for code, configs, reports, scripts, manifests,
  and the fixed rule inventory;
- rsync over SSH transfers only non-Git scientific input/result bytes;
- `scripts/cloud/sktlm_bridge.py` is the deterministic control plane that
  validates provenance, invokes those system tools, and writes JSON receipts;
- the human operator remains responsible for packages, disks/mounts,
  bootstrap waiting, destructive infrastructure decisions, and every
  benchmark command.

The bridge is not an agent and does not make scientific decisions. It has no
arbitrary remote-shell command, package installer, benchmark launcher, Git
push, data deletion, or report-commit operation.

Copy the tracked example to the gitignored local configuration and edit only
operational values:

```bash
cp configs/cloud/bridge.example.toml .sktlm-bridge.toml
```

Never place a password, token, private-key content, or credential-bearing URL
in that file. CLI overrides are accepted before the subcommand. From WSL/Linux:

```bash
python3 scripts/cloud/sktlm_bridge.py status --json
python3 scripts/cloud/sktlm_bridge.py deploy-code
python3 scripts/cloud/sktlm_bridge.py push-inputs
python3 scripts/cloud/sktlm_bridge.py verify-remote --json
# The user manually runs and waits for smoke/medium here.
python3 scripts/cloud/sktlm_bridge.py collect <RUN_ID>
python3 scripts/cloud/sktlm_bridge.py pull-results <RUN_ID> --profile scientific
```

Native Windows can use read-only status and Git/SSH code deployment when the
system tools are available. All rsync transfer commands deliberately refuse to
run under native Windows; run them inside WSL/Linux so path and rsync semantics
are unambiguous. No weaker copy fallback is provided.

Every bridge sync/mutating operation writes a redacted machine-readable receipt
under `artifacts/cloud_transfers/`. Receipts record local/remote HEADs, logical
paths, return codes, file/byte information, validation results, warnings, and
failures. They never contain key contents or configured identity-file paths.

## 1. Read-only host and disk discovery (completed)

The initial manual discovery is complete. After the repository is cloned,
`scripts/cloud/host_sanity.sh` can reproduce the read-only inventory. It records
`lscpu`, `free -h`, `lsblk`, `df -hT`, and `findmnt` without changing the
machine. Missing Git, Python 3.11, or iostat is reported as `MISSING` rather
than aborting the inventory.

Do not infer the 300 GB device name from a provider convention. Confirm size,
model/serial, filesystem type, UUID, and current mountpoints from the output.

## 2. Data-disk decision (completed on the current host)

The commands below are retained as the reusable deployment procedure. They
must not be repeated on the current host merely because they appear here.

If the confirmed data filesystem already exists, mount by UUID:

```bash
sudo install -d -m 0755 /mnt/sktlm-data
sudo mount -U '<CONFIRMED_UUID>' /mnt/sktlm-data
findmnt /mnt/sktlm-data
df -hT /mnt/sktlm-data
```

Only after that succeeds should an `/etc/fstab` entry be added:

```text
UUID=<CONFIRMED_UUID> /mnt/sktlm-data ext4 defaults,nofail 0 2
```

Then verify it with `sudo mount -a` and `findmnt /mnt/sktlm-data`.

If the 300 GB device is blank, stop after read-only confirmation:

```bash
sudo wipefs -n /dev/<CONFIRMED_DATA_DEVICE>
sudo fdisk -l /dev/<CONFIRMED_DATA_DEVICE>
```

Formatting is destructive. Do not run `mkfs` until the exact device/partition
has been reviewed and confirmed to contain no required data. The eventual
manual operation, only after that confirmation, is:

```bash
sudo mkfs.ext4 -L sktlm-data /dev/<CONFIRMED_DATA_PARTITION>
```

Give the deployment user ownership after the filesystem is mounted:

```bash
sudo install -d -o "$USER" -g "$USER" /mnt/sktlm-data/sktlm
```

## 3. Repository bootstrap

On the current fresh host, install Git from the approved Ubuntu package source
and install Python 3.11 plus its venv support from an approved source. Verify
both before cloning:

```bash
git --version
python3.11 --version
python3.11 -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version'
```

The bridge status command reports either tool as `MISSING`; `deploy-code` stops
precisely when remote Git is absent. The bootstrap exits before changing the
repository/data layout when Git or Python 3.11 is absent. Neither tool installs
packages.

After the final bridge commit is pushed, the preferred code path is local
GitHub-to-VM deployment from WSL/Linux:

```bash
python3 scripts/cloud/sktlm_bridge.py deploy-code
```

It requires a clean local tree, requires local HEAD to equal the published
branch HEAD, refuses a dirty remote repository, performs only clone/fetch and
fast-forward operations, and verifies the exact deployed SHA. It never copies
the local source tree or runs `git push` from the VM.

Manual clone remains a transparent fallback. Clone onto the system disk or
another ordinary workspace; large data, venv cache, artifacts, and benchmark
scratch are linked to the data disk by the bootstrap script.

```bash
git clone --branch exp/m0-core-methods --single-branch \
  https://github.com/KelvinYangBK67/sktlm.git
cd sktlm
git status --short --branch
bash scripts/cloud/bootstrap_repo.sh '<EXPECTED_HEAD>' /mnt/sktlm-data
```

`bootstrap_repo.sh`:

- refuses a dirty tree or non-fast-forward update;
- verifies exact HEAD;
- requires the supplied data path to be the actual non-root mount point;
- requires at least 100 GiB free;
- links `artifacts/`, `data/canonical/`, `data/representations/`, and the
  Python 3.11 venv to the data disk;
- installs `.[test]` and runs `pip check`;
- never partitions, formats, or mounts a device.

Install Python 3.11 and its venv support through the host's approved package
source before running the script. The bootstrap deliberately fails rather than
adding an unreviewed package repository.

Dependency installation (especially PyTorch) may exceed five minutes. The user
must run/wait for bootstrap manually. Its success signal is
`bootstrap_complete`, followed by the exact HEAD and resolved data mount.

## 4. Transfer and validate frozen inputs

After exact code deployment and manual bootstrap, run from WSL/Linux:

```bash
python3 scripts/cloud/sktlm_bridge.py push-inputs
```

The command first invokes the local authoritative validator, verifies local and
remote repository HEAD equality, rechecks that `/mnt/sktlm-data` is the actual
non-root mount for every remote rsync process, verifies that resolved
destination paths remain below the data-disk root, and then transfers:

- `/mnt/sktlm-data/sktlm/data/canonical/gretil_iast/`;
- `/mnt/sktlm-data/sktlm/data/representations/`.

It uses resumable rsync partials, preserves bytes, and never supplies
`--delete`. It does not transfer tracked manifests/rules; those come from the
exact Git commit. It does not regenerate or mutate M₀. By default it then runs
the remote authoritative validator. The explicit standalone form is:

```bash
python3 scripts/cloud/sktlm_bridge.py verify-remote --json
```

The command reuses the repository's freeze and representation validators and
must report:

- 240 canonical documents;
- 57,588,079 characters and 69,864,279 bytes;
- freeze ID `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`;
- 1,440 representation files;
- 1,218 external-sandhi rules;
- `valid: true`.

## 5. Short smoke gate

Before a medium job, run a short 4-worker smoke through the resource wrapper:

```bash
./.venv/bin/python scripts/cloud/run_with_metrics.py \
  --output-dir artifacts/cloud_metrics/smoke_p10_w4_p3 \
  -- \
  ./.venv/bin/python -m sktlm.latent.benchmark \
  --benchmark smoke \
  --run-id cloud_smoke_p10_w4_p3 \
  --passes 3 \
  --workers 4

./.venv/bin/python scripts/cloud/audit_latent_run.py \
  artifacts/latent_benchmarks/cloud_smoke_p10_w4_p3
```

The wrapper records one-second process-tree samples, simultaneous aggregate RSS,
sampled process-tree CPU, and process I/O. The benchmark's own
`peak_rss_bytes` remains main-process-only.

## 6. Manual medium scaling sequence

Each medium command exceeds five minutes and must be launched/waited for by the
user. Run only one worker count at a time.

First, 4 workers:

```bash
./.venv/bin/python scripts/cloud/run_with_metrics.py \
  --output-dir artifacts/cloud_metrics/medium_p10_w4_p3 \
  -- \
  ./.venv/bin/python -m sktlm.latent.benchmark \
  --benchmark medium \
  --run-id cloud_medium_p10_w4_p3 \
  --passes 3 \
  --workers 4
```

After natural completion:

```bash
./.venv/bin/python scripts/cloud/audit_latent_run.py \
  artifacts/latent_benchmarks/cloud_medium_p10_w4_p3 \
  | tee artifacts/cloud_metrics/medium_p10_w4_p3/audit.json
```

Compare the six emitted hashes with
`medium_scaling_p10.md`. Any scientific mismatch or integrity failure closes
the deployment gate until diagnosed.

Only after the 4-worker audit passes, run the analogous 8-worker job:

```bash
./.venv/bin/python scripts/cloud/run_with_metrics.py \
  --output-dir artifacts/cloud_metrics/medium_p10_w8_p3 \
  -- \
  ./.venv/bin/python -m sktlm.latent.benchmark \
  --benchmark medium \
  --run-id cloud_medium_p10_w8_p3 \
  --passes 3 \
  --workers 8
```

Test 12 workers only if 8 workers gives a material wall improvement, scientific
hashes remain exact, and peak process-tree RSS/storage are safe. Test 16 only if
12 improves again. Do not batch all worker counts into one unattended command.

For every run retain:

- benchmark and phase metrics;
- `process_tree_samples.csv` and `process_tree_summary.json`;
- CPU capacity/utilization and process I/O;
- checkpoint, SQLite, overflow, and residue audit;
- the six scientific hashes;
- data-disk free space before and after.

If `iostat` is available, additionally record device-level latency/utilization
during the run; process I/O bytes alone do not expose storage queueing.

## 7. Result collection

`pull-results` is selective and defaults to `report`:

- `report`: small benchmark/config/provenance/audit/inspection/resource files;
- `scientific`: report files plus the canonical scientific exports;
- `full`: the complete benchmark and metrics directories, explicitly including
  `learner.sqlite` and any other large run artifacts.

Normal `scientific` collection does not include `learner.sqlite`. A new local
collection is created under `artifacts/cloud_collected/<RUN_ID>/`; an existing
destination is refused rather than silently overwritten. Remote files are
never deleted.

`collect <RUN_ID>` runs the fixed remote audit command, pulls the report
profile even when that audit is invalid, compares any downloaded files covered
by remote audit hashes, writes `remote_audit.json`, and records which scientific
and full-profile artifacts remain remote-only. It never commits, pushes,
launches another job, or removes the remote run.

## 8. Full-M₀ gate

The full command is intentionally not prepared for immediate execution.
Authorize it only after:

1. cloud 4/8 medium scientific hashes and integrity pass;
2. a worker sweet spot is measured on this host;
3. simultaneous process-tree RSS has safe headroom below 32 GB;
4. the 300 GB filesystem has credible artifact and crash-shard headroom;
5. the projected runtime is accepted;
6. a new run ID and exact command are recorded in `.codex/CURRENT_TASK.md`.

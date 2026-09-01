# Ubuntu 22.04 cloud deployment and scaling gate

Deployment template:

- equivalent Ubuntu 22.04 CPU-only nodes;
- 16 vCPU, 32 GB RAM;
- 80 GB system SSD;
- 300 GB fast data SSD;
- branch `exp/m0-core-methods`.

The local host's 4-worker sweet spot is not assumed to transfer to this host.
Cloud worker scaling starts again at 4, then 8, and reaches 12/16 only if the
preceding result is beneficial and memory-safe. No full-M₀ run may start
automatically.

This file preserves the bootstrap/deployment procedure. Current multi-host run
state and results are authoritative in `cloud_scaling_checkpoint_20260831.md`.

## Initial reference-host checkpoint (historical)

Before repository bootstrap, the user manually established the following state
on the reference host:

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

- Git commit/history is the authoritative identity for code, configs, reports,
  scripts, manifests, and the fixed rule inventory;
- GitHub is the publication and collaboration endpoint, not the required
  production transport into mainland core hosts;
- production code transport to core-01 through core-06 is a local Git bundle
  over SCP/SSH with remote bundle verification, exact-SHA checks, and a
  fast-forward-only update;
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
python3 scripts/cloud/sktlm_bridge.py push-inputs
python3 scripts/cloud/sktlm_bridge.py verify-remote --json
# The user manually runs and waits for smoke/medium here.
python3 scripts/cloud/sktlm_bridge.py collect <RUN_ID> --profile scientific
```

The bridge `deploy-code` subcommand is retained as a legacy GitHub-backed
workflow for environments with reliable direct GitHub connectivity. It is not
the production deployment path for core-01 through core-06. Native Windows can
use read-only status when the system tools are available. All rsync transfer
commands deliberately refuse to run under native Windows; run them inside
WSL/Linux so path and rsync semantics are unambiguous. No weaker copy fallback
is provided.

Every bridge sync/mutating operation writes a redacted machine-readable receipt
under `artifacts/cloud_transfers/`. Receipts record local/remote HEADs, logical
paths, return codes, file/byte information, validation results, warnings, and
failures. They never contain key contents or configured identity-file paths.

### Multi-host profiles and run assignment

The original single `[bridge]` configuration remains supported. For a fleet,
add operational overlays only to the ignored `.sktlm-bridge.toml`:

```toml
[host_profiles.core-02]
machine_id = "core-02"
host = "<LOCAL-ONLY-HOST-OR-IP>"
```

Real hosts/IPs and identity-file paths must remain in that ignored file. The
tracked `configs/cloud/experiment_registry.toml` contains logical machine/run
assignments but no addresses. Select profiles after the subcommand:

```bash
python3 scripts/cloud/sktlm_bridge.py status --host-profile core-02 --json
python3 scripts/cloud/sktlm_bridge.py collect cloud_medium_p10_w8_p3 \
  --metrics-id medium_p10_w8_p3 --host-profile core-02
```

When host profiles exist, `collect` and `pull-results` require an explicit
profile and refuse a run/profile/machine/metrics mismatch from the tracked
registry before making an SSH call. Receipts record the selected logical
profile and machine alongside the actual remote target. Machine IDs are stable;
their current benchmark roles are reassignable.

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

For core-01 through core-06, direct remote GitHub access is not reliable and
must not be the production deployment path. The fixed human-operated sequence
is:

```text
clean published local Git checkout
-> git bundle create
-> SCP/SSH transfer of that bundle
-> remote git bundle verify
-> git fetch from the bundle
-> exact fetched-SHA check
-> git merge --ff-only
-> exact remote HEAD check
```

The local checkout must be clean, on the intended branch, and at the published
commit. An existing remote checkout must also be clean. For an initial
bootstrap, clone the verified bundle onto the system disk or another ordinary
workspace; for an existing checkout, fetch the intended branch from the bundle
into a dedicated remote-tracking ref, verify that ref equals the expected
40-character SHA, then fast-forward the checked-out branch to that exact SHA.
Run `bootstrap_repo.sh` only after the exact remote HEAD is established:

```bash
cd /path/to/sktlm
git status --short --branch
test "$(git rev-parse HEAD)" = '<EXPECTED_HEAD>'
bash scripts/cloud/bootstrap_repo.sh '<EXPECTED_HEAD>' /mnt/sktlm-data
```

Never use remote `git fetch`/`git pull` from GitHub as the production path
for these hosts. Never copy a local working tree with SCP/rsync, overwrite the
remote repository, or relax the clean-tree, exact-SHA, bundle-verification, or
fast-forward-only checks. The legacy bridge `deploy-code` operation remains
available only for non-core environments with reliable GitHub connectivity.

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

`collect` and the lower-level transfer-only `pull-results` both accept
`--profile report|scientific|full` and default to `report`:

- `report`: small benchmark/config/provenance/audit/inspection/resource files;
- `scientific`: report files plus the canonical scientific exports;
- `full`: the complete benchmark and metrics directories, explicitly including
  `learner.sqlite` and any other large run artifacts.

Normal `scientific` collection does not include `learner.sqlite`. Without an
explicit output root, a new local collection is created under
`artifacts/cloud_collected/<RUN_ID>/`; an existing destination is refused rather
than silently overwritten. Remote files are never deleted.

`collect <RUN_ID>` runs the fixed remote audit first, transfers the selected
profile even when that audit is invalid, writes `remote_audit.json`, validates
all downloaded files covered by remote audit hashes, and writes the redacted
transfer receipt. Registry assignment, resumable partial-transfer identity, and
refusal-to-overwrite checks are unchanged. `pull-results` remains available for
a transfer without the audit envelope; it is not needed in addition to formal
scientific `collect`.

For a completed representation-gate cell, the one-shot human command is:

```bash
python3 scripts/cloud/sktlm_bridge.py collect <RUN_ID> \
  --metrics-id <METRICS_ID> --host-profile <HOST_PROFILE> \
  --profile scientific --output-root artifacts/post_gate/collected
```

It produces the aggregator-ready layout:

```text
artifacts/post_gate/collected/<RUN_ID>/
    benchmark/
    metrics/
    remote_audit.json
    .sktlm-collection.json
```

It never commits, pushes, launches another job, or removes the remote run.

## 8. Full-M₀ representation gate

The four IAST surface_word replicas are complete and accepted. Five additional
8-worker unrestricted cells were manually bundle-deployed at scientific
checkpoint 375178ba50bd1a1644d65525907692b31413b33d, verified, and launched
on core-01 through core-05. They are RUNNING, not complete. Core-06 remains
standby and was neither deployed nor launched.

The exact assignments, launch PIDs, common frozen-input verification values,
and immediate PID/process-sample checks are recorded in
`six_representation_gate_launch_checkpoint_20260901.md`. No early process
sample is a final metric or scientific result.

Do not poll, collect, audit, stop, restart, resume, or otherwise modify a
running job. After natural completion, the human operator must require
process_tree_summary.json return_code=0, run one final audit with valid=true,
and only then collect, compare, or mark a registry row DONE.

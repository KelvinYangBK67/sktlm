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

## 1. Read-only host and disk discovery

Before cloning, run the exact command given in `.codex/CURRENT_TASK.md` and
return its output. It records `lscpu`, `free -h`, `lsblk`, `df -hT`, and
`findmnt` without changing the machine.

Do not infer the 300 GB device name from a provider convention. Confirm size,
model/serial, filesystem type, UUID, and current mountpoints from the output.

## 2. Data-disk decision

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

Clone onto the system disk or another ordinary workspace; large data, venv
cache, artifacts, and benchmark scratch are linked to the data disk by the
bootstrap script.

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
- refuses a data path on the root/system filesystem;
- requires at least 100 GiB free;
- links `artifacts/`, `data/canonical/`, `data/representations/`, and the
  Python 3.11 venv to the data disk;
- installs `.[test]` and runs `pip check`;
- never partitions, formats, or mounts a device.

Install Python 3.11 and its venv support through the host's approved package
source before running the script. The bootstrap deliberately fails rather than
adding an unreviewed package repository.

## 4. Transfer and validate frozen inputs

Transfer the frozen trees into:

- `/mnt/sktlm-data/sktlm/data/canonical/gretil_iast/`;
- `/mnt/sktlm-data/sktlm/data/representations/`.

The tracked manifests and rule inventory come from the verified repository
commit. Do not regenerate or mutate M₀ on the cloud host. Then run:

```bash
./.venv/bin/python scripts/cloud/verify_inputs.py \
  | tee artifacts/cloud_input_verification.json
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

## 7. Full-M₀ gate

The full command is intentionally not prepared for immediate execution.
Authorize it only after:

1. cloud 4/8 medium scientific hashes and integrity pass;
2. a worker sweet spot is measured on this host;
3. simultaneous process-tree RSS has safe headroom below 32 GB;
4. the 300 GB filesystem has credible artifact and crash-shard headroom;
5. the projected runtime is accepted;
6. a new run ID and exact command are recorded in `.codex/CURRENT_TASK.md`.

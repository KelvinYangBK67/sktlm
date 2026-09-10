# S1M2 pre-VM production workflow

## Scope and frozen boundary

This workflow turns the accepted S1M2 implementation into a fail-closed VM
execution interface. It does not change the 1,218-rule grammar, legal candidate
support, scoring equations, exact inference, posterior semantics, piece limits,
or any frozen S1M1/M0 bytes.

The production universe is exactly six independently trained cells. Five use
frozen M0. IAST `continuous` uses the validated derived M0-prime manifest and
the `iast_m0_prime` frontend; original M0 IAST `continuous` is scientifically
excluded and the contract refuses to substitute it. `full-M0` means the full
frozen-corpus extent of one representation cell, not a model named M0.

The machine-readable source of truth is
`configs/production/s1m2_six_cell.json`. Its contract hash is the SHA-256 of
canonical sorted JSON as emitted by `validate-contract`. Worker count is an
engineering parameter selected by the active bundle-based Round 2.

The deployment/collection source of truth is
`configs/cloud/s1m2_prevm.yaml`. It fixes the production branch, verified
Git-bundle transport, frozen input sets, remote roots, collection profiles, and
the direct run-to-host assignments. The earlier pre-VM SHA is invalidated by
this control-plane change and must not be deployed.

## Command surface

Run every command from a clean checkout of
`exp/s1m2-reusable-pieces` at the published pre-VM SHA. Production deployment
continues to use the established verified Git-bundle workflow; do not use a
copied worktree or remote GitHub pull as the production deployment path.

The control-plane verbs map to the requested lifecycle as follows:

- prepare: `plan-round1`, `plan-round2`, `plan-final`;
- run: `run` without `--resume`;
- resume: `run --resume` (explicit only; never automatic);
- audit: `audit` and the existing `scripts/cloud/audit_latent_run.py`;
- collect: the existing `scripts/cloud/sktlm_bridge.py collect`, which resolves
  the exact tracked S1M2 planned-run identity and its assigned core host;
- summarize: historical `aggregate-round1` and active `aggregate-round2`.

All plan and result writers refuse overwrite. The runner snapshots the plan,
contract hash, complete command, runtime versions, host identity, timestamps,
and attempt/resume history. It invokes the existing exact trainer through the
existing Linux process-tree metrics wrapper and preserves the child return
code. A failed job is resumable only by an explicit `--resume` invocation.

## Cheap pre-VM checks (normally under five minutes)

```text
python -m sktlm.production.s1m2 validate-contract
python -m pytest tests/production/test_s1m2_prevm.py tests/latent/test_s1m2_benchmark_contract.py tests/pieces/test_s1m2_training.py tests/cloud/test_audit_latent_run.py tests/cloud/test_sktlm_bridge.py -q
python -m sktlm.production.s1m2 validate-bounded --output-root artifacts/s1m2_prevm_validation/pre_vm_<SHA>
python -m pytest -q
git diff --check
```

The bounded validation uses one frozen document, one line, one pass, one worker,
exact training, and exact inspection for all six cells. It must emit
`bounded_validation.json` with `cell_count=6`, `status=PASS`, and a valid
checkpoint/config/provenance/storage/scientific-artifact audit for every cell.
The machine-readable `script_neutral_production_path` gate must also compare
piece inventory, lexical diagnostics, and rule usage across each matched
IAST/Devanagari condition and pass. It is an interface check only and must not
be cited as representative timing or scientific evidence.

If any check exceeds five minutes, stop it, preserve its output, and report the
exact unfinished command as an external gate. Never replace it with a larger
benchmark.

## Frozen M0-prime v1 deployment

M0-prime v1 is a frozen historical derived representation. Its frozen paths are
retained verbatim for provenance stability. Do not move, rename, regenerate,
overwrite, or rewrite it to normalize repository layout.

Before VM execution, copy the already-frozen package verbatim so that both of
these repository-relative paths exist on the VM:

```text
data/derived/m0_prime/iast/continuous/
artifacts/m0_prime/m0_prime_iast_continuous_v1/
```

The Git repository does not carry those payloads. VM bootstrap must therefore
restore them explicitly alongside the other frozen M0 inputs, then run
`python -m sktlm.production.s1m2 validate-contract` before preparing Round 1.
A missing or hash-mismatched frozen manifest is a hard preflight failure.

## Six-host VM operator sequence

Round 1 used and Round 2 uses six distinct physical core VMs. This engineering
assignment is accepted from the S1M1 host-equivalence evidence; it does not
change the scientific contract. Copy `configs/cloud/bridge.example.toml` to the
ignored `.sktlm-bridge.toml` and fill the six `core-01` through `core-06` SSH
profiles. Each profile must have the matching `machine_id`, and all six SSH
endpoints and observed `/etc/machine-id` values must be distinct.

The tracked operator script runs each phase concurrently across all six
profiles and writes a machine-readable receipt below `artifacts/`. Replace the
angle-bracket values with the final handoff identities:

```text
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml preflight --output artifacts/s1m2_vm/preflight.json
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml deploy --bundle artifacts/deployment_bundles/s1m2_prevm/<BUNDLE> --bundle-sha256 <BUNDLE_SHA256> --expected-head <PRE_VM_S1M2_SHA> --output artifacts/s1m2_vm/deploy.json
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml environment --expected-head <PRE_VM_S1M2_SHA> --output artifacts/s1m2_vm/environment.json
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml sync-inputs --expected-head <PRE_VM_S1M2_SHA> --output artifacts/s1m2_vm/input_sync.json
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml validate --expected-head <PRE_VM_S1M2_SHA> --output artifacts/s1m2_vm/remote_validate.json
python -m sktlm.production.s1m2 plan-round1 --output artifacts/s1m2_production/round1_plan.json
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml launch-round1 --plan artifacts/s1m2_production/round1_plan.json --expected-head <PRE_VM_S1M2_SHA> --output artifacts/s1m2_vm/round1_launch.json
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml collect-round1-attestations --plan artifacts/s1m2_production/round1_plan.json --expected-head <PRE_VM_S1M2_SHA> --attestation-dir artifacts/s1m2_vm/round1_attestations --output artifacts/s1m2_vm/round1_attestation_collection.json
python -m sktlm.production.s1m2 aggregate-round1 --plan artifacts/s1m2_production/round1_plan.json --attestation-dir artifacts/s1m2_vm/round1_attestations --output artifacts/s1m2_production/round1_result.json
```

`preflight` checks SSH reachability, hostname, physical/boot identity, CPU,
RAM, filesystem and free space, the data mount, repository/HEAD/clean state,
active S1M2 processes, Python environment, and M0/M0-prime presence. `deploy`
transfers the already verified bundle, verifies its SHA-256 remotely, fetches
only the contained branch, checks out the exact published SHA, and requires a
clean worktree. `environment` reuses a valid Python 3.11 venv and otherwise
creates one on the data mount, installs the repository once, and ends with
`pip check`.

`sync-inputs` first runs all authoritative validators. It skips a host whose
frozen inputs are already valid; otherwise it uses partial, append-verified,
checksum-guarded rsync and validates again. Identical frozen files are not
rewritten. `validate` then checks exact SHA/branch/clean state, physical host
separation, host role, the non-root data mount, free-space gate, Python 3.11,
`pip check`, frozen inputs, and the production contract. Every phase fails
closed if any host fails. None of these commands should be run by Codex during
pre-VM closure; they are the operator's explicit network phase.

## Round 1: VM worker scaling

Round 1 is closed as `MANUALLY_TERMINATED_AFTER_DIAGNOSTIC_CONVERGENCE`.
Its formal winner remains unresolved; workers below 12 are excluded from the
retained search, and the active candidates are 12, 16, and 24. The procedure
below is historical and must not be rerun for the active pipeline.

Round 1 is six simultaneous executions of the same M0 Devanagari-continuous
engineering worker-calibration job. Its tracked list contains 72 deterministic
stratified documents selected from the already-frozen static structure scan,
excluding both frozen stress documents. It is not a replacement or redefinition
of the representative workload. Every job uses three passes and at most 256
lines per selected document. Inputs and scientific configuration are identical;
only engineering worker count and physical host differ:

```text
core-01 -> workers=4
core-02 -> workers=8
core-03 -> workers=12
core-04 -> workers=16
core-05 -> workers=20
core-06 -> workers=24
```

Prepare the immutable plan:

```text
python -m sktlm.production.s1m2 plan-round1 --output artifacts/s1m2_production/round1_plan.json
```

Use `s1m2_vm_ops.py launch-round1` so the machine-readable plan—not a manually
copied trainer command—starts all six jobs in parallel on their assigned core
hosts. These calibration jobs are external workloads and are not Codex-local
validation. Each job must have a distinct absent run directory and metrics
identity. The launcher records PID, process start ticks, machine and boot
identity, command hash, completion marker, result path, logs, and exit-status
path for detached monitoring.

If interrupted, use the exact generated launch command with `--resume`. The
runner creates a new metrics attempt, retains earlier attempt evidence, and
never restores scores from the reconstructible topology cache.

Audit one job explicitly when needed:

```text
python -m sktlm.production.s1m2 audit --plan artifacts/s1m2_production/round1_plan.json --job-id <JOB_ID> --output artifacts/s1m2_production/<JOB_ID>.audit.json
```

After completion, run `collect-round1-attestations`. Each host executes the
formal production audit in place and writes one compact attestation containing
the plan/contract/Git/job/host identity and only the resource fields needed by
the frozen winner rule. Complete run directories, scientific artifacts,
topology, and `learner.sqlite` remain on their VM. Only the six compact JSON
files are copied locally.

Aggregate only after all six compact attestations are present:

```text
python -m sktlm.production.s1m2 aggregate-round1 --plan artifacts/s1m2_production/round1_plan.json --attestation-dir artifacts/s1m2_vm/round1_attestations --output artifacts/s1m2_production/round1_result.json
```

The aggregator excludes scientific/audit/provenance failures and memory or
storage safety failures. It ranks eligible jobs by calibration wall time.
If the fastest is at least 10% faster than the runner-up, it wins directly.
Otherwise configurations within the 10% practical-tie envelope are ordered by
lower process-tree RSS, watched storage, total CPU, canonical reducer stall,
and finally worker count. Required output fields are `ROUND1_STATUS`,
`WORKER_RANKING`, `WINNER_WORKERS`, `WINNER_REASON`, resource summaries, and
excluded-job reasons.

## Round 2: bundle worker recalibration

The former six-workload readiness stage is retired. Active Round 2 is the final
worker-selection engineering stage before full production. It holds the frozen
M0 Devanagari-continuous representative and stress workloads fixed and varies
only workers:

```text
core-01 representative w12    core-04 stress w12
core-02 representative w16    core-05 stress w16
core-03 representative w24    core-06 stress w24
```

Both subset execution plans use complete canonical `ObservedSegment` values,
never cross documents, preserve document-list order, and fix
`target_pressure=279047`, `max_segments_per_bundle=256`, and
`max_segment_tokens=128`. Materialize both plans before generating Round 2:

```text
python scripts/analysis/plan_s1m2_execution_bundles.py --document-list configs/benchmarks/s1m2_continuous_representative_documents.txt --target-pressure 279047 --max-segments-per-bundle 256 --max-segment-tokens 128 --output-dir artifacts/s1m2_execution_bundle_plans/round2_representative_tp279047
python scripts/analysis/plan_s1m2_execution_bundles.py --document-list configs/benchmarks/s1m2_continuous_stress_documents.txt --target-pressure 279047 --max-segments-per-bundle 256 --max-segment-tokens 128 --output-dir artifacts/s1m2_execution_bundle_plans/round2_stress_tp279047
python -m sktlm.production.s1m2 plan-round2 --output artifacts/s1m2_production/round2_plan.json
```

Plan generation fails closed until both materializations exist and match their
frozen document-list and bundle identities. The generated trainer commands
include `--execution-bundle-plan`, `--workers 12|16|24`, and `--passes 3`.
Launch only through `s1m2_vm_ops.py launch-round2`, which transfers and verifies
the plan and the workload-specific bundle materialization on each assigned VM.

After all six jobs finish, collect compact attestations and aggregate:

```text
python scripts/cloud/s1m2_vm_ops.py --config .sktlm-bridge.toml collect-round2-attestations --plan artifacts/s1m2_production/round2_plan.json --expected-head <PRE_VM_S1M2_SHA> --attestation-dir artifacts/s1m2_vm/round2_attestations --output artifacts/s1m2_vm/round2_attestation_collection.json
python -m sktlm.production.s1m2 aggregate-round2 --plan artifacts/s1m2_production/round2_plan.json --attestation-dir artifacts/s1m2_vm/round2_attestations --output artifacts/s1m2_production/round2_result.json
```

A worker is eligible only when both representative and stress complete their
artifact, provenance, memory, storage, resume, and zero-overflow gates. Each
workload keeps the 10% practical wall-time threshold; ties prefer lower peak
process-tree RSS, lower canonical reducer stall, then fewer workers. Agreement
between workloads yields `ROUND2_STATUS=PASS`. A decision-critical disagreement
yields `ROUND2_STATUS=NEEDS_W20_INTERPOLATION` plus prepared representative and
stress w20 job specifications; it does not run them automatically.

## Final six-cell launch plan

Only a PASS Round 2 result can generate a full plan:

```text
python -m sktlm.production.s1m2 plan-final --round2-result artifacts/s1m2_production/round2_result.json --output artifacts/s1m2_production/final_six_cell_plan.json
```

The plan assigns the six cells in contract order to logical roles core-01
through core-06, uses the resolved Round 2 winner for every cell, includes exact
launch/audit/resume commands and expected paths, and records:

```text
FULL_M0_SIX_CELL_CONFIG=FROZEN
FULL_M0_LAUNCH_PLAN=PREPARED
FULL_M0_PROCESS_RUNNING=NO
```

Plan generation never launches a full-M0 process. Full six-cell execution is a
separate researcher-authorized external workload.

## Telemetry and provenance

`process_tree_summary.json` records total wall, sampled aggregate CPU, mean host
CPU-capacity use, aggregate/main/worker peak RSS, process count, read/write
bytes, delay-accounting I/O wait, host RAM, filesystem headroom, and high-water
bytes for the run tree, SQLite/WAL/SHM, topology archives, pending inspection
shards, and filesystem used/free space. `timing_metrics.json` supplies
per-pass/inspection/finalization timing,
candidate/topology work, reducer database merge/stall, completed-but-blocked
shards, pending queue/shard gauges, and straggler distributions. Telemetry is
engineering-only and never feeds inference.

Every successful job must bind the plan and contract hashes, Git SHA/branch and
clean state, cell/workload, M0 freeze, representation and document-list hashes,
grammar hash/count, scientific and engineering configuration, workers, run and
metrics IDs, logical host, runtime versions, timestamps, resume history, final
status, and hashes of every canonical scientific artifact.

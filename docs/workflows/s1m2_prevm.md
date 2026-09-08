# S1M2 pre-VM production workflow

## Scope and frozen boundary

This workflow turns the accepted S1M2 implementation into a fail-closed VM
execution interface. It does not change the 1,218-rule grammar, legal candidate
support, scoring equations, exact inference, posterior semantics, piece limits,
or any frozen S1M1/M0 bytes. Opt17 is not authorized.

The production universe is exactly six independently trained cells. Five use
frozen M0. IAST `continuous` uses the validated derived M0-prime manifest and
the `iast_m0_prime` frontend; original M0 IAST `continuous` is scientifically
excluded and the contract refuses to substitute it. `full-M0` means the full
frozen-corpus extent of one representation cell, not a model named M0.

The machine-readable source of truth is
`configs/production/s1m2_six_cell.json`. Its contract hash is the SHA-256 of
canonical sorted JSON as emitted by `validate-contract`. Worker count is an
engineering parameter selected only by Round 1.

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
- summarize: `aggregate-round1` and `evaluate-round2`.

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

Round 1 and Round 2 use six distinct physical core VMs. This engineering
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

Round 1 is six simultaneous executions of the same frozen
Devanagari-continuous representative job. Scientific inputs and configuration
are identical; only engineering worker count and physical host differ:

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
hosts. A representative job is an external workload and is not a Codex-local
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

Aggregate only after all six jobs pass:

```text
python -m sktlm.production.s1m2 aggregate-round1 --plan artifacts/s1m2_production/round1_plan.json --output artifacts/s1m2_production/round1_result.json
```

The aggregator excludes scientific/audit/provenance failures and memory or
storage safety failures. It ranks eligible jobs by representative wall time.
If the fastest is at least 10% faster than the runner-up, it wins directly.
Otherwise configurations within the 10% practical-tie envelope are ordered by
lower process-tree RSS, watched storage, total CPU, canonical reducer stall,
and finally worker count. Required output fields are `ROUND1_STATUS`,
`WORKER_RANKING`, `WINNER_WORKERS`, `WINNER_REASON`, resource summaries, and
excluded-job reasons.

## Round 2: production-readiness matrix

Round 2 consumes `WINNER_WORKERS` from the Round 1 result; it never hardcodes a
worker count independently.

```text
python -m sktlm.production.s1m2 plan-round2 --round1-result artifacts/s1m2_production/round1_result.json --output artifacts/s1m2_production/round2_plan.json
```

The generated six-way-parallel plan contains exactly:

1. `core-01`: Devanagari continuous / stress;
2. `core-02`: M0-prime IAST continuous / representative;
3. `core-03`: Devanagari continuous / representative;
4. `core-04`: Devanagari surface_word / smoke;
5. `core-05`: Devanagari legacy_joined / smoke;
6. `core-06`: IAST surface_word / smoke.

All six jobs use the same `WINNER_WORKERS` selected by Round 1 and launch on
their six hosts concurrently. A shared single-VM execution is not a valid
production plan.

Execute the six generated commands, then evaluate:

```text
python -m sktlm.production.s1m2 evaluate-round2 --plan artifacts/s1m2_production/round2_plan.json --output artifacts/s1m2_production/round2_result.json
```

PASS requires all artifact audits, zero candidate overflow, exact provenance,
the explicit resume-capable interface, aggregate RSS at or below 80% of host
RAM, at least 20 GiB free at completion, and actual watched peak storage at
or below 300 GiB for every Round 2 job. Representative jobs additionally require
their full-corpus projected peak storage to remain at or below 300 GiB. Both
continuous representative wall times are scaled by
the frozen phoneme ratio `46,255,133 / 456,891`; both projections must meet the
existing approximately-three-hour engineering target (10,800 seconds). Stress
must complete/audit but is not linearly projected. The result emits each named
gate and `ROUND2_STATUS` as machine-readable PASS/FAIL.

These are engineering gates. Failure does not authorize approximate inference,
candidate pruning/tuning, a new sandhi reward, changed grammar, or Opt17.

## Final six-cell launch plan

Only a PASS Round 2 result can generate a full plan:

```text
python -m sktlm.production.s1m2 plan-final --round2-result artifacts/s1m2_production/round2_result.json --output artifacts/s1m2_production/final_six_cell_plan.json
```

The plan assigns the six cells in contract order to logical roles core-01
through core-06, uses the one Round 1 winner for every cell, includes exact
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

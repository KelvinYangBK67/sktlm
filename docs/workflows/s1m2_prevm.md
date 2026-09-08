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
  the exact tracked S1M2 planned-run identity and logical host role;
- summarize: `aggregate-round1` and `evaluate-round2`.

All plan and result writers refuse overwrite. The runner snapshots the plan,
contract hash, complete command, runtime versions, host identity, timestamps,
and attempt/resume history. It invokes the existing exact trainer through the
existing Linux process-tree metrics wrapper and preserves the child return
code. A failed job is resumable only by an explicit `--resume` invocation.

## Cheap pre-VM checks (normally under five minutes)

```text
python -m sktlm.production.s1m2 validate-contract
python -m pytest tests/production/test_s1m2_prevm.py tests/pieces/test_s1m2_training.py tests/cloud/test_audit_latent_run.py tests/cloud/test_sktlm_bridge.py -q
python -m sktlm.production.s1m2 validate-bounded --output-root artifacts/s1m2_prevm_validation/pre_vm_<SHA>
python -m pytest -q
git diff --check
```

The bounded validation uses one frozen document, one line, one pass, one worker,
exact training, and exact inspection for all six cells. It must emit
`bounded_validation.json` with `cell_count=6`, `status=PASS`, and a valid
checkpoint/config/provenance/storage/scientific-artifact audit for every cell.
It is an interface check only and must not be cited as representative timing or
scientific evidence.

If any check exceeds five minutes, stop it, preserve its output, and report the
exact unfinished command as an external gate. Never replace it with a larger
benchmark.

## Round 1: VM worker scaling

Round 1 is six sequential executions of the same frozen Devanagari-continuous
representative job. Only worker count changes: 4, 8, 12, 16, 20, 24.

Prepare the immutable plan:

```text
python -m sktlm.production.s1m2 plan-round1 --output artifacts/s1m2_production/round1_plan.json
```

Execute each `launch_command_shell` in plan order on the logical
`s1m2-vm-01` role. A representative job is an external workload and is not a
Codex-local validation. Each job must have a distinct absent run directory and
metrics identity. Do not run worker variants concurrently on one host.

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

The generated plan contains exactly:

1. Devanagari continuous / stress;
2. M0-prime IAST continuous / representative;
3. Devanagari continuous / representative;
4. Devanagari surface_word / smoke;
5. Devanagari legacy_joined / smoke;
6. IAST surface_word / smoke.

Execute the six generated commands, then evaluate:

```text
python -m sktlm.production.s1m2 evaluate-round2 --plan artifacts/s1m2_production/round2_plan.json --output artifacts/s1m2_production/round2_result.json
```

PASS requires all artifact audits, zero candidate overflow, exact provenance,
the explicit resume-capable interface, aggregate RSS at or below 80% of host
RAM, at least 20 GiB free at completion, and projected representative peak
storage below 300 GiB. Both continuous representative wall times are scaled by
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

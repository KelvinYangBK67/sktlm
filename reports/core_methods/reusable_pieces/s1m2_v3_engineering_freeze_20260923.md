# S1M2 V3 engineering implementation freeze

Date: 2026-09-23

Status: **ENGINEERING IMPLEMENTATION FROZEN**

## Freeze identity

| Field | Value |
|---|---|
| Scientific semantics | `FROZEN` |
| Engineering implementation | `FROZEN` |
| Accepted implementation HEAD | `7ae18240b2e81125cc2fc159969760e4deccafc6` |
| Branch | `exp/s1m2-reusable-pieces` |
| Performance result | `NOT_YET_MEASURED_AT_FULL_SCALE` |
| Production contract | `configs/production/s1m2_six_cell_v3.json` |
| Contract ID | `s1m2-six-cell-v3-prefreeze-v1` |
| Contract file SHA-256 | `6a29480ba27d82ed334cdc6027f2aedab30e6fc7b3f5ebe2465ff6469b3022fa` |
| Contract canonical SHA-256 | `03c524b8978919bbfb98f65caaf75625e4cd053314c704f433ad002009b27bd2` |

The scientific semantics remain independently frozen by
`s1m2_v3_scientific_freeze_20260922.md`. This engineering freeze is an
implementation lifecycle decision and does not introduce or reinterpret a
scientific objective.

## Completed scope

The accepted implementation contains all fourteen authorized engineering
changes:

1. role-neutral production piece-score caching;
2. shorter segment-local object lifetimes;
3. token-local reuse of internal grammar matches;
4. removal of full posterior-map copies;
5. allocation-light ordered piece endpoints;
6. reduced SQLite row materialization;
7. streamed execution-bundle plan loading and hashing;
8. removal of avoidable hot-loop slices and singleton tuples;
9. scorer-lifetime constant precomputation;
10. removal of training-only `factor_top_paths` bookkeeping;
11. replacement of count-only sets with scalar state;
12. prompt release of parsed JSONL records;
13. single-pass candidate statistics; and
14. direct length accounting for known-ASCII stable keys.

The detailed implementation record is
`s1m2_v3_engineering_optimization_20260922.md`. The optimization sweep is
closed; this task changes documentation and control-plane state only.

## Accepted review result

```text
SCIENTIFIC_SEMANTICS=FROZEN
ENGINEERING_SWEEP=PASS
STATIC_REVIEW=PASS
REWORK_REQUIRED=NO
```

Researcher static review found no blocker requiring another engineering round.
No test-equivalence or measured-performance result is claimed by this closure.

## Measurement status

```text
TESTS_RUN_DURING_OPTIMIZATION=NO
BENCHMARKS_RUN_DURING_OPTIMIZATION=NO
PROFILING_RUN_DURING_OPTIMIZATION=NO
SMALL_SCALE_PERFORMANCE_GATE=INTENTIONALLY_NOT_USED
VM_OR_CLOUD_RUN=NO
FULL_M0_RUN=NO
FULL_SCALE_RUNTIME_RSS_RESULT=NOT_YET_AVAILABLE
```

The frozen implementation is the accepted production candidate. Its runtime
and peak-RSS outcome remains intentionally unmeasured until the authorized
full-scale VM production phase.

## Why another small-scale performance gate is rejected

First, repeated optimization, small test, and further tuning cycles have no
natural stopping point after the major structurally justified work is complete.
The completed changes remove duplicate containers and traversal, shorten large
object lifetimes, share immutable state, stream input, and precompute fixed
values. Their production admission does not require another small workload to
reopen the tuning loop.

Second, a small workload does not reproduce Full M0 candidate branching,
long-tail segments, piece/host cardinality, cache reuse and eviction, SQLite
write volume, worker lifetime, long-running heap behavior, bundle distribution,
script and spacing differences, or peak RSS. A small measured effect therefore
does not reliably quantify the full-scale effect, and a structurally important
change can appear insignificant locally.

The project has already lost a valuable production round because conclusions
from a smaller scale did not adequately represent the full workload. That is
direct project evidence against using another small performance probe as the
gate between this engineering closure and Full M0.

This policy is limited to repeated small-scale performance gates for the frozen
S1M2 V3 production path. It is not a general rejection of correctness testing.
Small-scale performance results must not automatically start another tuning
cycle.

## Freeze meaning and reopening conditions

The runtime implementation at the accepted HEAD is closed. Further speculative
tuning, micro-allocation cleanup, cache adjustment, style cleanup, general
refactoring, or unmeasured theoretical optimization is not authorized before
VM deployment.

Researcher-authorized implementation work may reopen only if the subsequent
VM or full-scale run exposes one of these conditions:

1. a correctness bug;
2. OOM or a hard RSS failure;
3. a clear production-blocking runtime failure;
4. an execution or control-plane defect that prevents the planned run;
5. a violation of frozen scientific semantics; or
6. an existing scientific requalification trigger.

Any later code change to the frozen runtime path must name its applicable
condition and receive researcher authorization.

## Next phase

```text
VM preparation
-> researcher-authorized deployment
-> frozen V3 full-scale confirmatory production
```

This closure authorizes documentation and control-plane preparation only. It
does not authorize VM access, deployment, a performance probe, or Full M0.

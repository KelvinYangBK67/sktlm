DATE=2026-09-28
BRANCH=exp/s1m2-runtime-reopen
STATUS=S1M2_V3_ROUND3BC_CANDIDATE_AWAITING_UPDATED_CORE11_BENCHMARK

BASELINE_SHA=5ec5d5c33a59abe06fadc9bde84f48b380b7fe39
BENCHMARK_CANDIDATE_SHA=464e4dc4050e15bd9a233ae04f543211e7798ac7
SCIENTIFIC_SEMANTICS=FROZEN
PERFORMANCE_RESULT=NOT_YET_REMEASURED_ON_CORE_11
FULL_M0_RUNTIME_VIABLE=NOT_REQUALIFIED

Round 3B/3C is locally complete. The candidate adds immediate validated bundle
retirement before document commit, crash-safe missing-bundle recomputation,
execution-only byte backpressure, raw-key reducer APIs, packed binary64
host-support sidecars without reconstructible-payload fsync, one-scan V3
moments, exact bounded neutral host templates, and batch-local aligned bulk
PieceStore scores for topology pieces and compact endpoint whole forms.

Compact topology persistence and transient SQLite integer/BLOB identities were
not implemented because their new storage/order/recovery contracts are higher
risk without the updated Core-11 evidence. `.codex/DECISIONS.md` is unchanged
because no scientific or research decision changed.

Validation completed locally:

- final combined selection: 139 passed in 45.66 seconds;
- 84 composed/training/V3 tests passed in about 15 seconds;
- 53 scheduler/planner/production-wiring/metrics/comparator tests passed in
  about 14 seconds;
- 13 focused cache/bundle/comparator tests passed in about four seconds;
- touched Python modules compile and `git diff --check` passes.

No >5-minute test, representative/stress workload, Passes 2/3 benchmark,
Full M0 run, VM/cloud/SSH action, or operation on Core-07 through Core-10 was
performed.

NEXT_ACTION=RESEARCHER_RUNS_UPDATED_CORE11_BASELINE_CANDIDATE_AND_COMPARATOR

Use the exact commands in:
`reports/core_methods/reusable_pieces/s1m2_runtime_reopen_core11_benchmark_20260928.md`

The protocol is the same idle Core-11, complete first Devanagari continuous
document, W12, Pass 1, baseline then candidate sequentially. The candidate
command explicitly sets the execution-only ready-spool bound to 4294967296
bytes. Run the training-state comparator first; do not interpret performance
unless it reports PASS under unchanged `rtol=1e-10`, `atol=1e-12`.

First-document identity:
`1_veda/2_bra/gopbra_u.txt`, 5315 segments, 195480 phonemes, pressure
10579072, 39 bundles, plan SHA-256
`e66b0363d19ea53b8023653ba33e27367466dbeaa8b3e30eaf103c31ab7d4d81`.

Do not launch VM/cloud/Full M0 automatically. Do not touch Core-07 through
Core-10 or their run/checkpoint/artifact state.

DATE=2026-09-28
BRANCH=exp/s1m2-runtime-reopen
STATUS=S1M2_V3_RUNTIME_RSS_CANDIDATE_AWAITING_CORE11_BENCHMARK

BASELINE_SHA=5ec5d5c33a59abe06fadc9bde84f48b380b7fe39
BENCHMARK_CANDIDATE_SHA=4f8e09707ab283a0a796d89d882e4b45c6621762
SCIENTIFIC_SEMANTICS=FROZEN
PERFORMANCE_RESULT=NOT_YET_MEASURED_ON_CORE_11
FULL_M0_RUNTIME_VIABLE=NOT_REQUALIFIED

The candidate implements exact engineering changes for the confirmed Full M0
scaling mechanisms: bounded grammar cache and monitoring, streamed SQLite
host support, an exact neutral Pass-1 route, bounded host-specific adjoints,
row-streamed bundle host support, and strict incremental canonical reduction
overlapped with later workers. Pass/checkpoint and document transaction
semantics are unchanged.

Focused final validation: 38 passed in 3.43 seconds. No >5-minute,
representative, stress, Passes 2/3, Full M0, VM, or cloud workload was run.
Core-07 through Core-10 were not contacted or changed.

The next action is researcher-operated on idle Core-11 only:

1. Make `BENCHMARK_CANDIDATE_SHA` available in `/root/sktlm`.
2. Follow the exact worktree, first-document plan, baseline, and candidate
   commands in the authority report.
3. Run the training-state comparator without changing its tolerance.
4. Interpret wall/RSS/reducer telemetry only if the comparator reports PASS.
5. Decide whether the measured result justifies any later Full redeployment or
   a separately scoped secondary optimization.

First-document identity:
`1_veda/2_bra/gopbra_u.txt`, 5315 segments, 195480 phonemes, 39 bundles,
plan SHA-256
`e66b0363d19ea53b8023653ba33e27367466dbeaa8b3e30eaf103c31ab7d4d81`.

Authority:
reports/core_methods/reusable_pieces/s1m2_runtime_reopen_core11_benchmark_20260928.md

Do not launch VM/cloud/Full M0 automatically. Do not touch Core-07 through
Core-10 or their run/checkpoint/artifact state.

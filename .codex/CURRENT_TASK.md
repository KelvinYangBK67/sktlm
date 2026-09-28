DATE=2026-09-28
BRANCH=exp/s1m2-runtime-reopen
STATUS=S1M2_V3_ROUND3D_CANDIDATE_AWAITING_CORE11_BENCHMARK

BASELINE_SHA=5ec5d5c33a59abe06fadc9bde84f48b380b7fe39
BENCHMARK_CANDIDATE_SHA=38557dab9bff522dfb886452b4786da04e627458
SCIENTIFIC_SEMANTICS=FROZEN
PERFORMANCE_RESULT=NOT_YET_REMEASURED_ON_CORE_11
FULL_M0_RUNTIME_VIABLE=NOT_REQUALIFIED
PRODUCTION_JOURNAL_MODE=WAL_NORMAL_UNCHANGED

Round 3D is locally complete. The compact production reducer now uses
flush-local piece/host integer identities and an integer-pair Counter. New
bundle v4 / segment v5 host dictionaries carry a fixed versioned phoneme BLOB
without reconstructing canonical host strings in the parent hot path. New
transient SQLite support tables use BLOB hosts; active legacy TEXT passes have
an explicit compatible resume path, and schema conflicts fail closed.

Piece-count, pooled-support, lexical-diagnostic, and optional role writes use
ordered bounded multi-row UPSERTs under a fixed 900-bind ceiling. Canonical
document/bundle/segment/row order, per-key floating addition sequence, flush
boundaries, V3 final moments, checkpoint meaning, and frozen comparator
tolerances are unchanged.

The 16.96-second local synthetic journal benchmark found no meaningful peak-
storage benefit for DELETE/TRUNCATE and materially slower transaction phases,
so production remains WAL + NORMAL. Append-only external support runs were
designed but deferred because they require a new cross-filesystem manifest,
orphan, recovery, and ordered external-merge contract.

Validation completed locally:

- touched modules and journal benchmark script compile;
- 63 focused codec/V3/bundle tests passed in 14.16 seconds;
- 98 selected storage/comparator/V2/V3/training/bundle/Round-3 tests passed in
  36.48 seconds;
- corrected synthetic SQLite journal benchmark passed in 16.96 seconds;
- git diff --check passed.

No representative/stress workload, Passes 2/3 production benchmark, Full M0,
VM/cloud/SSH action, or operation on Core-07 through Core-11 was performed.

NEXT_ACTION=RESEARCHER_RUNS_UPDATED_CORE11_BASELINE_CANDIDATE_AND_COMPARATOR

Use the exact commands in:
`reports/core_methods/reusable_pieces/s1m2_runtime_reopen_core11_benchmark_20260928.md`

The protocol remains idle Core-11, the complete first Devanagari continuous
document, W12, Pass 1, historical baseline then Round 3D candidate, followed
first by the training-state comparator. Do not interpret performance unless it
reports PASS under unchanged `rtol=1e-10`, `atol=1e-12`.

First-document identity:
`1_veda/2_bra/gopbra_u.txt`, 5315 segments, 195480 phonemes, pressure
10579072, 39 bundles, plan SHA-256
`e66b0363d19ea53b8023653ba33e27367466dbeaa8b3e30eaf103c31ab7d4d81`.

After comparator PASS, inspect reducer decode/accumulate/sort/flush timing,
support batch counts/rows, compact-versus-canonical host bytes, main RSS,
SQLite/WAL/storage high-water, and the bundle timeline. If SQLite support flush
still dominates, use the external-run design conditions in the Round 3D report
as the next engineering audit; do not implement it speculatively.

Do not launch VM/cloud/Full M0 automatically. Do not touch Core-07 through
Core-10 or their run/checkpoint/artifact state.

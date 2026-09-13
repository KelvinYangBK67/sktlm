# CURRENT TASK

DATE=2026-09-13
BRANCH=exp/s1m2-reusable-pieces
STATUS=ROUND4_RUNTIME_OPTIMIZATION_IMPLEMENTED

ROUND4_START_HEAD=535f4e618563d88b9d85109d03bfaf1b049664dc
ROUND4_CODE_HEAD=3b937abd4a64d5f6b48034d716112bdedca918e8
DIRECT_SEEK_EXECUTION_BUNDLES=PASS_LOCAL
STREAMING_BUNDLE_SHARD_SHA=PASS_LOCAL
DUPLICATE_LEGAL_SPAN_TRAVERSAL_REMOVED=PASS_LOCAL
STRING_KEY_CANONICAL_REDUCER=PASS_LOCAL
COMPACT_TRANSIENT_TRIE=PASS_LOCAL
FIXED_PIECE_DP_PRIORS=PASS_LOCAL
SCIENTIFIC_SEMANTICS_CHANGED=NO
RAM_BOUND_INCREASED=NO
LONG_VALIDATION_RUN=NO
FULL_M0_AUTHORIZED=NO

Round 4 removed repeated document-prefix reads, post-write shard rereads,
duplicate legal-span telemetry scans, repeated reducer form construction,
transient compact-trie node objects, and repeated fixed-prior construction.
All changes are execution-only. Candidate membership, inference, posterior,
support, scoring, canonical reduction and floating-point accumulation order are
unchanged. Worker, inflight, lookahead, cache and retained-factor bounds were
not increased.

Execution bundle plans now use schema/planner implementation v2 and contain a
deterministic UTF-8 byte offset for each bundle's first source line. Existing
v1 plans fail closed and must be rematerialized before a run uses this HEAD;
this changes execution-plan identity, not scientific training identity.

NEXT_ACTION=RESEARCHER_RUN_ROUND4_MANUAL_GATES

Do not automatically launch Full M0, VM/cloud work, representative/stress
workloads, worker calibration, RAM/runtime benchmarks, or long equivalence
runs. The researcher should manually rematerialize any needed v2 execution
plan, run a short 12-worker Pass-2 RAM/runtime probe, and perform the canonical
scientific-equivalence comparison.

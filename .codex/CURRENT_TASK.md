# CURRENT TASK

DATE=2026-09-13
BRANCH=exp/s1m2-reusable-pieces
STATUS=LEGACY_S1M2_PASS1_FINALIZE_ONLY_RECOVERY_READY_LOCAL

START_HEAD=e8c5de49739d34953d058edeba55a6062fd766f7
SCIENTIFIC_SEMANTICS_CHANGED=NO
SCIENTIFIC_OUTPUT_IDENTITY=PASS_LOCAL_SQL_REFERENCE
WORKER_COUNT_UNCHANGED=YES
CACHE_LIMITS_UNCHANGED=YES
INFERENCE_PATH_UNCHANGED=YES
TRANSACTION_FREQUENCY_UNCHANGED=YES
HOT_LOOP_EXTRA_IO=0
PASS_BOUNDARY_WAL_TRUNCATE=PASS_LOCAL
PIECE_FINALIZE_NO_FULL_COPY=PASS_LOCAL
TRANSIENT_TABLE_LIFECYCLE=PASS_LOCAL
RESUME_SAFETY=PASS_LOCAL
REMOTE_OPERATIONS_RUN=NO
LONG_VALIDATION_RUN=NO
FULL_M0_RUN=NO
FULL_M0_AUTHORIZED=NO
FULL_END_TO_END_IDENTITY_VALIDATED=NO
LEGACY_V1_FINALIZE_ONLY_RECOVERY=PASS_LOCAL
V1_TO_V2_EXECUTION_PLAN_MIGRATION=PASS_LOCAL
ATOMIC_PLAN_AND_PASS_TRANSITION=PASS_LOCAL
COMPLETED_DOCUMENTS_REPROCESSED=0
RECOVERY_WORKER_POOLS_STARTED=0
RECOVERY_DOCUMENT_ITERATIONS=0
PASS2_NORMAL_V2_ADMISSION=PASS_LOCAL
CORE07_PASS1_RECOVERY_PATH=PASS_LOCAL
CORE07_PASS1_RECOVERED=NO

S1M2 pass finalization now filters `piece_counts_next` in place and renames it
to `piece_lexicon`, preserving the exact positive-count and reuse-support
selection without creating and filling a second full active table. The
transaction still atomically installs the authoritative piece state and
completed-pass checkpoint. Pass-only lexical diagnostics are retired in that
same transaction.

After the committed S1M2 pass and worker/read-only connection teardown, the
trainer performs a fail-closed `PRAGMA wal_checkpoint(TRUNCATE)`. Telemetry
records database/WAL/SHM/total bytes before finalize, after finalize, and after
WAL truncation, plus checkpoint count and duration. No VACUUM was added.

The narrow recovery path accepts only an authoritative SQLite S1M2 checkpoint
for active Pass 1 with zero completed passes, all configured documents already
committed, matching active metrics, non-empty `piece_counts_next`, present
`lexical_diagnostics_next`, and the exact supported v1 plan/planner identity.
The requested plan must first pass the complete current v2 loader, and its
representation-set and segment-sequence identities must exactly match v1.

Recovery performs no corpus iteration, candidate/inference work, bundle
dispatch, or worker-pool creation. It uses the optimized in-place piece
finalization and WAL truncation. Pass completion, v2 plan identity, and a
preservation-oriented v1-to-v2 migration record are written atomically in the
same authoritative SQLite transaction. Pass 2 then returns to the ordinary v2
resume path. The core-07 database has not been touched by Codex.

Focused recovery validation passes 10 tests. Full scientific output identity
remains unvalidated because the unrelated composed-prior fixture failure was
not changed; the supported claim remains
`SCIENTIFIC_OUTPUT_IDENTITY=PASS_LOCAL_SQL_REFERENCE`.

Corrected researcher-observed PRE_CHANGE storage pressure: `/dev/vdb` exposed
approximately 295 GiB, used approximately 281 GiB, had no available space and
was at 100%; the current run directory was approximately 208 GiB, comprising
approximately 106 GiB `learner.sqlite`, 103 GiB WAL, and 203 MiB SHM.
Historical attempts additionally occupied approximately 2.0 GiB and 66 GiB.
These are observations, not post-change validation.

NEXT_ACTION=RESEARCHER_RUN_CORE07_PASS1_FINALIZE_ONLY_RECOVERY

Do not automatically launch Full M0, representative, stress, RAM/runtime, VM,
cloud, or other long validation. Validate post-change disk peaks and canonical
scientific artifacts on the researcher-controlled workload before declaring
the Full M0 disk target closed.

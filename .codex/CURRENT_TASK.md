# CURRENT TASK

DATE=2026-09-13
BRANCH=exp/s1m2-reusable-pieces
STATUS=S1M2_SQLITE_STORAGE_LIFECYCLE_OPTIMIZED_LOCAL

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

The dedicated lifecycle tests pass (3 tests). A pre-existing focused training
fixture fails before reaching this change, in composed inference prior lookup
with `IndexError: tuple index out of range`; it was not changed or bypassed.

The researcher-observed Full continuous storage pressure motivating this work
was approximately 108 GiB for the current run directory, approximately 106
GiB for `learner.sqlite`, and approximately 2.03 GiB for its WAL. These are
observations, not post-change validation.

NEXT_ACTION=RESEARCHER_RUN_FULL_M0_DISK_AND_SCIENTIFIC_EQUIVALENCE_PROBES

Do not automatically launch Full M0, representative, stress, RAM/runtime, VM,
cloud, or other long validation. Validate post-change disk peaks and canonical
scientific artifacts on the researcher-controlled workload before declaring
the Full M0 disk target closed.

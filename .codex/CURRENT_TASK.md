# CURRENT TASK

DATE=2026-09-14
BRANCH=exp/s1m2-reusable-pieces
STATUS=ROUND4_PRODUCTION_HARDENING_PASS_LOCAL

IMPLEMENTATION_HEAD=41ce1a6542d8e31105c1458bc3edbfae3f2592ee
ROUND4_LONG_WHOLE_PRIOR_REGRESSION=FIXED
SCIENTIFIC_SEMANTICS_CHANGED=NO
P0_REFERENCE_EQUIVALENCE=PASS_LOCAL
PYTEST_COLLECTION=PASS_787_COLLECTED
CI_COLLECTION_FIX=PASS_LOCAL
FULL_AUTHORIZATION_GATE=PASS_LOCAL
CHILD_INTERPRETER_BINDING=PASS_LOCAL
LAUNCH_FAILURE_BOOKKEEPING=PASS_LOCAL
FAILED_RUN_RESET_PROTOCOL=PASS_LOCAL
LEGACY_V1_PASS1_FINALIZED_MIGRATION=PASS_LOCAL
STATUS_SQLITE_AUTHORITATIVE=PASS_LOCAL
PRODUCTION_BOOTSTRAP_PROFILE=PASS_LOCAL
BUNDLE_VALIDATION_SINGLE_AUTHORITY=PASS_LOCAL
LAUNCH_PREFLIGHT=PASS_LOCAL
FULL_ENVIRONMENT_LOCK=PARTIAL
REMOTE_OPERATIONS_RUN=NO
FULL_M0_RUN=NO
FULL_M0_AUTHORIZED=NO

Round 4 restores the exact fixed P0 prior for a legal whole form longer than
`piece_max_length`; bounded internal spans still use the precomputed table and
illegal long internal spans fail closed. No scientific equation, candidate,
posterior, grammar, frozen input, worker count, cache bound, or canonical
reduction order changed.

The production control plane now requires a separately generated exact Full
authorization artifact, uses the current interpreter for child phases, records
subprocess launch exceptions as durable FAILED state, offers a path-bounded
FAILED-only reset with a surviving receipt, reads status from SQLite first,
and performs cheap Full filesystem/memory/interpreter admission before spawn.
Full host and execution-bundle declarations are contract-owned and final plans
bind their exact plan and materialization identities.

The second legacy recovery state is implemented for authoritative SQLite with
finalized Pass 1 and an inactive boundary. It admits only an exact v1-to-v2
execution-identity migration with matching representation and segment
identities and unchanged finalized piece/history invariants. It performs no
Pass 1 finalization or completed-document/worker/inference recovery work, then
enters the normal v2 Pass 2 path.

Generic bootstrap remains distinct from S1M2 production bootstrap. Production
mode selects the Full cell assigned to the host, transfers that cell's
non-Git bundle/input set, runs the authoritative cell-specific validator in the
remote venv, and reports `S1M2_PRODUCTION_READY` only after exact validation.
CPython 3.11.9 source is checksum-verified. Reused and installed environments
emit Python/pip/direct-package versions and canonical `pip freeze --all` SHA;
there is no reliable tracked Linux dependency lock, so reproducibility remains
explicitly PARTIAL.

Local validation:

- `python -m pytest --collect-only -q`: 787 collected, zero errors.
- focused Round 4 suites: 134 passed; VM-ops compatibility: 7 passed.
- one earlier full-suite run reached 770 passed and 8 failed; each exposed
  failure surface was fixed and rerun in focused suites. The complete suite was
  not repeated to avoid redundant validation; final whole-suite confirmation
  is deferred to CI.

Four tracked Full bundle materializations are still legacy v1 (IAST surface,
IAST legacy, M0-prime IAST continuous, and Devanagari continuous). This turn
was explicitly forbidden to rematerialize full-corpus plans. The authoritative
production validator therefore correctly blocks those cells until the
researcher supplies their v2 production inputs; Devanagari surface/legacy are
already v2.

NEXT_ACTION=RESEARCHER_DEPLOY_AUTHORIZE_RESET_MIGRATE_AND_LAUNCH

Researcher sequence: deploy the new HEAD and exact v2 production inputs;
generate the explicit Full authorization; use `reset-failed` for core-09 and
core-10; run the guarded core-07 finalized-Pass1 identity-only migration; then
launch the authorized formal jobs. Codex did not perform any of these remote
actions.

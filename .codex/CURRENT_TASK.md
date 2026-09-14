# CURRENT TASK

DATE=2026-09-14
BRANCH=exp/s1m2-reusable-pieces
STATUS=FULL_EXECUTION_SCOPE_PASS_LOCAL

IMPLEMENTATION_HEAD=41ce1a6542d8e31105c1458bc3edbfae3f2592ee
ROUND4_LONG_WHOLE_PRIOR_REGRESSION=FIXED
SCIENTIFIC_SEMANTICS_CHANGED=NO
P0_REFERENCE_EQUIVALENCE=PASS_LOCAL
PYTEST_COLLECTION=PASS_795_COLLECTED
CI_COLLECTION_FIX=PASS_LOCAL
CI_CLEAN_CHECKOUT_ARTIFACT_DEPENDENCY=FIXED_LOCAL
GITHUB_CI=UNKNOWN_PENDING_RERUN
FULL_AUTHORIZATION_GATE=PASS_LOCAL
SCIENTIFIC_SIX_CELL_UNIVERSE=FROZEN
PRODUCTION_EXECUTION_SCOPE=EXPLICIT_SUBSET_SUPPORTED
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

Full plan construction now accepts an optional repeatable cell selection.
Omitting it preserves the six-job default. An explicit non-empty selection is
validated against the frozen six-cell universe, rejects duplicates, and emits
jobs in frozen contract order. Only selected bundle materializations are
loaded; `execution_cell_ids`, `FULL_EXECUTION_SCOPE`, and the unchanged
`FULL_M0_SIX_CELL_CONFIG=FROZEN` enter the plan hash and exact authorization.

The intended current execution set is M0-prime IAST continuous/core-07,
Devanagari continuous/core-08, Devanagari surface_word/core-09, and Devanagari
legacy_joined/core-10. The emitted canonical order follows the frozen contract:
M0-prime IAST continuous, Devanagari surface_word, Devanagari legacy_joined,
then Devanagari continuous. IAST surface_word and legacy_joined are already
complete and are not selected for re-execution.

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

- `python -m pytest --collect-only -q`: 795 collected, zero errors (8 focused
  execution-scope cases added).
- Full execution-scope focused production suites: 41 passed.
- focused Round 4 suites: 134 passed; VM-ops compatibility: 7 passed.
- clean-checkout artifact closure: 3 targeted tests passed; both complete
  affected test files passed 39 tests. The bootstrap test retains the real
  tracked six-cell/core-09 wiring while controlling only the external file
  verifier boundary; the selector test now separates synthetic algorithm
  coverage from tracked list/hash provenance.
- one earlier full-suite run reached 770 passed and 8 failed; each exposed
  failure surface was fixed and rerun in focused suites. The complete suite was
  not repeated to avoid redundant validation; final whole-suite confirmation
  is deferred to CI.

Four tracked Full bundle materializations are still legacy v1, but the already
completed IAST surface/legacy cells are outside the intended execution scope
and no longer block its plan. The two selected continuous cells still require
researcher-supplied v2 production inputs; Devanagari surface/legacy are already
v2. This turn did not materialize any plan.

NEXT_ACTION=RESEARCHER_REMATERIALIZE_TWO_SELECTED_CONTINUOUS_V1_FULL_BUNDLE_PLANS

Researcher sequence begins by rematerializing the M0-prime IAST continuous and
Devanagari continuous Full bundle plans as exact v2 production inputs. Only
after those selected inputs exist should the new HEAD be deployed, the scoped
four-cell final plan and explicit authorization generated, failed jobs reset,
the guarded core-07 migration run, and formal jobs launched. Codex did not
perform any of those operations.

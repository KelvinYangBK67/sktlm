# CURRENT TASK

DATE=2026-09-14
BRANCH=exp/s1m2-reusable-pieces
STATUS=HISTORICAL_QUALIFICATION_IDENTITY_PASS_LOCAL

TASK_BASE_HEAD=a46cf976f54dc931d08f785deb4525156874d216
ROUND4_HARDENING_IMPLEMENTATION_HEAD=41ce1a6542d8e31105c1458bc3edbfae3f2592ee
ROUND4_LONG_WHOLE_PRIOR_REGRESSION=FIXED
SCIENTIFIC_SEMANTICS_CHANGED=NO
P0_REFERENCE_EQUIVALENCE=PASS_LOCAL
PYTEST_COLLECTION=PASS_801_COLLECTED
HISTORICAL_QUALIFICATION_VALIDATION=PASS_LOCAL
HISTORICAL_QUALIFICATION_CONTRACT_SHA256=f8684597c061f6608569042e69fa8a0fed9badd14a413976abcd12a8d62cd92d
CURRENT_EXECUTION_CONTRACT_SHA256=c32c195901f989d7b41ab0875f31d05280a36b3462e93d73ceeb2a185c920809
NEW_ROUND3_CLOSURE_BUILD_REMAINS_CURRENT_CONTRACT_STRICT=YES
FINAL_PLAN_CURRENT_CONTRACT_BINDING=PASS_LOCAL
ROUND2_ROUND3_ARTIFACTS_CHANGED=NO
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

Historical Round 2/3 qualification validation is now independent of later
execution-artifact changes in the production contract. The immutable Round 3
closure contract SHA is syntax-checked and used as the exact expected Round 2
contract SHA; every existing closure checksum, Round 2 artifact/payload,
evidence, history, commit-ancestry, worker, and overflow gate remains intact.
New closure construction remains current-contract strict, while final plans
and authorization continue to bind the current contract, current Git identity,
and selected current bundle materializations.

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

- historical/current contract-identity focused suites: 30 passed in 1.05s.
- `python -m pytest --collect-only -q`: 801 collected, zero errors.
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

The selected continuous cells are now bound to exact v2 Full bundle artifacts
by the current production contract. The two remaining legacy v1 Full bundles
belong to already-completed, unselected IAST surface/legacy cells and do not
block the intended scoped invocation. This turn did not materialize a plan or
authorization and did not modify historical Round 2/3 artifacts.

NEXT_ACTION=CI_CONFIRM_THEN_RESEARCHER_GENERATE_SCOPED_FINAL_PLAN_AND_AUTHORIZATION

After CI confirms this commit, the researcher may generate the scoped
four-cell final plan and its explicit authorization from the current contract,
then proceed with the separately guarded deployment/reset/migration/launch
sequence. Codex did not perform any of those operations.

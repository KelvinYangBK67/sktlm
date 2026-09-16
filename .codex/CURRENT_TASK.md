# CURRENT TASK

DATE=2026-09-16
BRANCH=exp/s1m2-reusable-pieces
STATUS=S1M2_V2_SEMANTIC_REPAIR_IMPLEMENTED_LOCAL_AWAITING_REVIEW

TASK_BASE_HEAD=199cd70757dc10ff2e9b1ad971ae96dc81b3f490
S1M2_V1_SCIENTIFIC_FAILURE=UNCHANGED
S1M2_V2_SEMANTIC_REPAIR=IMPLEMENTED_LOCAL
OBSERVED_WHITESPACE_HARD_FENCE=PASS_LOCAL
VISIBLE_BOUNDARY_JOINED_RULE_INVERSION=PASS_LOCAL
INTERNAL_JOINED_RULE_INVERSION=PASS_LOCAL
POSITIONAL_PIECE_IDENTITY=PASS_LOCAL
DISTINCT_HOST_TYPE_QUALIFICATION=PASS_LOCAL
WHOLE_FORM_FALLBACK=LEGAL
SCORER_OBJECTIVE_CHANGED=NO
FROZEN_SANDHI_INVENTORY_CHANGED=NO
FROZEN_M0_CHANGED=NO
FULL_M0_RUN=NO
FULL_M0_AUTHORIZED=NO
REMOTE_OPERATIONS_RUN=NO
COMMIT_CREATED=NO
PUSH_RUN=NO

The local V2 patch makes every observed space a hard lexical fence without
equating lexical boundary with whitespace: missing spaces still permit latent
boundaries. Joined frozen sandhi surfaces are indexed at every exact visible
split, so `ū + e -> ve` is invertible across `v | e` as well as internally
inside `ve`. Regression coverage includes
`svayaṃbhv ekam -> svayaṃbhū | ekam`.

Reusable-piece identity is `(form, WHOLE|LEFT|RIGHT|INTERNAL)`. Expected count
and score lookups are role-conditioned. Qualification is separate: posterior
host mass is aggregated across tokens/derivations by stable lexical-form key,
then distinct host types meeting `piece_host_support_threshold=1.0` are
counted. Multi-phoneme identities require two qualifying host types by
default; singleton identities remain active. One repeated whole lexical form
therefore cannot qualify itself. Whole-form legality, including the long
fallback, remains unchanged.

The fixed scorer formula/hyperparameters, external-sandhi TSV, joint exact
posterior, shared trie, compact/lazy paths, bounded caches, streaming SQLite
reduction, bundle scheduler, topology reuse, and worker scheduling remain the
existing architecture. The necessary role and host-support metadata is routed
through those paths; no four-way duplicated DP or occurrence-history
materialization was introduced.

Documentation authority for this patch is
`reports/core_methods/reusable_pieces/s1m2_v2_semantic_repair_20260916.md`.
The V1 scientific authority remains
`reports/core_methods/reusable_pieces/s1m2_full_m0_scientific_failure_20260915.md`.

No real-corpus or performance conclusion is available. The next session must
not launch Full M₀ or a large benchmark merely because the unit regressions
pass.

Final local checks:

- touched source and analysis modules: `py_compile` passed;
- direct semantic/reference/store regressions: 57 passed in 1.60s;
- four selected streaming/parallel/bundle regressions: 4 passed in 4.30s;
- production-contract validation: PASS at SHA-256
  `12c0df4cc897f38632eb23b1d66685f3bfeb3de5854d560870b83e201f44e68e`.

NEXT_ACTION=HUMAN_REVIEW_THEN_BOUNDED_V2_PREFLIGHT_DESIGN

Suggested review commands after inspecting the dirty tree:

```powershell
git diff --check
git diff --stat
python -m pytest tests/latent/test_frontend_and_candidates.py tests/pieces/test_p1ab_checkpoint.py tests/pieces/test_p1c_composed_inference.py tests/latent/test_s1m2_storage_lifecycle.py -q
python -m sktlm.production.s1m2 --repo-root . validate-contract
```

Do not commit, push, run Full M₀, deploy to a VM, or run a representative,
stress, RAM, or runtime benchmark without separate researcher review and
authorization.

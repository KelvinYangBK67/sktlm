# CURRENT TASK

DATE=2026-09-17
BRANCH=exp/s1m2-reusable-pieces
STATUS=S1M2_DIRECT_VISIBLE_BOUNDARY_FIX_VALIDATED_PENDING_PUBLICATION

TASK_BASE_HEAD=bc10308048bb7c1b179b3e0dedb10581714e8093
PREVIOUS_REPAIR_COMMIT=bc10308048bb7c1b179b3e0dedb10581714e8093
PREVIOUS_REPAIR_PUSHED=YES
S1M2_V1_SCIENTIFIC_FAILURE=UNCHANGED
S1M2_V2_SEMANTIC_REPAIR=IMPLEMENTED_LOCAL
OBSERVED_WHITESPACE_HARD_FENCE=PASS_LOCAL
VISIBLE_BOUNDARY_JOINED_RULE_INVERSION=PASS_LOCAL
VISIBLE_BOUNDARY_DIRECT_OPTION=ALWAYS_PRESENT_PASS_LOCAL
INTERNAL_JOINED_RULE_INVERSION=PASS_LOCAL
POSITIONAL_PIECE_IDENTITY=PASS_LOCAL
DISTINCT_HOST_TYPE_QUALIFICATION=PASS_LOCAL
POSTERIOR_HOST_SUPPORT_CONSERVATION=PASS_LOCAL
WHOLE_FORM_FALLBACK=LEGAL
SCORER_OBJECTIVE_CHANGED=NO
FROZEN_SANDHI_INVENTORY_CHANGED=NO
FROZEN_M0_CHANGED=NO
FULL_M0_RUN=NO
FULL_M0_AUTHORIZED=NO
FIRST_FAILING_SMOKE_DOCUMENT=6_sastra/3_phil/buddh/nrat_1_u.txt
FIRST_FAILING_SMOKE_LINE=7
FIRST_FAILING_SMOKE_SEGMENT=0
ROOT_CAUSE=DIRECT_VISIBLE_BOUNDARY_OPTION_OMITTED
REMOTE_OPERATIONS_RUN=PREVIOUS_GIT_PUSH_ONLY

The local V2 patch makes every observed space a hard lexical fence without
equating lexical boundary with whitespace: missing spaces still permit latent
boundaries. Joined frozen sandhi surfaces are indexed at every exact visible
split, so `ū + e -> ve` is invertible across `v | e` as well as internally
inside `ve`. Regression coverage includes
`svayaṃbhv ekam -> svayaṃbhū | ekam`.

Reusable-piece identity is `(form, WHOLE|LEFT|RIGHT|INTERNAL)`. Expected count
and score lookups are role-conditioned. Qualification is separate: support for
`(identity, host)` is the sum of outer host-occurrence posterior mass times the
conditional inner expected usage of that identity. Legal membership alone
contributes nothing. Host-keyed support sums back to the ordinary expected
piece count for every observed identity within floating-point tolerance, and
distinct host types are counted only after their aggregated expected usage
reaches `piece_host_support_threshold=1.0`. Multi-phoneme identities require
two qualifying host types by default; singleton identities remain active. One
repeated whole lexical form therefore cannot qualify itself. Whole-form
legality, including the long fallback, remains unchanged.

The fixed scorer formula/hyperparameters, external-sandhi TSV, joint exact
posterior, shared trie, compact/lazy paths, bounded caches, streaming SQLite
reduction, bundle scheduler, topology reuse, and worker scheduling remain the
existing architecture. The necessary role and host-support metadata is routed
through the existing contribution points in those paths; no second DP,
legal-identity Cartesian expansion, four-way duplicated DP, or corpus
occurrence-history materialization was introduced.

Documentation authority for this patch is
`reports/core_methods/reusable_pieces/s1m2_v2_semantic_repair_20260916.md`.
The V1 scientific authority remains
`reports/core_methods/reusable_pieces/s1m2_full_m0_scientific_failure_20260915.md`.

The smoke-list first-failure probe found
`6_sastra/3_phil/buddh/nrat_1_u.txt`, line 7, segment 0:
`dharmam ekāntakalyāṇaṃ rāja n dha rmodayāya te`. The one-phoneme middle
token `n` had no factor because the left and right visible boundaries exposed
only non-transformed grammar options that each consumed it. Ordinary visible
boundaries now always include the direct `0/0` option alongside every legal
sandhi inverse; whitespace remains a hard lexical fence.

No broad real-corpus or performance conclusion is available. The next session
must not launch Full M₀ or a large benchmark merely because the focused
regressions pass.

Focused validation for the posterior-host-support blocker:

- touched modules and direct test files: `py_compile` passed;
- direct piece-model/composed-inference files: 49 passed in 1.21s;
- compact, legacy, compiled-shared, merged-factor, and whole fallback paths
  retain their existing exact inference routes;
- the public model label remains `reusable_pieces_v1` deliberately for current
  config/checkpoint/contract/audit compatibility; a rename should be a
  separately versioned migration.
- visible-boundary candidate regressions: 8 passed in 0.42s, including the
  short-middle-token complete path, `svayaṃbhv ekam`, internal `ve`, and hard
  whitespace fencing;
- the original first failing smoke segment now completes under the exact S1M2
  lazy/composed Pass-1 path with total posterior mass approximately 1 and zero
  merged factors.

NEXT_ACTION=PUBLISH_DIRECT_VISIBLE_BOUNDARY_FIX

Do not run Full M₀, deploy to a VM, or run a representative, stress, RAM, or
runtime benchmark without separate researcher review and authorization.

# CURRENT TASK

DATE=2026-09-20
BRANCH=exp/s1m2-reusable-pieces
STATUS=DIAGNOSTIC_TARGET_LOCALIZATION_V2_VALIDATED_E100_E300_NOT_RUN

Current target-localization repair (2026-09-20): Diagnostic evaluation now
locates each DCS occurrence by source_file + sent_id + id/occ_id, ordered
CoNLL-U surface atoms (multiword ranges count as one), and source-text spans.
It validates top-analysis factor groups against existing visible/internal
boundary source offsets. A split standalone gold token or a merged DCS
multiword range is a scorable nonrecovery; ambiguous range/factor count
mismatches remain unscorable. No predicted lexical string selects the target
factor. Held-out reevaluation is SQLite read-only and writes only versioned
v2 analysis/summary/evaluation-provenance artifacts; original evidence and
training provenance are retained. The bounded E000 held-out preflight (no
training) found 76/80 evaluable and four explicit ambiguous component/factor
alignments. The original 10 predictions/pieces are identical. E100/E300 and
all new evidence-level training remain unrun. Next action is researcher review
of the E000 v2 artifacts, not an automatic pilot launch.

Previous diagnostic handoff follows:

Historical initial probe (superseded by v2 above): The diagnostic-only
S1M2 lexeme evidence probe trains from one UTF-8 surface-sentence file via a
non-M0 CorpusDocument seam in the unchanged exact trainer, then evaluates the
held-out challenge with a read-only SQLite piece scorer and exact composed
inference. The formal M0 manifest/freeze loader and config signature remain
unchanged. Diagnostic provenance records corpus/challenge SHA-256, target,
level, Git SHA, and scientific configuration, with no formal freeze claim.
Target-local exact posterior fields that cannot be losslessly obtained from
the current aggregate reductions are null with reasons; top-1 target metrics
are reported only for uniquely localized single-match sentences. No 18-cell
pilot or real-corpus training had run at that handoff. The later E000 cell
is complete and only its v2 held-out reevaluation is in scope now. Do not
launch Full M0, cloud, or large benchmarks.

Historical S1M2 V2 handoff follows:

TASK_BASE_HEAD=e50e0b21374748367030816c1cfb8818147ba2d6
PREVIOUS_REPAIR_COMMIT=e50e0b21374748367030816c1cfb8818147ba2d6
PREVIOUS_REPAIR_PUSHED=YES
S1M2_V1_SCIENTIFIC_FAILURE=UNCHANGED
S1M2_V2_SEMANTIC_REPAIR=IMPLEMENTED_LOCAL
OBSERVED_WHITESPACE_HARD_FENCE=PASS_LOCAL
VISIBLE_BOUNDARY_JOINED_RULE_INVERSION=PASS_LOCAL
VISIBLE_BOUNDARY_DIRECT_OPTION=ALWAYS_PRESENT_PASS_LOCAL
VISIBLE_NONTRANSFORMED_GRAMMAR_OPTIONS=DEDUPLICATED_TO_DIRECT
INTERNAL_JOINED_RULE_INVERSION=PASS_LOCAL
POSITIONAL_PIECE_IDENTITY=PASS_LOCAL
DISTINCT_HOST_TYPE_QUALIFICATION=PASS_LOCAL
POSTERIOR_HOST_SUPPORT_CONSERVATION=PASS_LOCAL
WHOLE_FORM_FALLBACK=LEGAL
SCORER_OBJECTIVE_CHANGED=NO
SANDHI_TRANSFORMATION_PENALTY=CONFIGURABLE_DEFAULT_0.0
SANDHI_TRANSFORMATION_EVENT_UNIT=ONE_TRANSFORMED_BOUNDARY_EVENT
SANDHI_TRANSFORMATION_RULE_ID_MULTIPLIER=NO
SANDHI_TRANSFORMATION_CONFIG_SIGNATURE=INCLUDED_FOR_S1M2
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

The optional S1M2 scientific parameter
`sandhi_transformation_penalty = gamma` now subtracts `gamma` exactly once for
each `transformed=True` internal or visible inversion event. Internal events
are charged on the lexical transition ending at their boundary node; visible
events are charged only on the preceding factor's outgoing option. Grouped
rule IDs do not multiply the cost. The default is `0.0`, the S1M2 config
signature distinguishes gamma values, and frozen S1M1 payload identity remains
unchanged. No value was tuned.

Documentation authority for this patch is
`reports/core_methods/reusable_pieces/s1m2_v2_semantic_repair_20260916.md`.
The V1 scientific authority remains
`reports/core_methods/reusable_pieces/s1m2_full_m0_scientific_failure_20260915.md`.

The smoke-list first-failure probe found
`6_sastra/3_phil/buddh/nrat_1_u.txt`, line 7, segment 0:
`dharmam ekāntakalyāṇaṃ rāja n dha rmodayāya te`. The one-phoneme middle
token `n` had no factor because the left and right visible boundaries exposed
only non-transformed grammar options that each consumed it. Ordinary visible
boundaries now always include the direct `0/0` option. Transformed sandhi
inverses remain parallel options, while non-transformed grammar matches are
canonicalized to direct rather than retained as duplicate derivations;
whitespace remains a hard lexical fence.

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
- visible-boundary candidate regressions: 8 passed in 0.45s, including the
  short-middle-token complete path, `svayaṃbhv ekam`, internal `ve`, and hard
  whitespace fencing;
- the original first failing smoke segment now completes under the exact S1M2
  lazy/composed Pass-1 path with total posterior mass approximately 1 and zero
  merged factors.

Focused validation for the transformed-event penalty:

- touched production modules and the focused regression file compile;
- the new focused file passes 7 tests, covering gamma zero, exact one- and
  two-event costs, grouped rule IDs, all compact/shared/legacy routes,
  `svayaṃbhv ekam`, `rāja n dha`, CLI/config, and signature separation;
- 8 directly related existing hard-fence, visible/internal inversion, and
  optimized-path parity tests pass.

HISTORICAL_NEXT_ACTION=PUBLISH_TRANSFORMED_SANDHI_PENALTY

Do not run Full M₀, deploy to a VM, or run a representative, stress, RAM, or
runtime benchmark without separate researcher review and authorization.

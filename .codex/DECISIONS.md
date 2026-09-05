# DECISIONS.md

This file records decisions that should not be casually re-litigated in each Codex session. Change it only when the user explicitly changes a research/design decision.

## Frozen corpus and experiment structure

1. M₀ is frozen. Do not reopen corpus QA during core-method work.
2. The `m0` annotated tag must never move.
3. Formal M₀ observation conditions are exactly six:
   - IAST: `surface_word`, `legacy_joined`, `continuous`
   - Devanagari: `surface_word`, `legacy_joined`, `continuous`
4. Each condition will ultimately be trained independently. Do not initialize later conditions from the first trained condition.
5. `IAST + surface_word` is the first formal core-method implementation and calibration anchor; it is not the final selection of a sole S1M1 representation.

## Grammar scope

6. Formal v1 uses the fixed 1218-rule external-sandhi inventory.
7. Do not learn internal sandhi in v1.
8. Do not modify `data/rules/external_sandhi.tsv` in the current implementation task.
9. Fixed grammar licenses/reconstructs candidates; do not add a generic reward for “using sandhi”.

## Boundary semantics

10. Lexical boundary is an abstract structural object.
11. Boundary is not whitespace.
12. Boundary is not literal `#`.
13. Boundary is not apostrophe/avagraha.
14. Boundary is not a Devanagari orthographic sign.
15. `#` may be used only as debug/serialization notation.
16. Visible spacing and lexical structure must remain separate.
17. Whitespace is strong observed evidence, not gold segmentation.

## Representation

18. Raw IAST Unicode strings are not the final linguistic representation.
19. Formal core code must use a script-neutral Sanskrit phonological representation.
20. The core interface remains script-neutral, and formal IAST plus generated-M0 Devanagari frontends map into the same phonological representation.
21. Script-specific observation problems must be fixed in the frontend without introducing divergent scientific hyperparameters.

## Candidate generation

22. The old “any matching substring becomes a sandhi edge” lattice is only a proof-of-concept.
23. Formal candidate generation should prune impossible analyses before statistical learning.
24. Candidate pruning may use observable orthographic cues, phonological legality, the fixed grammar, and exact forward reconstruction.
25. Do not use dictionaries, gold segmentation, morphological analyzers, or pretrained Sanskrit models for candidate pruning in the surface-only experiment.
26. Preserve genuine ambiguity; do not hard-decode early.

## Learning objective

27. The formal learner's main signal is corpus-wide reuse of latent lexical units.
28. Do not use character-string likelihood as the main formal lexical scoring signal.
29. Do not continue building the formal method by patching the toy character n-gram EM prototype.
30. Start with an interpretable unigram latent-lexicon model, not a Transformer.
31. Use soft assignments/posteriors and posterior expected lexical counts.
32. Initialization must not first train an identity-favoring surface character LM.
33. Include an explicit, simple, configurable lexicon-complexity/sparsity pressure against proliferating one-off latent lexical types.
34. The exact v1 complexity formula is not yet theoretically frozen; any choice must be documented as an explicit implementation assumption.
35. Current latent target is unsandhied lexical word-form identity such as `devaḥ | api`.
36. Deeper morphology such as `deva | s` is out of scope for v1.

## Scalability and evaluation

37. Full M₀ processing must be streaming/sharded and bounded-memory.
38. Do not materialize all full-corpus lattices/candidate paths in memory.
39. Do not automatically launch a long full-M₀ run unless explicitly requested.
40. First-run analysis must expose learned structure: latent lexicon, candidate posteriors, boundaries, rule usage, identity-vs-latent mass, ambiguity, and complexity—not only a single loss.

## Deployment and scaling gate

41. Four workers are the measured production sweet spot on the current local Windows host; do not run local 12/16-worker benchmarks after the completed 8-worker negative-scaling result.
42. Local worker scaling must not be extrapolated to a different cloud host. On the Ubuntu cloud host, measure 4 workers first, then 8; consider 12/16 only when each preceding step is scientifically identical, materially faster, and memory-safe.
43. Cloud artifacts, benchmark scratch, input copies, and resource metrics belong on the confirmed 300 GB data filesystem, not the 80 GB system filesystem. Never format a device until its exact identity and emptiness are manually confirmed.
44. Full M₀ remains gated on audited cloud medium scaling, aggregate process-tree memory, storage headroom, and an explicitly recorded user-run command. Do not start it automatically.
45. Raw multi-gigabyte artifacts remain gitignored, but every result that changes a scientific, implementation, performance, scaling, projection, or deployment decision must be promoted into tracked Markdown.
46. Git commit/history is authoritative code identity; GitHub is the publication/collaboration endpoint. Production deployment to core-01 through core-06 uses a clean published local checkout, verified Git bundle over SCP/SSH, exact fetched-SHA checks, and a fast-forward-only remote update. Never deploy a copied working tree or use remote GitHub fetch/pull as the core production path.
47. Non-Git scientific bytes move only through resumable rsync over SSH. Transfers never imply deletion, regeneration, transcoding, or replacement of Git-tracked manifests/rules.
48. `sktlm_bridge.py` is a deterministic control plane, not an autonomous agent: it may run only its fixed status/deploy/transfer/verification/collection workflows and must not expose arbitrary remote shell, package installation, benchmark launch, Git push, or destructive infrastructure actions.
49. Every bridge sync/mutating operation must write a redacted gitignored JSON receipt. Native Windows rsync workflows are unsupported; use WSL/Linux rather than silently falling back to another copy mechanism.
50. Result collection defaults to the small `report` profile. The `scientific` profile excludes `learner.sqlite`; only an explicit `full` profile may retrieve the entire run, and no collection profile deletes remote artifacts or silently overwrites an existing local collection.
51. Logical machine identity (`core-01`, etc.) is stable and separate from run identity and temporary worker role; real host/IP/SSH values remain only in ignored local bridge configuration.
52. The bridge preserves legacy single-host configuration. When multiple host profiles are configured, result collection requires an explicit profile and an exact tracked registry match before SSH; receipts record both logical machine/profile and actual remote target.
53. `configs/cloud/experiment_registry.toml` is the tracked machine/run assignment record. It must not contain real addresses or credentials, and RUNNING/PENDING rows must never acquire fabricated result values.
54. `reports/core_methods/latent_lexicon/cloud_scaling_checkpoint_20260831.md` is authoritative for the current cloud scaling state; deployment instructions and earlier stage checkpoints are preserved as procedural/historical provenance.
55. Cloud medium scaling is closed: 8 workers are the frozen production setting for the next full-M0 stage because w8 was approximately 12.8% faster than the w16 runner-up and therefore satisfied the preregistered >=10% direct-winner rule.
56. Do not run a cloud medium tie-break or additional medium worker-scaling benchmark. The accepted w4/w8/w12/w16 runs are scientifically equivalent across the six canonical artifacts; worker count affects accepted runtime/resource behavior, not scientific output.
57. The four unrestricted IAST surface_word full-M0 replicas at 8 workers completed successfully and are byte-identical across all six canonical scientific artifacts.
58. The five remaining unrestricted representation cells were launched at scientific checkpoint 375178ba50bd1a1644d65525907692b31413b33d. Their outcomes supersede the dated RUNNING state: IAST `legacy_joined` and Devanagari `surface_word`/`legacy_joined` completed; IAST `continuous` was scientifically excluded and Devanagari `continuous` was execution-incomplete after manual termination.

## Optional fixed-vocabulary comparison condition

59. `--vocab-budget K` is an optional condition; omission (`None`) preserves the unrestricted latent-lexicon-v1 configuration signature and scientific behavior.
60. Vocabulary capacity counts distinct latent `form_key` identities. Surface realizations and external-sandhi rules consume no vocabulary slots.
61. Every constrained vocabulary includes all 50 singleton `Phoneme` base units. The remaining `K-50` capacity is selected once after neutral Pass 1 by `expected_count DESC, form_key ASC`, then frozen for all later passes and inspection.
62. A nonselected multi-phoneme form has no independent lexical parameter. It deterministically projects to its constituent singleton base tokens for scoring, expected counts, and decoded output; pruned Pass-1 counts use the same phoneme-multiplicity projection.
63. Resume must load and validate the durable frozen vocabulary and allowed-key SHA-256; it must never reselect from later-pass counts.

## Research stage and milestone nomenclature

64. `M₀` is the reserved name of the frozen common experimental substrate: corpus, exactly six formal observation representations, and shared provenance/evaluation contracts. It is not an `SxMy` milestone or a latent-model name.
65. `full-M₀` means full frozen-corpus extent for one M₀ representation condition. It does not mean that the model itself is “M0”. Preserve historical `full_m0_*` IDs, report filenames, `stage01_checkpoint_20260831.md`, and branch `exp/m0-core-methods` as provenance.
66. A Stage is a major research phase. `M1`, `M2`, and optional `M3` are ordered scientific milestones within that Stage, and milestone numbering restarts at `M1` for each new Stage. `v1` remains an implementation/version label, not a Stage or Milestone synonym.
67. Capacity calibration is closed. K=16,384 and K=32,768 are appendix sensitivity conditions in the same strong projection-pressure regime, not candidate endpoints of a natural vocabulary sweet spot.
68. Do not add K values, reopen a capacity grid, or execute the previously contemplated 18-cell matrix. Fixed-K evidence remains calibration provenance rather than an active representation-gate condition.
69. The S1M1 representation gate is closed under the explicit four-AVAILABLE/two-typed-N/A protocol; continuous-cell partial learner states are not missing-at-random values and never enter quantitative aggregation.
70. Formal S1M1 aggregation, association microanalysis, scientific interpretation, and selective archival are complete. S1M1 is frozen. The deletion-readiness gate was `READY`, not deletion authority. After that checkpoint the researcher separately authorized and manually removed exactly its 12 `SAFE_TO_DELETE_REGENERABLE` files; current read-only reconciliation finds all 12 absent. Do not recreate them or infer authority to delete anything else.
71. Stage 1 assumes only the known/fixed external-sandhi grammar. S1M1 diagnoses flat lexical word-form identity; S1M2 induces reusable untyped pieces p1...pk whose exact concatenation equals the grammar-licensed lexical form u. S1M2 permits segmentation/composition but no new rewrite and predeclares no stem, suffix, root, lemma, POS, paradigm, or grammatical-feature roles.
72. An optional M3 in any Stage requires independent scientific semantics and a new scientific claim. Performance optimization, caching, implementation rewrites, worker scaling, and routine tuning do not qualify; absent such a claim, proceed to the next Stage.
73. Stage 2 learns the realization grammar before using it for full-corpus latent analysis. Stage 3 removes the language-specific rule prior and progresses toward joint latent-identity/realization discovery; detailed future supervision contracts remain unfrozen until explicitly designed.

## Future research hypothesis (not frozen)

Systematic-gap allomorph induction is a later-stage roadmap hypothesis, not an
S1M2 requirement or current implementation decision. It may eventually use
posterior-predictive missing forms, distributional/compositional replacement,
and explicit complexity costs to test latent allomorph families without
predeclaring Sanskrit grammatical roles or a unique underlying form.

## Reproducible environments

74. pyproject.toml remains install-oriented rather than globally exact-pinned. Each formal paper/release experiment should capture its actual Python, OS/machine, key-package, Torch/CUDA, Git, and installed-distribution environment as run/release provenance (environment.json plus deterministic requirements-freeze.txt).
75. Generic representation analysis declares its cell universe separately from supplied artifacts. Only `AVAILABLE` cells enter scientific aggregation; all other declared statuses remain explicit N/A, while optional runtime/termination evidence stays separate from science.
76. Missing scientific input is allowed only through an explicit N/A status. Any supplied cell remains subject to fail-closed provenance, configuration, completion, schema, artifact, and hash validation.
77. Artifact inventory is read-only and deletion readiness is evidence-based. The repository tooling may report `PENDING`, `RETAIN`, `SAFE_TO_DELETE_REGENERABLE`, or `NOT_SAFE`, but it must not implement or execute deletion.
78. The final S1M1 cell universe is four complete scientific cells plus two typed N/A cells: IAST `continuous` is scientifically excluded because ordinary space deletion is non-injective, and Devanagari `continuous` is scientifically valid but execution-incomplete. Neither partial learner state may enter scientific aggregation.
79. The derived M0-prime IAST-continuous representation uses frozen M0 Devanagari `continuous` as its sole source. It renders lexical diphthongs `/ai/` and `/au/` as `ē` and `ō`, reserves `ai`/`au` for separate `a+i`/`a+u`, renders lexical aspirates with modifier `ʰ`, and reserves ordinary `kh` ... `bh` for plain consonant+`h` sequences. Frozen M0 remains unchanged; M0-prime has its own manifest, hashes, and provenance. The formal 240-document derivation is `VALID` at manifest SHA-256 `3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`.
80. Formal four-cell/two-N/A aggregation and the selected association-level follow-up are validated. The selective archival/deletion-readiness/final-audit sequence is complete and the S1M1 freeze is closed; every completed-cell SQLite database was not required.
81. Across the four completed controlled cells, spacing effect is substantially larger than script effect. `surface_word` is scientifically identical across scripts except character accounting, `legacy_joined` has only negligible script residuals, and the large spacing effects replicate across both scripts.
82. Removing visible spacing sharpens the posterior while worsening lexicon economy through context-specific over-long lexicalization under the current flat lexical objective. Posterior sharpness alone is not a sufficient lexical or morphological quality criterion; visible spacing is evidence/regularization, not a gold lexical boundary.
83. S1M1 scientific analysis and selective archival are complete. Its current state is `SCIENTIFIC_ANALYSIS_COMPLETE`, `ARCHIVAL_COMPLETE`, `DELETION_GATE_READY`, and `FROZEN`; SQLite-derived association state is supplementary direct microscopic evidence rather than an input required to validate the formal representation analysis.
84. `notes/**` is strictly local-only. Codex may read, inspect, or search it when relevant, but must never modify, create, move, rename, delete, copy, overwrite, track, stage, commit, restore, checkout, or force-add anything under `notes/`, and must never weaken ignore/tracking policy to make it trackable.
85. S1M1 SQLite retention is selective: retain Devanagari `surface_word` raw `learner.sqlite`, its non-empty WAL if present, and compact scorer/association state; retain only compact scorer/association state for Devanagari `legacy_joined`; require no SQLite microstate archival for the two completed IAST cells because the matched-spacing script effect is negligible. `surface_word` is the boundary-visible microscopic reference, not the preferred downstream representation, while `legacy_joined` is a completed diagnostic failure/stress condition.
86. IAST and Devanagari `continuous` partial databases are excluded from the completed training-final SQLite retention contract. Their existing representation, runtime, termination, and scalability evidence remains retained.
87. Repository tooling and Codex may classify scientific artifacts only as `PENDING`, `RETAIN`, `SAFE_TO_DELETE_REGENERABLE`, or `NOT_SAFE`, matching the generic artifact-inventory vocabulary. `NOT_READY` is reserved for gate-level status. Tooling and Codex must never delete artifacts; every deletion requires separate manual researcher authority.
88. Direct association-level evidence for the S1M1 failure mechanism is `YES`, with a weighting qualification: expected-count and association-mass weighting show substantially narrower `legacy_joined` contexts and surfaces, and the long/low-count inventory proliferates strongly, but type-weighted context top-1 concentration does not move uniformly in that direction.
89. The downstream corrected representation substrate is five unchanged valid M0 cells plus derived M0-prime IAST `continuous`. Original M0 IAST `continuous` remains `NA_SCIENTIFICALLY_EXCLUDED` and is never silently overwritten or relabeled. Consumers opt into M0-prime through its explicit manifest and `iast_m0_prime` frontend.

## S1M2 reusable-piece semantics and P1c boundary

90. S1M2 adds untyped reusable script-neutral `PhonologicalForm` pieces below the S1M1 latent lexical form. Every complete piece path concatenates exactly to the grammar-licensed lexical form; S1M2 uses no piece-level rewrite, morphology label, gold segmentation, or Sanskrit-specific boundary/suffix inventory.
91. The P0 legal piece set contains every singleton, every contiguous slice through `max_piece_length`, and the whole lexical form even when longer. Whole-form memorization and all-singleton atomization remain genuine competitors.
92. The P0 independent-boundary prior is renormalized exactly over its restricted legal segmentation DAG. With neutral piece scores, every lexical form has zero normalized piece-model log score regardless of length or segmentation multiplicity.
93. P0's count-based piece energy is the declared `log P(p) - lambda * (kappa + beta * len(p)) * log(1 + 1 / (tau + count(p)))`. It is the reference energy/reweighted-MDL semantics, not a newly established normalized generative distribution over all variable-length lexical forms.
94. P0 remains a tiny exact oracle. It is not the production shared/composed engine, a streaming trainer, or authority for full-corpus S1M2 execution.
95. P1a production fixed-pass probability is `(count_A(p) + alpha H(p)) / (N + alpha)`, where `H(p)=q(1-q)^(len(p)-1)|Sigma|^(-len(p))` is a normalized countable base measure over the complete script-neutral phoneme inventory. Inactive pieces remain legal and scoreable without an enumerated vocabulary denominator.
96. During one pass the finite active piece map is fixed. Between passes, persistent parameters are limited by default to observed singletons and pieces with positive posterior support in at least two observed lexical-form occurrences. This is a parameter-state update, not candidate pruning or a sandhi-use reward.
97. P1b stores existing M1 boundary options and internal nodes without persistent lexical-edge tuples. Requested spans reconstruct the exact underlying phoneme sequence and existing boundary/rule/identity metadata; its materialization adapter is comparator-only.
98. P1c must implement exact shared/composed piece inference over lazy spans and pass P0 plus materialized-outer oracle-equivalence gates. It must not build an independent P0 lattice per lexical form, use a beam, hard-decode early, or change fixed Stage-1 external-sandhi grammar semantics.
99. P1c readiness authorizes only P1c implementation and tiny/cheap equivalence validation. It does not authorize full trainer integration, a full-corpus S1M2 experiment, S1M2 scientific conclusions, S1M3, Stage 2, or downstream tuning.
100. P1c production inference uses direct exact position DP over the unchanged P0 legal piece support and composes its marginalized form scores/conditional piece counts with P1b lazy spans and outer factors. It must not construct per-form P0 lattices or persistent lexical-edge rows. Piece-score and per-form reuse is pass-local, LRU-bounded by entries and estimated bytes, and invalidated by constructing a fresh engine after each piece-parameter update; cache behavior is engineering-only and cannot alter scientific results.
101. S1M2 occurrence support counts distinct observed lexical-form interval/form identities with positive joint posterior mass (default epsilon zero), deduplicating alternative derivations and piece multiplicity within one occurrence. Expected piece counts retain multiplicity separately. This support controls only the finite between-pass active parameter map; it never removes legal candidates.
102. The integrated trainer keeps cache/store work counters in engineering timing telemetry rather than scientific iteration history because interruption boundaries legitimately change cache reuse. Resume equivalence is defined over deterministic scientific state/artifacts, which are byte-identical in the bounded gate. Adding S1M2 support must not change an existing S1M1 configuration identity; S1M2-only fields are omitted from S1M1 payloads.

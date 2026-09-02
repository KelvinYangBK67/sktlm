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
58. The five remaining unrestricted representation cells were manually bundle-deployed and launched at scientific checkpoint 375178ba50bd1a1644d65525907692b31413b33d on core-01 through core-05 and are RUNNING; core-06 remains standby. No completion, audit, performance, or scientific result may be inferred before natural completion and final audit.

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
69. The active pre-S1M1 gate is unrestricted training for all six M₀ representations. Accepted IAST surface_word replicas supply one cell; the other five are the RUNNING assignments in the dated 2026-09-01 launch checkpoint.
70. Baseline/tokenizer comparison, common evaluation, S1M1 specification freeze, aggregation, and paper-facing output work remain deferred until the unrestricted six-representation gate completes.
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

## S1M1 post-hoc archival reduction

75. The frozen preregistered S1M1 gate and the later S1M1 post-hoc archival reduction are separate scientific objects. The archive may describe completed audited collections but must not alter the frozen protocol, formal six-cell aggregator, gate criteria, or gate conclusion.
76. Full S1M1 archival reduction must remain local, read-only, fail-closed, streaming/bounded-memory, and output-only into a fresh directory. Source bytes and the final collection audits are retention identities, not mutable inputs.
77. Archive outputs must distinguish exact streaming quantities from deterministic bounded approximations and from learner-produced bounded top-k inspection quantities. Full-tail support overlap is represented by bounded sketches rather than a giant temporary database or in-memory support set.

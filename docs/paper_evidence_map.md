# Paper evidence map

This map connects likely paper claims or sections to the tracked repository
record. It is not a paper draft, a new result, or permission to strengthen a
claim. Status describes the evidence available at this documentation
checkpoint. S1M2 Round 2 has a formal failure and engineering evidence, but no
final scientific result.

## Research design and substrate

| # | Likely claim or subsection | Authoritative tracked source | Optional support | Status | Claim boundary |
|---:|---|---|---|---|---|
| 1 | Research question and Stage/Milestone design | [Research roadmap](research_roadmap.md) | [Top-level research map](../README.md#research-documentation) | COMPLETE | The roadmap defines the program; later stages remain planned rather than demonstrated. |
| 2 | GRETIL source provenance and canonical identity | [Canonical-corpus contract](methodology/canonical_corpus.md) | [Cleaning provenance index](../reports/cleaning/README.md), [data licensing](../DATA_LICENSE.md) | FROZEN | Paths, hashes, membership, and freeze identity establish technical provenance; they are not a per-text bibliographic catalogue. |
| 3 | Cleaning, inclusion/exclusion, and final freeze | [Cleaning provenance index](../reports/cleaning/README.md) | [Cleaning workflow](workflows/corpus_cleaning.md), [final closure](../reports/cleaning/pre_m0_single_consonant_final_closure.md) | FROZEN | Use the final 240-document state; older 246-document reports are historical ancestors. |
| 4 | M₀ six-representation substrate | [Representation contract](methodology/representations.md) | [Formal construction/validation report](../reports/representations/README.md) | FROZEN | The six M₀ datasets remain frozen even though original IAST `continuous` was later scientifically excluded. |
| 5 | Pre-S1M1 calibration and capacity/scaling choices | [Pre-S1M1 calibration checkpoint](../reports/core_methods/latent_lexicon/pre_s1m1_calibration_checkpoint_20260901.md) | [Historical latent-lexicon index](../reports/core_methods/latent_lexicon/README.md) | HISTORICAL | Calibration explains the route to S1M1; it is not the S1M1 result or a reusable-piece conclusion. |

## S1M1 and the corrected continuous substrate

| # | Likely claim or subsection | Authoritative tracked source | Optional support | Status | Claim boundary |
|---:|---|---|---|---|---|
| 6 | Spacing effect is substantially larger than script effect for flat lexical identity | [S1M1 final checkpoint](../reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md) | [Non-continuous 2×2 checkpoint](../reports/core_methods/latent_lexicon/noncontinuous_representation_checkpoint_20260901.md) | FROZEN | The formal result is four AVAILABLE cells plus two typed N/A cells, not a completed six-cell estimate. |
| 7 | Long/low-count/narrow-association failure mechanism | [Direct association-level evidence](../reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md#direct-association-level-evidence-yes) | [Association workflow](workflows/association_specialization_analysis.md) | FROZEN | The population/mass-weighted mechanism is supported; not every type-weighted concentration statistic moves uniformly. |
| 8 | Continuous-cell limitations | [S1M1 continuous-cell results](../reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md#continuous-cells-two-different-results) | [Final analysis plan](../reports/core_methods/latent_lexicon/s1m1_final_analysis_plan.md) | FROZEN | IAST `continuous` is scientifically excluded for non-injectivity; Devanagari `continuous` is scientifically valid but execution-incomplete. Neither partial learner state enters aggregation. |
| 9 | M₀′ repairs the downstream IAST-continuous encoding | [M₀′ formal checkpoint](../reports/core_methods/latent_lexicon/m0_prime_formal_checkpoint_20260905.md) | [M₀′ workflow](workflows/m0_prime.md) | COMPLETE | M₀′ is a deterministic derived substrate from frozen M₀ Devanagari `continuous`; it does not alter or relabel M₀ and is not an S1M2 result. |

## S1M2 reusable pieces

| # | Likely claim or subsection | Authoritative tracked source | Optional support | Status | Claim boundary |
|---:|---|---|---|---|---|
| 10 | S1M2 scientific contract: reusable untyped pieces with exact concatenation | [Research roadmap](research_roadmap.md#s1m2--reusable-untyped-compositional-pieces) | [S1M2 report index](../reports/core_methods/reusable_pieces/README.md) | METHOD COMPLETE / SCIENCE BLOCKED | No stem/suffix/root labels, learned internal rewrite, gold morphology, or sandhi-use reward is introduced. Round 2 does not supply a final scientific result. |
| 11 | P0 exact reference semantics | [P0 reference checkpoint](../reports/core_methods/reusable_pieces/s1m2_p0_reference_and_profiling.md) | [S1M2 report index](../reports/core_methods/reusable_pieces/README.md#p0--exact-reference-semantics) | COMPLETE | P0 is the numerical oracle and tiny fitting path, not the production full-corpus engine. |
| 12 | P1a scoring and P1b lazy lexical spans | [P1a/P1b checkpoint](../reports/core_methods/reusable_pieces/s1m2_p1ab_checkpoint.md) | [Historical P1c readiness](../reports/core_methods/reusable_pieces/s1m2_p1c_readiness_20260905.md) | COMPLETE | The checkpoint establishes fixed-pass scoring and lazy candidate representation; its statement that P1c remained open is historical. |
| 13 | P1c exact shared/composed inference | [P1c closure](../reports/core_methods/reusable_pieces/s1m2_p1c_closure_20260905.md) | [P0 reference checkpoint](../reports/core_methods/reusable_pieces/s1m2_p0_reference_and_profiling.md) | COMPLETE | Equivalence and bounded-cache contracts establish exact implementation semantics, not corpus-scale scientific success. |
| 14 | Streaming trainer, resume, and serial/parallel equivalence | [Trainer integration checkpoint](../reports/core_methods/reusable_pieces/s1m2_trainer_integration_20260905.md) | [P1c closure](../reports/core_methods/reusable_pieces/s1m2_p1c_closure_20260905.md) | COMPLETE | Integration and deterministic bounded tests do not authorize or substitute for a full-corpus S1M2 result. |
| 15 | Continuous profiling and exact optimization | [Continuous benchmark/profiling/optimization record](../reports/core_methods/reusable_pieces/s1m2_continuous_benchmark_definition_20260905.md) | [Compact evidence directory](../reports/core_methods/reusable_pieces/evidence/) | COMPLETE ENGINEERING HISTORY | Treat optimization results as engineering evidence, not a final scientific conclusion. |
| 16 | Round 2 worker scaling, inspection bundling, and exact-science gate | [Round 2 closure](../reports/core_methods/reusable_pieces/s1m2_round2_closure_20260910.md) | [Execution-bundle scheduler checkpoint](../reports/core_methods/reusable_pieces/s1m2_execution_bundle_scheduler_20260909.md) | FORMAL FAIL / ENGINEERING CLOSED | Worker-count artifacts are deterministic and 12 workers is the engineering preference, but stress candidate truncation prevents a formal PASS or production winner. |

## Later stages

| # | Likely claim or subsection | Authoritative tracked source | Optional support | Status | Claim boundary |
|---:|---|---|---|---|---|
| 17 | Later learned-grammar and language-general research program | [Stage 2 and Stage 3 roadmap](research_roadmap.md#stage-2-learned-realization-grammar) | None | N/A | These are planned research stages and hypotheses, not completed methods or evidence-backed results. |

## Use rule

When drafting, cite the authoritative source for the sentence being written.
Use supporting sources for mechanism, implementation detail, or provenance,
and retain every caveat above. Generated `artifacts/` may reproduce or inspect
a result, but they do not replace the tracked narrative when a report exists.

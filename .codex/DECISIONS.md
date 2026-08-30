# DECISIONS.md

This file records decisions that should not be casually re-litigated in each Codex session. Change it only when the user explicitly changes a research/design decision.

## Frozen corpus and experiment structure

1. M₀ is frozen. Do not reopen corpus QA during core-method work.
2. The `m0` annotated tag must never move.
3. Formal M₀ observation conditions are exactly six:
   - IAST: `surface_word`, `legacy_joined`, `continuous`
   - Devanagari: `surface_word`, `legacy_joined`, `continuous`
4. Each condition will ultimately be trained independently. Do not initialize later conditions from the first trained condition.
5. First formal core-method condition: `IAST + surface_word`.

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
20. The current task implements/exercises only the IAST frontend, while keeping the core interface ready for a later Devanagari frontend.
21. Do not implement the complete Devanagari frontend in the current task.

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

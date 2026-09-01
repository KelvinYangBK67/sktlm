# Research roadmap: latent identity under surface variation

## Research question

Sanskrit sandhi is the project's primary testbed because it makes the central
problem unusually visible, but the general claim is broader than sandhi
learning. A latent identity may have several context-conditioned surface
realizations:

`a -> {b, c, d, ...}`

The research asks whether a learner can:

1. determine when different surface forms should share one latent identity;
2. distinguish lexical memorization from productive context-conditioned
   realization;
3. decide when recurring variation warrants a reusable realization or
   transformation grammar; and
4. learn an appropriate amount and kind of grammar for a language, without
   assuming that every language has Sanskrit-style sandhi.

The preferred general vocabulary is *latent identity*, *surface realization*,
*context-conditioned realization*, *realization/transformation grammar*, and
the *lexicon–grammar trade-off*. Sanskrit-specific experiments and rule
descriptions continue to use *sandhi* precisely.

## Nomenclature

### M₀ is the shared experimental substrate

`M₀` is a reserved name for the frozen common benchmark substrate. It is not
an `SxMy` milestone and it is not the name of the latent model. M₀ includes:

- the frozen corpus;
- exactly six formal observation representations:
  - IAST: `surface_word`, `legacy_joined`, `continuous`;
  - Devanagari: `surface_word`, `legacy_joined`, `continuous`;
- shared provenance and evaluation contracts; and
- the common experimental substrate reused by later methods.

Accordingly, `full-M₀` means a run over the full frozen M₀ corpus for one
representation condition. It does **not** mean that the model itself is “M0”.

### Stages and milestones

A **Stage** is a major research phase. `M1`, `M2`, and optional `M3` are
ordered scientific milestones or substages *within that Stage*. Milestone
numbering restarts at `M1` when a new Stage begins; `M` is not a permanently
increasing model-family number across stages.

Names such as `v1` remain implementation/version labels. They do not carry
Stage or Milestone semantics.

## Current position: unrestricted representation gate

Pre-S1M1 VM and vocabulary-capacity calibration is closed. IAST +
`surface_word` remains the implementation/deployment anchor, but it is not
the sole representation. Four unrestricted replicas established cross-VM
scientific equivalence; their result supplies that one cell of the current
six-representation gate.

The unrestricted lexical support is approximately 19.07 million word-form
identities. Expected-count mass reaches 90%, 95%, 99%, 99.9%, and 99.99% only
at approximately 1.027M, 1.493M, 2.084M, 2.875M, and 3.893M identities. This
million-scale long tail is evidence about the limitations of a flat
whole-form/near-whole-form hypothesis class under the fixed sandhi grammar.

K=16,384 and K=32,768 mainly induce atomization and phoneme fallback under
high compression pressure. That pressure is not morphology. These runs remain
capacity-stress and appendix sensitivity evidence only: do not add new K
values, search for a vocabulary sweet spot, or run a fixed-K 18-cell matrix.

The active gate is the unrestricted learner across all six M₀
representations. Five new cells are currently running at the exact frozen
representation-gate checkpoint; no result is inferred until natural
completion and final audit.

## Entry path to S1M1

After pre-S1M1 calibration closes—and assuming VM differences are negligible—
the next scientific gate is one unrestricted run for each of the six M₀
representations:

- IAST + `surface_word`;
- IAST + `legacy_joined`;
- IAST + `continuous`;
- Devanagari + `surface_word`;
- Devanagari + `legacy_joined`;
- Devanagari + `continuous`.

This gate tests script neutrality as well as spacing-condition behavior. For
the same spacing condition, the IAST and Devanagari runs should be compared on
latent behavior, learned lexical support, identity/latent mass, ambiguity,
grammar usage, segmentation/reconstruction diagnostics, and other common
scientific outputs. Mapping both scripts into the same script-neutral
representation should yield substantially consistent core behavior.

If the comparison exposes a script- or orthography-specific problem, fix the
Devanagari frontend first. Change shared model/scoring parameters only for a
shared scientific problem. Do not manufacture agreement with divergent
IAST-specific and Devanagari-specific scientific hyperparameters.

Only after this six-representation unrestricted gate and any necessary
frontend/shared adjustment should the S1M1 scientific specification freeze.
The accepted unrestricted cells—not a fixed-K expansion—will define the
primary representation evidence. K16/K32 remain appendix stress evidence.

Baseline/tokenizer comparison, common evaluation, paper-facing S1M1
orchestration, aggregation, and tables/figures are deliberately deferred until
the unrestricted gate completes and the S1M1 specification freezes. Only then
should the project implement:

    declarative matrix -> per-cell provenance -> audit -> aggregation -> tables/figures

## Stage 1: known realization grammar

Stage 1 supplies the known/fixed external-sandhi grammar.

### S1M1 — lexical word-form identity

The latent target is lexical word-form identity. Surface realization and
latent lexical identity are separated. The central question is:

> Given a known realization grammar, can the model unify multiple surface
> realizations of one lexical identity without lexicalizing every surface
> accident?

### S1M2 — reusable untyped compositional pieces

S1M2 moves from flat whole-form identity to reusable compositional sharing:

    x -> u -> p1 ... pk
    concat(p1 ... pk) = u

Here x is the observed surface, u is a lexical form licensed/reconstructed by
the frozen external-sandhi grammar, and p1...pk are reusable pieces induced by
the learner. Segmentation and composition are free, but rewrite is not: the
pieces must concatenate exactly to u.

Every learned piece belongs to one untyped V_piece inventory. The model does
not predeclare stem, suffix, root, ending, lemma, POS, paradigm, or grammatical
feature roles. Legal analyses include:

    gaccha|ti
    gacch|a|ti

Either is acceptable when its concatenation exactly equals u. The milestone
does not require decomposition to a traditional or historical root analysis.
For example, gam|a|ti is unavailable when the frozen grammar does not license
a gam -> gacch realization.

Stage 1's only external linguistic supervision is the frozen external-sandhi
table. It introduces no gold morpheme boundaries, stem/suffix labels, paradigm
tables, POS, lemma, morphological analyzer, TransLIST/gold segmentation,
Sanskrit-specific suffix inventory or morphological prior, or newly learned
internal morphophonological rewrite rules.

### S1M3 — optional scientific extension

Open S1M3 only if S1M2 results support additional scientific semantics and a
new claim. It may investigate generic latent hierarchy or generic latent roles,
but must not predeclare Sanskrit stem/suffix/root categories. Performance work
and routine tuning do not qualify. If S1M2 is sufficient, close Stage 1 and
proceed directly to Stage 2.

## Stage 2: learned realization grammar

Stage 2 removes the assumption that the external-sandhi grammar is a fully
given gold object. Its precise supervision contract will be frozen when Stage
2 is formally designed; this roadmap does not pre-commit to undecided paired
data or supervision details.

### S2M1 — learn the grammar

Treat machine sandhi/realization-grammar learning itself as the research
object: can the learner recover a grammar sufficient to describe productive
surface alternations?

### S2M2 — use the learned grammar

Use the grammar learned in S2M1 for full-corpus latent learning and test
whether it can support the latent-identity learning that Stage 1 performed
with a fixed grammar:

`learn grammar -> use learned grammar -> rerun full-corpus latent analysis`

### S2M3 — optional scientific extension

As in Stage 1, open M3 only for genuinely new scientific semantics. Otherwise
proceed directly to Stage 3.

## Stage 3: remove the language-specific rule prior

### S3M1 — induce an explicit grammar without listed Sanskrit rules

Provide no pre-enumerated Sanskrit sandhi rules, while retaining the weak
structural premise that a systematic context-conditioned alternation exists
and an explicit transformation/realization grammar should be induced:

`corpus -> induced transformation grammar -> full-corpus latent analysis`

### S3M2 — joint latent identity and realization discovery

Remove even the strong premise that the language must contain sandhi. Allow
only that systematic context-conditioned transformations *may* exist. The
learner must jointly decide whether a transformation grammar is needed, which
variation belongs in that grammar, which variation remains lexical, and which
surface forms share latent identity. This is the intended “previously unknown
language” abstraction.

### S3M3 — optional cross-lingual stress test

If opened, apply the S3M2 method as unchanged as practical to another language
to test language-general behavior. English is a useful candidate: the learner
might connect variation such as `entity` / `entiti-` without hallucinating a
Sanskrit-style external-sandhi system at corpus scale. The question is not
whether English “has sandhi”, but whether the learner infers the appropriate
amount and type of realization grammar for each language.

## Future hypothesis: systematic-gap allomorph induction

This is a later-stage research hypothesis, not a frozen S1M2 requirement and
not implemented now. Once a learner has a productive compositional baseline,
posterior-predictive expected-but-missing forms may provide negative evidence.
For example, a learned gacch- plus productive -ta pattern may strongly expect
an unattested *gacchta while gata repeatedly occupies the corresponding
distributional/compositional niche.

A future model could compare an accidental-gap hypothesis against a shared
latent-family/allomorphic-realization hypothesis using generic evidence:
systematic gaps, MDL/Occam compression, complementary distribution,
distributional/contextual similarity, shared compositional neighborhoods,
consistent niche replacement, and an explicit complexity cost for exception
or allomorph rules.

The target may be a latent family such as {gacch-, gam-, ga-, gan-} without
declaring gam the unique underlying form. The gam/gacch relation is a later
allomorph-family stress test, not a gold answer S1M2 must recover. Any learned
rewrite or allomorphic realization belongs to a later explicitly frozen stage,
outside current S1M2's exact-concatenation contract.

## Historical naming and provenance

Existing names—including branch `exp/m0-core-methods`, `full_m0_*` run IDs,
historical report filenames, and `stage01_checkpoint_20260831.md`—remain
unchanged. They are provenance. In those records, “Stage 01” denotes the
historical latent-lexicon/core-method work line, and “full-M₀” denotes corpus
extent. Neither label retroactively declares a final S1M1 milestone.

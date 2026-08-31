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

## Current position: pre-S1M1 calibration

The current full-corpus latent-lexicon work is pre-S1M1 infrastructure and
capacity calibration, not the final S1M1 evidence package.

`IAST + surface_word` has served as the implementation and deployment anchor
for the formal latent algorithm, exact inference, full-corpus streaming,
checkpoint/resume safety, deterministic multiprocessing, performance and
cloud scaling, and fixed-vocabulary-budget implementation. This history does
not select `IAST + surface_word` as the only final S1M1 representation.

The current calibration program answers two questions:

### A. VM equivalence

Unrestricted replicas test whether VM identity produces scientifically
meaningful differences. If the scientific outputs are equivalent, later VMs
can be assigned to different representation conditions without replicating
every condition across many machines.

### B. Vocabulary-capacity calibration

Fixed budgets `K=16,384` and `K=32,768` are the current candidate `K1` and
`K2` conditions. Unrestricted effective lexical support, posterior-mass
concentration, segmentation/identity behavior, and constrained results should
jointly determine whether those values need one evidence-based adjustment
before S1M1 freezes. After the S1M1 specification is frozen, the final matrix
must not change K while it is being run.

Calibration runs remain valuable provenance and calibration evidence, but are
not retroactively relabeled as final S1M1 cells.

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
adjustment should the S1M1 specification freeze. The final matrix is then:

`6 M₀ representations × {unrestricted, K1, K2} = 18 scientific cells`

All 18 cells must use the same frozen S1M1 scientific specification. These 18
cells—not the preceding calibration runs—form the final Stage 1 / Milestone 1
evidence package.

## Stage 1: known realization grammar

Stage 1 supplies the known/fixed external-sandhi grammar.

### S1M1 — lexical word-form identity

The latent target is lexical word-form identity. Surface realization and
latent lexical identity are separated. The central question is:

> Given a known realization grammar, can the model unify multiple surface
> realizations of one lexical identity without lexicalizing every surface
> accident?

### S1M2 — reusable stem/morpheme identity

The external-sandhi grammar remains known/fixed, while the latent target moves
to a reusable surface-realizable stem or morpheme level, for example:

- `gaccha | ti`;
- `gaccha | nti`;
- `deva | s`.

The planned scope stops there. It does not automatically extend to
`gam | a | ti`, abstract feature bundles such as `<NOM.SG>`, or historical/PIE
reconstruction; any such extension requires a later explicit decision.

### S1M3 — optional scientific extension

Open S1M3 only if S1M2 leaves a direction with independent scientific
semantics and a new scientific claim. Performance optimization, caching,
implementation rewrites, worker scaling, and routine hyperparameter tuning do
not constitute a milestone. If no such extension exists, Stage 1 closes at
S1M2 and the project proceeds directly to Stage 2.

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

## Historical naming and provenance

Existing names—including branch `exp/m0-core-methods`, `full_m0_*` run IDs,
historical report filenames, and `stage01_checkpoint_20260831.md`—remain
unchanged. They are provenance. In those records, “Stage 01” denotes the
historical latent-lexicon/core-method work line, and “full-M₀” denotes corpus
extent. Neither label retroactively declares a final S1M1 milestone.

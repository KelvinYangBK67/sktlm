# S1M1 final analysis plan

**Status:** FROZEN analysis specification.

This document defines the final scientific reduction and comparison contract
for Stage 1 Milestone 1 (S1M1). The implementation remains provisional until
it has been exercised successfully on the complete real S1M1 collections and
is frozen together with the S1M1 result release.

This plan supersedes the use of the earlier six-representation gate and
post-hoc archival reducer as the final S1M1 analysis implementation. Those
implementations remain historical midpoint/diagnostic checkpoints in Git.

## 1. Scientific scope

S1M1 evaluates flat latent lexical word-form identity under the frozen M0
corpus, representation substrate, and fixed external-sandhi grammar.

M0 itself remains frozen. Its historical representation inventory still
contains six observation conditions. This final S1M1 analysis changes no M0
corpus bytes, representation files, manifests, freeze metadata, or rule
inventory.

The final S1M1 analysis asks:

1. whether reusable latent lexical identities emerge;
2. how concentrated and economical the induced lexical inventory is;
3. how strongly learned forms recur across surface realizations and contexts;
4. how the identity/latent posterior balance behaves;
5. how much and how diversely the fixed external-sandhi grammar is used;
6. how script and spacing conditions affect those quantities;
7. how flat lexical behaviour changes under the extreme Devanagari
   continuous condition;
8. what empirical evidence bears on the move to S1M2 reusable-piece
   induction.

No single scalar pass/fail criterion is defined.

## 2. Valid final analysis cells

The final valid-cell set contains exactly five S1M1 cells. Each must be
completed and audited before it can enter the final reduction:

| Script | Condition | Role |
|---|---|---|
| IAST | `surface_word` | valid controlled cell |
| IAST | `legacy_joined` | valid controlled cell |
| Devanagari | `surface_word` | valid controlled cell |
| Devanagari | `legacy_joined` | valid controlled cell |
| Devanagari | `continuous` | valid extreme no-spacing stress cell |

The first four cells form the controlled 2 x 2 script/spacing comparison.

Devanagari continuous is an additional extreme stress condition. It does not
create a complete script x continuous comparison.

## 3. IAST continuous invalidation

IAST `continuous` is scientifically INVALIDATED for downstream S1M1 formal
analysis.

Deleting whitespace before ordinary IAST serialization is not always
phoneme-sequence preserving across lexical boundaries. Attested cross-boundary
vowel hiatus can collapse into an ordinary IAST diphthong spelling, especially

    a + i -> ai

and analogously

    a + u -> au.

The frontend then parses the written diphthong as a single phonological unit.
Consequently this observation condition is not guaranteed to preserve the
phoneme sequence that the experiment intends to vary only by spacing.

This invalidation does not modify M0 retrospectively and does not authorize
repairing the representation, recovering hidden boundaries, or changing the
frontend.

Recorded status:

- scientific status: `INVALIDATED`
- runtime status: `TERMINATED EARLY BY RESEARCHER`
- completed passes: `2`
- termination point: pass `3`, `next_document_index = 86`
- formal comparison: `EXCLUDED`
- diagnostic evidence: `RETAINED`
- rerun/repair: `NONE`
- scientific runtime commit: `375178ba50bd1a1644d65525907692b31413b33d`
- termination archive SHA-256:
  `386c94233ead7f569d0a7cdc1436a874d165dd1e0cede349f943c0196fafaa9d`

The invalidated cell is metadata/provenance for the final analysis manifest.
It is never accepted as a sixth completed scientific cell and its incomplete
outputs are never imputed.

No speculative consonant/aspirate collision argument is part of this
invalidation.

## 4. Designated formal comparisons

The final analysis contains exactly six designated scientific contrasts.

### 4.1 Controlled script effects

1. IAST `surface_word` -> Devanagari `surface_word`
2. IAST `legacy_joined` -> Devanagari `legacy_joined`

### 4.2 Controlled spacing effects

3. IAST `surface_word` -> IAST `legacy_joined`
4. Devanagari `surface_word` -> Devanagari `legacy_joined`

### 4.3 Devanagari continuous stress effects

5. Devanagari `surface_word` -> Devanagari `continuous`
6. Devanagari `legacy_joined` -> Devanagari `continuous`

No IAST-continuous versus Devanagari-continuous script contrast is permitted.

Arbitrary all-pairs comparisons are not part of the final formal result.
Historical midpoint analyses may retain such exploratory comparisons.

For scalar quantities, each designated comparison should expose where
applicable:

- value in reference cell A;
- value in comparison cell B;
- signed difference `B - A`;
- relative change `(B - A) / abs(A)` when `A != 0`;
- ratio `B / A` when `A != 0`.

Distributional comparisons already supported by the bounded reducer may also
report their declared overlap/divergence statistics, provided their exact or
approximate status remains explicit.

## 5. Per-cell analysis families

### 5.1 Training dynamics

For every pass:

- lexical inventory size;
- expected lexical tokens;
- lexical count total;
- identity mass;
- latent mass;
- candidate factors/nodes/edges;
- overflow diagnostics;
- pass-to-pass signed and relative changes where defined.

Training-pass quantities and final-inspection quantities must remain
distinguishable.

### 5.2 Lexicon structure and economy

Report:

- active lexical types;
- expected lexical count distribution;
- lexical mass concentration;
- Shannon entropy and effective vocabulary quantities where already supported;
- phoneme-length distribution;
- lexical mass by phoneme length;
- low-count tail;
- context reuse;
- surface-variant reuse;
- relationships among count, length, contexts, and surface variants.

Predeclared mass-support thresholds inherited from the midpoint reducer are:

    0.90, 0.95, 0.99, 0.999, 0.9999

Predeclared lexical-length thresholds are:

    8, 16, 32, 64 phonemes

Predeclared reuse thresholds are:

    2, 5, 10

These threshold families must not be changed after viewing the five-cell final
result unless a later quantity is explicitly labelled exploratory.

### 5.3 Posterior behaviour

Report:

- total and mean identity posterior mass;
- total and mean latent posterior mass;
- mean top-1 posterior;
- posterior entropy;
- bounded top-k residual mass diagnostics;
- ambiguity distributions;
- deterministic bounded examples of high-confidence and high-ambiguity cases.

Predeclared confidence thresholds inherited from the midpoint reducer are:

    0.50, 0.90, 0.95, 0.99

### 5.4 Boundary behaviour

Report:

- candidate boundary counts;
- expected boundary totals;
- posterior probability distribution;
- binary entropy;
- expected boundaries per segment;
- expected boundaries per phoneme;
- cue-stratified summaries.

Whitespace, avagraha, and other observation cues remain reference signals and
are never interpreted as gold lexical boundaries.

### 5.5 External-sandhi grammar use

Report exact global rule usage:

- total expected rule use;
- rules with positive expected use;
- positive inventory coverage;
- normalized rule distribution;
- Shannon entropy;
- effective rule count;
- usage per segment;
- usage per expected boundary;
- usage per surface phoneme;
- deterministic high- and low-usage rule examples.

Bounded top-k segment diagnostics must remain explicitly labelled as bounded
inspection quantities and must not replace exact global rule totals.

### 5.6 Candidate/scaling diagnostics

Report candidate graph size and heavy-tail diagnostics already available from
the learner artifacts, including:

- factors;
- lattice nodes;
- lexical edges;
- overflow;
- document-level distributions;
- segment-length strata.

These quantities describe computational structure and must not be treated as
direct linguistic-quality measures.

### 5.7 Runtime and resource behaviour

Runtime/resource evidence remains a separate engineering family.

It may include:

- wall time;
- CPU time;
- peak process-tree RSS;
- read/write volume;
- phase timings;
- lexical-score/cache/SQLite counters;
- candidate edges per wall second;
- surface phonemes per wall second.

Runtime differences never substitute for scientific-quality comparisons.

## 6. Predeclared failure-mode indicators

The final implementation must expose objective indicators for at least the
following phenomena.

### 6.1 Long-form lexicalization

Use lexical-type and expected-mass quantities at the frozen length thresholds
8, 16, 32, and 64 phonemes.

### 6.2 Low-reuse memorization

Expose type and mass behaviour stratified by context and surface-variant reuse,
using the frozen reuse thresholds 2, 5, and 10 where applicable.

Particular attention is paid to long forms with little contextual or
surface-variant reuse.

### 6.3 Identity/latent concentration

Expose identity and latent posterior mass directly. The implementation must
not convert these quantities into an automatic collapse/pass verdict.

### 6.4 Spacing-removal lexicalization

Use the two designated surface_word -> legacy_joined contrasts to quantify
changes in lexical inventory, lexical length/mass concentration, reuse,
posterior behaviour, boundaries, and rule use.

### 6.5 Devanagari continuous stress

Use the two designated Devanagari continuous contrasts to quantify changes in
the same families under complete spacing removal.

### 6.6 Sandhi-use displacement

Expose changes in exact expected rule usage, positive-rule coverage, rule
entropy/effective count, and usage normalized by segments, expected boundaries,
and phonemes.

The term "displacement" names a diagnostic family only. The implementation does
not infer a causal or linguistic verdict automatically.

## 7. Deterministic evidence selection

Qualitative/evidence examples must be selected mechanically.

Existing deterministic bounded top-score, low-score, hash-reservoir, or
equivalent fixed-selection machinery may be reused.

The default retained evidence limit remains 12 examples per predeclared
category where the midpoint implementation already uses that bound.

Examples may illustrate:

- longest lexical forms;
- high-mass long forms;
- low-count forms;
- high-context forms;
- high-surface-variant forms;
- high ambiguity;
- high boundary entropy/confidence;
- common and low-usage sandhi rules;
- largest designated cross-condition differences.

Examples must not be manually selected after viewing final results.

## 8. Final compact outputs

The final analysis implementation should emit deterministic compact outputs
including:

- `manifest.json`
- `cells.tsv`
- `pass_dynamics.tsv`
- `lexicon_distribution.tsv`
- `lexical_length.tsv`
- `reuse_distribution.tsv`
- `ambiguity_distribution.tsv`
- `boundary_distribution.tsv`
- `rule_usage.tsv`
- `candidate_scaling.tsv`
- `document_distribution.tsv`
- `length_strata.tsv`
- `runtime_breakdown.tsv`
- `formal_comparisons.tsv`
- `failure_mode_indicators.tsv`
- `evidence_samples.jsonl`
- `decision_inputs.json`
- `summary.md`

Source artifacts are read-only. Output must go to a fresh directory and must
fail closed rather than overwrite an existing output.

## 9. decision_inputs.json

`decision_inputs.json` is a compact machine-readable synthesis of objective
evidence.

It should expose evidence relevant to questions such as:

- how concentrated/economical the final lexicon is;
- how much expected lexical mass lies in long forms;
- how reusable lexical identities are across contexts and surfaces;
- how identity and latent mass are balanced;
- how much and how diversely the external-sandhi grammar is used;
- how large the controlled spacing effects are;
- how large the controlled script effects are;
- the magnitude and direction of the Devanagari continuous stress effect;
- what empirical evidence bears on the need for S1M2 reusable pieces.

It must not encode the paper's final prose conclusion or an automatic S1M1
pass/fail judgement.

## 10. Provenance and validation

Every valid cell must be a completed, audited unrestricted S1M1 collection with
its exact:

- run identity;
- metrics identity;
- final audit;
- scientific Git commit;
- configuration/provenance identity;
- canonical scientific artifact identities.

The final input manifest must also contain an explicit IAST-continuous
invalidation record consistent with Section 3.

Validation is fail-closed.

The final reducer remains:

- local-only;
- read-only over source artifacts;
- streaming/bounded-memory;
- deterministic;
- output-only into a fresh directory.

## 11. Freeze discipline

At the commit that introduces this document:

- analysis plan/specification: `FROZEN`;
- final analysis implementation: `PROVISIONAL`;
- S1M1 result release: `NOT YET FROZEN`.

The first complete real five-cell execution is an implementation validation
step. Genuine implementation bugs may be fixed before the S1M1 release,
provided the frozen scientific comparisons, metric families, threshold
families, and interpretation contract above are not opportunistically changed
after observing the result.

After complete real-data execution, source/audit verification, sanity review,
and any implementation-only corrections:

- final analysis implementation: `FROZEN`;
- S1M1 result release: `FROZEN`.

Git history is the authoritative archive of the earlier midpoint
implementations. Historical logs are not reconstructed retroactively.

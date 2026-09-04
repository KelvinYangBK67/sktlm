# S1M1 final scientific analysis and freeze (closed 2026-09-04)

## Closure status

S1M1 has reached:

```text
SCIENTIFIC_ANALYSIS_COMPLETE
ARCHIVAL_COMPLETE
DELETION_GATE_READY
FROZEN
```

The scientific conclusions, selective archival contract, and milestone are
closed. The formal result is four complete quantitative cells plus two
typed N/A cells, not a completed six-cell experiment:

| Script | Representation | Formal status | Scientific use |
|---|---|---|---|
| IAST | `surface_word` | `AVAILABLE` | quantitative |
| IAST | `legacy_joined` | `AVAILABLE` | quantitative |
| IAST | `continuous` | `NA_SCIENTIFICALLY_EXCLUDED` | representation result; partial learner state excluded |
| Devanagari | `surface_word` | `AVAILABLE` | quantitative |
| Devanagari | `legacy_joined` | `AVAILABLE` | quantitative |
| Devanagari | `continuous` | `NA_EXECUTION_INCOMPLETE` | scalability result; partial learner state excluded |

## Authoritative evidence and provenance

The formal analysis ID is `s1m1-final-four-cell-20260903`. Its manifest is
`configs/analysis/s1m1_final_v2.json`; its already-completed output is
`artifacts/s1m1_final/aggregation/`. `aggregation.json` reports validation
`valid: true`, with six declared cells, four `AVAILABLE`, and two N/A. The
machine-readable outputs are `aggregation.json`, `cells.tsv`, `pairs.tsv`,
`rule_distances.tsv`, `rule_usage.tsv`, and `top_k_overlap.tsv`; `summary.md`
is the claim-free human summary.

The source inventory ID is `s1m1-final-source-inventory-20260903`. The input is
`configs/analysis/s1m1_source_inventory.json` and the completed result is
`artifacts/s1m1_final/source_inventory/inventory.json`. Its validation is
`valid: true`; it records size and SHA-256 for all twelve completed-cell large
scientific sources, totaling 91,193,439,274 bytes. This closure reads those
small outputs and does not rerun aggregation, rescan the large files, or
recompute their hashes.

All four complete cells use frozen M0 freeze ID
`9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`,
the 240-document manifest SHA-256
`c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520`,
and the 1,218-rule SHA-256
`55a204169a1ec442e8ac6e9ca90da1e6510b24998cdeba2d76f95f513bab7e90`.
The IAST `surface_word` anchor was produced at
`cd3a092b116ad236c4ad96d7c24868e79e9a47ce`; the other three cells were
produced at `375178ba50bd1a1644d65525907692b31413b33d`. Their approved
cross-commit compatibility is recorded in the formal manifest and acceptance
evidence.

## Scientific result

### Script effect: negligible under matched spacing

Within `surface_word`, IAST and Devanagari are exactly equal on the aggregated
latent-structure, posterior, graph, lexicon, and rule metrics. Rule total
variation and Jensen-Shannon divergence are both zero, and top-k lexical
overlap is exact at k=100, 1,000, and 10,000. The sole reported difference is
orthographic character accounting: 53,233,989 IAST characters versus
48,678,812 Devanagari characters (-8.556896%). This is an orthographic
representation effect, not a learned latent-structure effect.

Within `legacy_joined`, the script comparison is near-equivalent rather than
mathematically identical. From IAST to Devanagari, active lexical types change
by +0.002094%, low-count types by +0.002095%, expected lexical tokens by
+0.001690%, mean identity mass by -0.000293%, entropy by +0.004974%, top-1
posterior by -0.000780%, and candidate edges by -0.008110%. Rule TV is
`1.3080489453873243e-05` and JSD is `2.339464786880392e-06` nats. Top-k
overlap is exact at k=100 and 1,000 and 9,998/10,000 at k=10,000. The large
character-count difference (-9.843212%) again reflects script encoding. The
scientifically meaningful residuals are orders of magnitude below the spacing
effects.

### Spacing effect: large and replicated across scripts

The formal `surface_word` to `legacy_joined` comparisons are:

| Metric | IAST | Devanagari |
|---|---:|---:|
| active lexical types | +36.227805% | +36.230658% |
| low-count lexical types | +36.703865% | +36.706730% |
| expected lexical tokens | -21.335704% | -21.334375% |
| mean identity mass | +25.133947% | +25.133580% |
| mean latent mass | -4.320038% | -4.319975% |
| mean posterior entropy | -19.545603% | -19.541601% |
| mean top-1 posterior | +5.036431% | +5.035612% |
| candidate edges | +15.996962% | +15.987554% |
| candidate factors | -21.379752% | -21.378641% |
| candidate nodes | -6.471913% | -6.475032% |
| external-rule expected usage | -28.788099% | -28.787904% |
| complexity penalty | +4.491664% | +4.492846% |

The long tail worsens in both scripts: low-count types grow from 18,851,674 to
25,770,967 in IAST and to 25,771,507 in Devanagari, while their share rises
from 98.8625% to 99.2080%. Support also spreads across more types: the number
needed for 90%, 95%, and 99% lexical mass rises respectively by about 27.31%,
14.00%, and 5.55%.

Lexical top-k overlap between spacing conditions is only 73/100, 769/1,000,
and 7,899/10,000 in either script (Jaccard 0.574803, 0.624695, and 0.652756).
Rule distributions also move substantially: IAST rule TV/JSD are
`0.1905965334208121` and `0.06972276490145518` nats; Devanagari values are
`0.19058822550539367` and `0.06971220943933126` nats. These nearly identical
effects under both scripts establish the controlled conclusion:

> Across the four completed cells, spacing exerts a substantially larger
> effect than script.

### Interpretation: sharper posterior, worse lexicon economy

The direct observation is a tension. Removing visible spacing lowers entropy
and raises top-1 concentration, yet expands the active and low-count lexicon,
raises the complexity penalty, requires more types to cover most lexical mass,
reduces expected lexical-token count, and sharply reduces external-rule use.
Posterior sharpness is therefore not sufficient evidence of lexical or
morphological quality.

The coherent model-level interpretation is context-specific over-long
lexicalization. Without visible boundary evidence, the current flat lexical
objective can absorb longer surface contexts into single lexical identities.
Those identities can win locally and sharpen the posterior while reusing less
well across contexts, enlarging the inventory and its low-count tail. The
bounded examples in
`noncontinuous_representation_checkpoint_20260901.md` directly illustrate
this tendency and show that it already exists under `surface_word` but is
amplified by `legacy_joined`.

Visible spacing here acts as editorial/lexical-boundary evidence that supplies
strong supervision or regularization to this particular
representation-by-objective combination. This is not a universal claim that
Sanskrit requires spaces, not a definition of linguistic wordhood, and not a
license to treat whitespace as a gold lexical boundary.

### Direct association-level evidence: YES

The full supplementary association analysis is
`s1m1-devanagari-association-microanalysis-20260904`, schema
`sktlm-association-specialization/v1`. It read the retained Devanagari compact
states and emitted 45,045,832 per-form rows and 27,897,467 aligned-comparison
rows. Its output manifest records implementation commit
`ccf4002ce8100e02a436e447a1c2172722ef1421`; all eleven output files validate
against `SHA256SUMS`.

The direct population evidence is:

- `legacy_joined` contains 25,977,252 scorer forms versus 19,068,580 in
  `surface_word`. Of the aligned union, 17,148,365 forms are shared,
  1,920,215 are surface-only, and 8,828,887 are legacy-only.
- Expected-count-weighted context top-1 share rises from 0.3204 to 0.4188 and
  context entropy falls from 4.7255 to 3.7926 nats. Association-mass weighting
  gives the same direction (top-1 0.3203 to 0.4228; entropy 4.7246 to 3.7627).
- Expected-count-weighted surface top-1 share rises from 0.3246 to 0.4453 and
  surface entropy falls from 4.7817 to 3.7422 nats; association-mass-weighted
  values are 0.3188 to 0.4424 and 4.8101 to 3.7553.
- The long tail is not merely an aggregate vocabulary count. Forms of length
  17 or more increase from 5,048,227 to 8,213,592, and forms with final
  expected count at most 0.1 increase from 16,673,665 to 23,534,035. In the
  joint length/count cells, legacy has 6,713,168 forms of length at least 17
  and count at most 0.1, versus 3,829,489 for surface-word.
- Low count directly predicts narrow association: in `legacy_joined`, the
  correlation between `log1p(expected_count)` and top-1 share is -0.7936 for
  context and -0.8148 for surface under expected-count weighting; corresponding
  entropy correlations are 0.9818 and 0.9871. Length has a much weaker
  type-weighted relationship, so the scientifically defensible statement is a
  joint long/low-count proliferation, not an independent morphology-like
  length law.

The deterministic diagnostics make the mechanism concrete. The shared form
`abhyadhikam` has expected count 0.616 in `legacy_joined` versus 32.290 in
`surface_word`; its legacy context top-1 share/effective support are 1.0/1.0,
versus 0.0286/84.53 in the reference, and its surface top-1 share is 0.9303
versus 0.0290. A legacy-only 266-phoneme form is an entire joined textual
sequence with expected count 0.99975 and both context and surface top-1 share
1.0. These examples are deterministic diagnostics, not representative effect
estimates; the population summaries above carry the general claim.

The weighting qualification matters. Type-weighted context top-1 share is
0.8607 for `surface_word` and 0.8509 for `legacy_joined`, while type-weighted
surface top-1 share rises from 0.9389 to 0.9507. Within fixed low-count/length
bins, the two conditions can also be similar. The evidence therefore does not
support the stronger claim that every legacy type is more context-specialized.
It directly supports the stated mechanism: removing visible boundary evidence
creates far more long, low-count, narrowly associated lexical identities and
shifts scientifically important mass toward concentrated contexts and
surfaces.

## Continuous cells: two different results

### IAST `continuous`: representation invalidation

Ordinary IAST after spacing removal is non-injective. Cross-boundary hiatus
`a + i` serializes as `ai`, colliding with lexical diphthong spelling, and
`a + u` similarly collides with lexical `au`. The cell is therefore
`NA_SCIENTIFICALLY_EXCLUDED`; its absence is itself a representation result.
The manually terminated partial learner state (two completed passes and 86
documents in pass 3) is diagnostic only and contributes no quantitative
scientific estimate.

### Devanagari `continuous`: computational scalability failure

The Devanagari representation remains scientifically valid, but the current
learner/finalization path is computationally unacceptable for this condition.
The run was manually terminated after pass 3 had traversed 240/240 documents
but before pass finalization and inspection. A completed pass contained
875,448,908 candidate edges; before termination the database and WAL were
78,628,376,576 and 79,089,093,872 bytes. These are execution diagnostics, not
scientific estimates. The cell is `NA_EXECUTION_INCOMPLETE`, not a negative
representation result.

## Consequence for subsequent work

S1M1 identifies a concrete failure mode of flat lexical induction and supplies
the empirical motivation for testing reusable compositional pieces in S1M2.
Targets such as `gaccha|ti` or `gacch|a|ti` should be tested as learned,
script-neutral reusable pieces; this checkpoint does not claim S1M2 has solved
the problem.

`surface_word` is the successful boundary-visible reference condition, not the
preferred downstream representation. `legacy_joined` is a completed
diagnostic failure/stress condition: its sharper posterior coexists with worse
lexicon economy. A corrected and scalable continuous representation remains
the downstream target direction.

For future continuous IAST work, derived M0-prime uses frozen M0
Devanagari continuous as its source, renders lexical `/ai/` and `/au/` as `ē`
and `ō`, and retains ordinary `ai` and `au` for cross-boundary hiatus after
spacing removal. Frozen M0 is unchanged. M0-prime implementation and S1M2
integration are separate post-freeze work and are not part of the S1M1 result.

## Archival completeness and deletion readiness

Selective archival is complete. The retained Devanagari `surface_word` raw
`learner.sqlite` is 10,488,496,128 bytes and its locally recomputed SHA-256,
`e62ec033052c4dcdfedf7c3164faa88c7e954a4c2fbc5b73379faa49395d5c8c`,
exactly matches the exporter-recorded source identity. No WAL was present at
export or in the returned raw directory, so the policy's conditional WAL
requirement is satisfied.

SQLite-derived association state is supplementary microscopic reuse/context
evidence; it is not required for the validity of the completed formal S1M1
analysis. The selective policy is recorded in
`configs/analysis/s1m1_sqlite_retention.json`:

- Devanagari `surface_word`: retain raw SQLite, a non-empty WAL if present,
  and compact scorer/association state;
- Devanagari `legacy_joined`: retain compact scorer/association state only;
- both completed IAST cells: no SQLite microstate archival requirement because
  the matched-spacing script effect is negligible;
- both continuous partial states: excluded from the completed-state contract;
  existing representation/runtime/termination evidence remains retained.

Both compact-state `SHA256SUMS` files validate locally, including manifests and
all six compressed scorer/context/surface payloads. Both manifests report all
database and read-back consistency checks true. The association output
checksum set also validates locally.

The final classifications are:

- `RETAIN`: Devanagari `surface_word` raw SQLite; both retained Devanagari
  compact states; the full association-microanalysis directory; formal
  aggregation/inventory and tracked provenance; both continuous-cell
  failure/termination evidence.
- `SAFE_TO_DELETE_REGENERABLE`: the twelve completed-cell large scientific
  sources totaling 91,193,439,274 bytes. Their exact sizes/hashes, frozen
  inputs, code/config provenance, scientific reductions, and required retained
  microscopic state are preserved.
- `PENDING`: none in the S1M1 closure scope.
- `NOT_SAFE`: none in the S1M1 closure scope.

The gate is `READY`. This is deletion readiness, not deletion authority. No
file, VM artifact, raw SQLite database, compact export, association payload, or
scientific source artifact was deleted. Any physical deletion remains a
separate manual researcher decision.

## Validation boundary

This report uses the already-completed formal aggregation and source inventory,
both of which declare `valid: true`. Closure additionally validated both
compact-state checksum sets, all association-output checksums, JSON syntax, the
retained raw-SQLite source identity, focused tests, Git diff, and repository
status. It did not rerun a learner, formal aggregation, the 91 GB inventory, or
the full association scan.

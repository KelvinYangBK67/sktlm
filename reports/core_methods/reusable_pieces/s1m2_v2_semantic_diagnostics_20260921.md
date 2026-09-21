# S1M2 V2 held-out semantic diagnostics #3 and #5

Date: 2026-09-21
Status: implemented and run on the existing E000 checkpoint; diagnostic only

## Scope and scientific freeze

This work adds two read-only held-out top-1 diagnostics:

1. wrong-latent-host coalition participation;
2. unseen exact DCS gold wordform generalization.

It does not change the V2 objective, `S`, `C`, `M`, `R`, piece identity,
scorer, grammar, gamma, rho, candidates, inference, training, SQLite schema,
caches, or workers. It does not introduce morphological boundary gold or a
boundary reward. The evaluator consumes the already generated DCS-structural
localization records; it invokes neither training nor inference.

## Training-gold inventory

No authoritative training-gold inventory sidecar existed before this task.
The E000 corpus is exactly the multiset in the locally generated
`controlled/background_1000.jsonl` selection. Every row carries its DCS source
file and sentence text. Reconstruction against the local DCS tree found:

- 1,000 selected training sentences;
- 996 unique DCS sentence matches;
- four surface-identical selections with multiple DCS sentence IDs whose
  ordered gold wordform sequences are identical;
- 4,350 distinct canonical valid IAST `Unsandhied` wordforms;
- 57 integer tokens with `Unsandhied=_`;
- one invalid non-IAST `Unsandhied` value, `ṣoﾱaśabhiḥ`.

The last 58 values remain explicitly unavailable and are not inferred from
surface spelling. The sidecar retains every selection, candidate sentence
identity, token, unavailable reason, source hash, selection hash, and corpus
hash. Its SHA-256 is
`2ca2ceb2096cde32ce89d1dfe481561ea161eea9c345a978a710d5c6e40bdb52`.
It is local generated diagnostic data, not a tracked corpus artifact.

## Diagnostic #5: unseen exact wordforms

Membership means exact canonical DCS `Unsandhied` membership in the selected
training-gold inventory. Lemma identity, training predictions, and surface
sandhi spelling are ignored.

| stratum | targets | evaluable | recovered | rate | mean pieces | piece denominator | whole use | whole denominator | unscorable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| seen exact gold wordform | 0 | 0 | 0/0 | NA | NA | 0 | NA | 0 | 0 |
| unseen exact gold wordform | 80 | 76 | 31/76 | 0.407895 | 1.750000 | 56 | 0.267857 | 56 | 4 |
| overall | 80 | 76 | 31/76 | 0.407895 | 1.750000 | 56 | 0.267857 | 56 | 4 |

All 80 held-out target gold wordforms are unseen. The four unscorable targets
have `dcs_component_factor_alignment_ambiguous`. Among the 76 lexical-recovery
evaluations, 20 top-1 analyses have no single target piece segmentation:
12 fragment a gold token and eight merge gold components. They remain lexical
nonrecoveries and are excluded from the two piece means.

This E000 result supplies an unseen-only estimate; it cannot compare seen and
unseen strata because the seen stratum is empty.

## Diagnostic #3: wrong-host coalition participation

The audit has 76 evaluable occurrences: 31 correct and 45 wrong. Twenty-five
wrong occurrences have one localized predicted host and a target piece
segmentation. Nine pieces appear in these wrong predictions. One piece is
shared by at least two distinct wrong predicted hosts and has `R>0`, so it is
the sole descriptive coalition candidate:

| piece | wrong occurrences | distinct wrong hosts | wrong hosts | correct occurrences | distinct correct hosts | C | M | R |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| `dev` | 16 | 4 | `devaṃ`, `devā`, `devānāṃ`, `devāñjigha` | 22 | 4 | 1.128234 | 0.222276 | 0.905958 |

The correct predicted hosts using `dev` are `devaiḥ`, `devebhyaḥ`, `devān`,
and `devānām`. Repetition within one wrong host does not increase the distinct
wrong-host count.

Final `C/M/R` are read from training state. Wrong-host participation is
measured on held-out top-1 analyses. This association does not show that the
wrong hosts caused the learned reusable count, and it is not an exact
posterior quantity.

## Artifacts and lifecycle

The local run now has separate artifacts:

- `challenge_semantic_diagnostics.v3.jsonl`
- `challenge_semantic_summary.v3.json`
- `challenge_semantic_diagnostics.v3.provenance.json`

The evaluator commit recorded in provenance is
`b3ec174cd7373200ffb0aa735336dc9775025e64`; the training commit is
`1e3348340410d8576b5ce2a6176ac9e3cac096d3`. The learner was opened with
SQLite `mode=ro` and `PRAGMA query_only=ON`. Provenance records that the
trainer and inference were not invoked and that the original analyses,
summary, config, checkpoint, provenance, and learner hashes were unchanged.
`PRAGMA quick_check` remains `ok`; no WAL or SHM sidecar exists.

Focused validation: touched modules compile, and the semantic diagnostics plus
existing lexeme probe/alignment tests pass, 18 tests total in 1.43 seconds.
`git diff --check` passes. No new training cell, VM, cloud job, Full M0 run,
representative/stress corpus, or long benchmark was run.

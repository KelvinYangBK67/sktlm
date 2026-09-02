# CURRENT_TASK.md

## Current status

Branch:

`exp/s1m1-final-reduction`

Current checkpoint before this task:

`88b5a1c6d710f74b3d40dc523180242bd99327e4`

This is a temporary S1M1 closure work branch. Do not create another branch and
do not merge this work into `exp/s1m2-reusable-pieces`.

The final S1M1 analysis specification is now:

`reports/core_methods/latent_lexicon/s1m1_final_analysis_plan.md`

## Scientific input status

Exactly five representation cells are valid for final S1M1 analysis:

- IAST / `surface_word`
- IAST / `legacy_joined`
- Devanagari / `surface_word`
- Devanagari / `legacy_joined`
- Devanagari / `continuous`

IAST / `continuous` is scientifically `INVALIDATED` and formally `EXCLUDED`.
Its terminated run is retained only as diagnostic provenance. Do not repair,
impute, or rerun it.

M0 itself remains frozen and historically contains six formal observation
representations. Do not alter M0 to encode the downstream S1M1 invalidation.

## Historical midpoint analysis implementations

The following remain untouched historical midpoint/diagnostic implementations:

- `src/sktlm/analysis/six_representation_gate.py`
- `scripts/analysis/aggregate_six_representation.py`
- `src/sktlm/analysis/s1m1_archival.py`
- `scripts/analysis/reduce_s1m1_archival.py`

Do not rename, delete, archive-copy, or retroactively manufacture logs for
them. Git history is authoritative.

## Next implementation task

Create the new provisional final S1M1 analysis implementation:

- `src/sktlm/analysis/s1m1_final.py`
- `scripts/analysis/finalize_s1m1.py`
- `tests/analysis/test_s1m1_final.py`

The implementation must:

1. accept exactly five valid completed/audited cells;
2. require an explicit IAST-continuous invalidation record;
3. reject IAST continuous if presented as a valid completed cell;
4. reuse mature bounded per-cell reduction machinery where safe rather than
   duplicating the whole archival reducer;
5. emit exactly the six designated formal contrasts in the frozen plan;
6. emit deterministic compact per-cell tables, formal comparisons,
   failure-mode indicators, evidence samples, and `decision_inputs.json`;
7. keep scientific and runtime/resource evidence distinct;
8. remain local-only, read-only, fail-closed, streaming/bounded-memory, and
   fresh-output-only.

Do not change learner code or scientific artifacts in this task.

## Validation boundary

Use only short focused synthetic validation.

At minimum test:

- exact five-cell acceptance;
- missing-cell rejection;
- IAST-continuous-as-valid rejection;
- missing or contradictory invalidation-record rejection;
- incomplete/non-audited valid-cell rejection;
- exactly six designated comparisons;
- absence of an IAST-vs-Devanagari continuous comparison;
- deterministic output;
- source read-only behavior;
- output overwrite refusal.

Do not run the complete real-artifact reduction yet.
Do not run full-corpus work.
Do not contact or poll a VM.
Do not SSH/SCP/rsync/bridge.
Do not interfere with the running Devanagari continuous experiment.

If any validation is likely to exceed five minutes, stop and leave the exact
command for the human researcher.

## Freeze status

- final analysis plan/specification: `FROZEN`
- final analysis implementation: `PROVISIONAL`
- S1M1 result release: `NOT YET FROZEN`

The implementation freezes only after successful complete real-data execution,
audit/sanity review, and any implementation-only corrections.

At the eventual S1M1 freeze, the human researcher will reconcile this temporary
closure branch back into the long-term `exp/s1m1-core-methods` milestone branch.

# S1M1 final-analysis and archival checkpoint (2026-09-03)

## Status

**S1M1 = `FINAL_ANALYSIS_PENDING_HUMAN_ARCHIVAL_GATE`.**

The final scientific framing is fixed as:

```text
4 complete controlled scientific cells
+ 1 scientifically invalid representation
+ 1 scientifically valid but computationally incomplete execution
```

This is not a completed six-cell experiment. The formal v2 manifest is
`configs/analysis/s1m1_final_v2.json`. It declares four `AVAILABLE` cells,
IAST `continuous` as `NA_SCIENTIFICALLY_EXCLUDED`, and Devanagari `continuous`
as `NA_EXECUTION_INCOMPLETE`. Partial continuous learner state is excluded
from every scientific estimate.

Formal v2 aggregation was deliberately not executed in this checkpoint. The
twelve large local analyses/boundary/lexicon sources total 91,193,439,274
bytes, and strict validation plus scientific reduction would scan them. That
clearly exceeds the five-minute stop rule. No long process was launched or
stopped. The exact human-run sequence is in
`docs/workflows/s1m1_final_human_run.md`.

## Frozen experiment provenance

All four complete cells use frozen M0 freeze ID
`9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`,
the 240-document manifest SHA-256
`c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520`,
and the 1,218-rule SHA-256
`55a204169a1ec442e8ac6e9ca90da1e6510b24998cdeba2d76f95f513bab7e90`.
The IAST `surface_word` anchor was produced at
`cd3a092b116ad236c4ad96d7c24868e79e9a47ce`; the other three cells were
produced at `375178ba50bd1a1644d65525907692b31413b33d`. Their compatibility
basis remains the completed non-continuous checkpoint.

The older IAST anchor predates config-level `script`/`condition` fields and its
historical remote audit failed only because that obsolete audit contract
required `benchmark_metrics.json`. Its completed process evidence and exact
four-replica scientific hashes were already accepted. The transparent local
acceptance envelope preserves both facts at
`reports/core_methods/latent_lexicon/evidence/s1m1_final/iast_surface_word_acceptance_audit.json`;
it does not rewrite the historical failed audit.

## Four-cell scientific result already established

The prior completed four-cell analysis remains authoritative until the v2
aggregation is human-run. Its detailed scalar tables and bounded qualitative
examples are in `noncontinuous_representation_checkpoint_20260901.md`.

- Script effect under `surface_word`: exact scientific equivalence except raw
  character count; rule TV and JSD are both zero.
- Script effect under `legacy_joined`: negligible but nonzero; rule TV is
  `1.3080489453873241e-05` and JSD is
  `2.339464786880391e-06` nats.
- Spacing effect is large and nearly script-invariant. From `surface_word` to
  `legacy_joined`, active lexical types rise about 36.23%, low-count types
  about 36.71%, expected lexical tokens fall about 21.33%, entropy falls about
  19.54%, identity mass rises about 25.13%, and external-rule usage falls
  about 28.79%.
- The sharper joined posterior is not evidence of better lexical analysis.
  Together with a larger/longer low-reuse lexicon, it supports an over-long
  lexicalization/economy failure already visible in `surface_word` and
  amplified when spacing evidence is removed.

The v2 human run will regenerate formal single-cell metrics, mass-support
thresholds, all four available pair comparisons, rule TV/JSD, and top-k
overlap. Every declared comparison involving either continuous cell will be
emitted as `N/A` with its status/reason rather than aborting the analysis.

## IAST continuous: representation failure

Status: `NA_SCIENTIFICALLY_EXCLUDED`.

Ordinary IAST with lexical spaces removed is non-injective. Cross-boundary
hiatus `a + i` serializes as `ai`, colliding with the ordinary spelling of a
lexical diphthong; likewise `a + u` serializes as `au`. No unproven
consonant/aspirate collision argument is needed. The representation was
scientifically invalidated, the run was manually terminated, and its partial
two-pass/partial-pass-3 learner state is diagnostic only.

The retained 6,739,892-byte termination archive has SHA-256
`386c94233ead7f569d0a7cdc1436a874d165dd1e0cede349f943c0196fafaa9d`.
It records SIGTERM/return code `-15`, 78,831.586 wall seconds, 82,376.37
sampled CPU seconds, peak process-tree RSS 11,493,634,048 bytes, about 2.316 TB
sampled reads, about 2.253 TB sampled writes, two complete passes, and 86
documents traversed in pass 3. These are runtime/termination diagnostics, not
scientific estimates. Rerunning the same invalid representation has no
scientific purpose.

Historical frozen M0 is unchanged and retained.

## Devanagari continuous: computational failure

Status: `NA_EXECUTION_INCOMPLETE`.

This representation remains scientifically valid, but the execution was
manually terminated during pass 3 after all 240 documents had been traversed,
before pass finalization and inspection. Pass-2/pass-3 database state is not a
formal scientific result.

The retained termination evidence records SIGTERM/return code `-15` at
`2026-09-02T21:45:54+08:00`, 107,097.277 wall seconds, 102,970.58 sampled CPU
seconds, peak process-tree RSS 11,938,275,328 bytes, about 3.138 TB sampled
reads, about 2.856 TB sampled writes, and peak process count 10. A completed
pass contained 875,448,908 candidate edges. Immediately before termination,
`learner.sqlite` was 78,628,376,576 bytes and its WAL was 79,089,093,872
bytes. The retained evidence-manifest SHA-256 is
`f0689f122e09bbeb710aa4f16b6ee2a13caadc656cadd5639bba527d3c2dbf79`.

All scientific fields for this cell are N/A. The figures above are explicitly
runtime/scalability evidence.

## M0-prime motivation (not generated)

Future work should create a new derived `M0-prime IAST continuous`
representation from frozen M0 Devanagari continuous, without modifying or
replacing M0. Its design decision is:

```text
source: frozen M0 Devanagari continuous
lexical diphthong /ai/: ai -> ē
lexical diphthong /au/: au -> ō
cross-boundary hiatus after space removal: a + i -> ai; a + u -> au
```

Thus lexical `/ai/` remains distinct from hiatus `/a i/`, and lexical `/au/`
from hiatus `/a u/`. This section records motivation only. No representation
script or M0-prime data was created in this task, and M0-prime must not be
retroactively counted as a completed S1M1 cell.

## Compact archive and deletion readiness

The read-only human-run exporter now preserves, per complete cell:

- exact final SQLite scorer state (`form_key`, training expected count,
  probability), kept distinct from inspection expected counts;
- full rendered/phonological lexicon inventory, length, probability, surface
  variant counts, and context counts;
- exact surface/context reuse associations;
- segment metrics and top-1 form/rule IDs;
- boundary table, pass dynamics, rule use, runtime breakdown, lexical-length,
  reuse, document, and length-stratum tables;
- compact-output SHA-256 and row/count/mass read-back checks.

None of those four real compact exports has run. The completed-cell SQLite
databases were not included in the local scientific collections, so exact
training-final scorer and reuse tables must be exported on their source hosts
before any large source can be considered disposable.

The machine-readable gate is
`reports/core_methods/latent_lexicon/s1m1_deletion_readiness_20260903.json`:

- `SAFE_TO_DELETE_REGENERABLE`: none;
- `RETAIN`: both continuous-cell termination evidence sets;
- `NOT_READY`: all twelve large local scientific exports and all four
  uncollected exact-state SQLite sources.

No artifact was deleted. The gate cannot become ready until human-run hashes,
all four compact exports, read-back consistency, compact hashes, and final v2
aggregation have been validated and incorporated into the final report.

## Freeze decision

S1M1 is not `READY_TO_FREEZE`. After the human outputs are returned, the next
small task is limited to validating them, populating the final v2 result paths,
updating deletion statuses, finalizing this report, and only then marking the
milestone ready. No tag or merge is authorized by this checkpoint. S1M2 P1c
has not started.

## Validation

Focused analysis/archival tests passed (`18 passed in 1.93s`). The complete
repository suite passed once (`551 passed, 4 warnings in 27.86s`). Changed
Python files compiled, the human SHA script passed Bash syntax validation, and
`git diff --check` passed. No formal large-file scan was part of these tests.

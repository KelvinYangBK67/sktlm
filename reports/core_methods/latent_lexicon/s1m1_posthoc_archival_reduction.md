# S1M1 post-hoc archival reduction

## Status and scientific boundary

This helper is a **post-hoc descriptive/archival reduction** of completed,
audited unrestricted S1M1 collections. It does not alter, reopen, replace, or
contribute new pass/fail criteria to the frozen preregistered S1M1 gate.

The frozen protocol remains 'post_gate_analysis_protocol.md', and the formal
six-cell scalar aggregation remains
'scripts/analysis/aggregate_six_representation.py'. Neither file is modified by
this work. The archive is a separate read-only pass intended to retain compact
engineering and distributional evidence after the six large collections are
available locally.

No real collection was scanned while implementing or testing this helper.

## Entry point and safety contract

The entry point is:

    python scripts/analysis/reduce_s1m1_archival.py \
      --manifest <completed-six-cell-gate-manifest.json> \
      --output-dir <new-empty-output-directory>

The manifest is the same exact six-cell local manifest accepted by the formal
aggregator. Before reduction, the helper reuses its fail-closed checks for cell
identity, unrestricted configuration, completed passes and inspection, zero
process return code, valid final audit, common scientific configuration and M0
provenance, required artifacts, and exact audited byte/SHA identities.

The helper:

- performs no network, VM, SSH, collection, registry, or process operation;
- opens source files read-only and never mutates them;
- refuses an existing output directory before beginning the large scan;
- uses streaming reductions, constant-domain histograms, small per-document
  maps, top-10,000 head maps, bounded MinHash sketches, and bounded evidence
  reservoirs;
- creates no temporary SQLite database or full-tail support set;
- writes to a new sibling temporary directory and atomically installs the
  completed directory;
- deletes only its own failed temporary output directory.

## Retention identity

'manifest.json' records, per cell and artifact:

- script, condition, run ID, metrics ID, and scientific Git SHA;
- relative local path, bytes, data-row count where defined, and SHA-256;
- artifact schema/header;
- config signature and common freeze/manifest/rule identities;
- the process-tree summary and completed final audit identities.

It also records the exact input gate-manifest SHA-256. This identifies the bytes
that were reduced without copying large scientific payloads into the archive.

## Reductions

### Pass dynamics

'pass_dynamics.tsv' retains passwise lexical types/count mass, expected lexical
tokens and tokens per segment, identity/latent mass, log partition, candidate
factors/nodes/edges, overflow, and absolute and signed relative changes from
the previous pass. A zero previous denominator is represented as unavailable,
not silently coerced.

### Lexicon distribution, length, and reuse

The lexicon scan validates the source ordering
'expected_count DESC, form_key ASC' and the declared row/mass totals. It
retains:

- expected-count distribution and fixed count bins;
- 90/95/99/99.9/99.99% mass-support sizes;
- mass in the top 10 through top 1,000,000 entries;
- Shannon entropy, exp(H) effective vocabulary, inverse-Simpson effective
  vocabulary, and the exact descending-rank Gini coefficient;
- exact discrete type- and expected-mass-weighted phoneme-length summaries;
- expected mass at lengths at least 8, 16, 32, and 64;
- context support at 2/5/10, multiple-surface support, and explicitly defined
  high-count/single-context support;
- one-pass centered Pearson relationships and fixed count-bin relationships
  among expected count, phoneme length, context count, and surface-variant
  count.

Context and surface-variant counts inherit the learner's thresholded bounded
inspection semantics; they are not promoted to exact full-posterior counts.

### Ambiguity, boundaries, rules, and candidate scaling

The JSONL scans validate every required row and preserve segment identity/order
across 'analyses.jsonl' and 'boundary_posteriors.jsonl'.

The ambiguity table covers exact full-posterior identity/latent mass and
entropy, plus explicitly top-k-only top-1, reported mass, residual, margin, and
top-k effective ambiguity. Valid top-analysis latent units are retained in
bounded evidence samples as script-neutral form keys and phoneme IDs.

Boundary reductions include expected boundaries per segment and phoneme,
posterior and binary-entropy distributions, present/absent/decision confidence
thresholds, and cue-kind breakdowns. Spaces and other orthographic cues are
always labelled reference evidence, never gold lexical boundaries.

Rule reductions retain exact global totals, coverage, normalized distribution,
entropy/effective rule count, top-N mass, and normalization by segments,
expected boundaries, and phonemes. Rule diagnostics reconstructed from reported
segment analyses are separately labelled bounded top-k approximations.

Candidate reductions retain factor/node/edge/overflow distributions,
edges per phoneme, optional raw/retained internal-match fields when present,
one-pass relationships to length/entropy/identity/latent mass, and heavy-tail
edge shares for the top 0.1/1/5% of segments. Heavy-tail shares use the same
bounded 1/8-octave histogram and therefore state their within-bin
approximation. Per-document and compact phoneme-length strata are separate
tables.

### Runtime and cross-cell stability

Runtime/resource evidence remains separate from scientific distributions.
Timers, counters, lexical scorer/cache/SQLite totals, process-tree resources,
and edges/characters/phonemes per wall second retain inclusion notes where
timers nest.

Cross-cell archival comparisons do not duplicate the formal scalar gate.
They retain exact top-K support overlap, shared-head rank correlation, a
top-10,000 weighted L1 comparison with one aggregate tail bucket, and bounded
bottom-2,048 MinHash estimates for high-mass support. Boundary comparisons are
labelled posterior/orthographic reference comparisons, not agreement with gold.
No full-tail Jaccard or giant exact support store is created.

## Approximation labels

Counts, sums, source identities, pass rows, sorted-head mass, lexicon diversity,
discrete length distributions, global rule usage, and boundary expectations are
streamed exactly up to normal floating-point arithmetic.

Arbitrary-valued distribution quantiles use a deterministic 1/8-octave log2
histogram with midpoint reporting. High-mass support overlap uses deterministic
bottom-2,048 MinHash. Candidate heavy-tail shares use histogram-bin means.
Every affected table row records its method/scope. Top-k inspection artifacts
remain labelled top-k; the reducer never describes their residual tail as
exactly enumerated.

## Compact outputs

The output directory contains:

    manifest.json
    cells.tsv
    pass_dynamics.tsv
    lexicon_distribution.tsv
    lexical_length.tsv
    reuse_distribution.tsv
    ambiguity_distribution.tsv
    boundary_distribution.tsv
    rule_usage.tsv
    candidate_scaling.tsv
    document_distribution.tsv
    length_strata.tsv
    runtime_breakdown.tsv
    pairwise_stability.tsv
    evidence_samples.jsonl
    summary.md

The evidence reservoir is selected before interpretation using deterministic
bounded rules: hash-selected lines, entropy/low-top1/residual extremes, large
graphs, long forms, high-mass long forms, high context/variant counts,
low-count forms, common/low-usage rules, overflow, confident/ambiguous
boundaries, and large cross-condition metric differences. Every item retains a
cell and stable source ID.

## Validation performed

Focused six-cell fixtures cover deterministic repeated reduction, compact
output creation, source-byte immutability, overwrite refusal, audited source
identities, script-specific phoneme denominators, analysis/boundary identity
agreement, top-k mass consistency, and declared lexicon row counts.

The fixture suite does not scan any real or large artifact.

The complete repository suite passed with 546 tests and 4 pre-existing
PyTorch/SentencePiece warnings in 48.30 seconds.

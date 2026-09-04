# Association-specialization analysis

scripts/analysis/analyze_association_specialization.py is the reusable,
fail-closed analysis entry point for compact scorer/surface/context association
state. Experiment-specific cells, paths, comparison directions, bins, and
diagnostic criteria belong in a JSON manifest.

The implementation reads only:

- final_scorer.tsv.gz;
- surface_usage.tsv.gz;
- context_usage.tsv.gz;
- the compact manifest.json and SHA256SUMS.

It does not open raw SQLite, rerun a learner, alter an input, sort to temporary
storage, or load a complete table into RAM. It validates the exporter schema
and provenance, small-manifest identity, declared compressed-file sizes and
hash identities, exact headers, numeric values, duplicate pairs, and the
exporter's ordering contract while streaming. Large compressed payload hashes
are referenced from a preverified SHA256SUMS; they are deliberately not
recomputed.

## Metrics

For each form_key and association axis, positive masses are normalized as
p_i = mass_i / sum_i mass_i. The outputs report:

- positive support size;
- top-1 and configured top-k share;
- Shannon entropy H = -sum p_i ln(p_i) in nats;
- normalized entropy, defined as zero for support one and H / ln(n) for
  support greater than one;
- Shannon effective support exp(H);
- Herfindahl/Simpson concentration sum p_i^2;
- Simpson effective support 1 / sum p_i^2.

Zero-total groups receive N/A specialization metrics. All masses must be
finite and nonnegative. phoneme_length is the number of validated canonical
Phoneme IDs in the dot-separated, script-neutral form_key; it is neither
Unicode code-point length nor a morphological analysis.

Summaries expose three distinct weighting views:

- unweighted lexical-type means;
- final-scorer training_expected_count weighted means;
- axis-specific association-expected-mass weighted means.

The scorer/association totals are intentionally not required to be equal.
final_scorer is final-training-pass state. Surface associations are
thresholded inspection expected counts, while context associations are derived
from retained top-K inspection analyses above the usage threshold.

## Sorting and memory contract

The compact exporter guarantees:

    final_scorer:  form_key ASC
    surface_usage: form_key ASC, surface ASC
    context_usage: form_key ASC, context ASC

The analyzer verifies strict order and rejects duplicate association pairs.
It performs one grouped pass per input and an outer merge by form_key across
cells. State is bounded by one current group per cell, fixed-size summary/bin
accumulators, and the configured diagnostic reservoirs. It never silently
sorts malformed input.

Exact form_key matching is performed only when a comparison manifest declares
SUPPORTED alignment and both cells declare the same namespace. An UNSUPPORTED
comparison emits an explicit scientific N/A summary and no matched-form rows.

## Outputs

Publication is atomic and refuses an existing destination. The stable output
set is:

    per_form_metrics.tsv.gz
    comparison.tsv.gz
    cell_summary.json
    comparison_summary.tsv
    comparison_strata.tsv
    length_bins.tsv
    count_bins.tsv
    joint_bins.tsv
    relationship_summary.tsv
    diagnostic_examples.tsv
    manifest.json
    SHA256SUMS

comparison.tsv.gz classifies every union form as shared, cell_a_only, or
cell_b_only and reports matched deltas as cell B minus cell A.
comparison_strata.tsv separately summarizes those classes and shared forms
whose count increased by the manifest's fixed ratio. Diagnostic examples are
selected mechanically from manifest thresholds; no morphology is inferred or
annotated.

## S1M1 command

The S1M1 manifest uses only the two preverified retained Devanagari compact
states. The full scan is intentionally an external researcher-run operation:

    PYTHONPATH="$PWD/src" python3 scripts/analysis/analyze_association_specialization.py \
      --manifest configs/analysis/s1m1_association_microanalysis.json \
      --output-dir artifacts/s1m1_final/association_microanalysis

Do not run this command merely as a smoke test: its declared inputs contain
tens of millions of rows. Use the focused synthetic pytest module for cheap
validation.

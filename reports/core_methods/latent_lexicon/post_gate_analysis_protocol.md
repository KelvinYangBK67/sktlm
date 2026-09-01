# Post-gate analysis protocol for the unrestricted six-representation gate

Status: **frozen analysis specification; no gate result is reported here**.

This protocol fixes how the unrestricted six-representation S1M1 gate will be
validated and analysed after natural completion. It is neither a result report
nor the independent-review protocol. No threshold or comparison may be added
merely because the completed result looks favourable.

## Closure order

The formal order is:

    natural completion
    -> process_tree_summary.json return_code == 0
    -> final audit valid == true
    -> human collection
    -> local collected-artifact validation
    -> six-cell aggregation
    -> preregistered quantitative comparison
    -> preregistered qualitative inspection
    -> interpretation
    -> S1M1 freeze decision

A later step cannot repair a failed earlier gate. RUNNING, a live PID, a partial
checkpoint, or an early process sample is not completion evidence.

## Fixed input contract

The local input manifest must name exactly one audited unrestricted run for
each formal cell:

1. IAST + `surface_word`;
2. IAST + `legacy_joined`;
3. IAST + `continuous`;
4. Devanagari + `surface_word`;
5. Devanagari + `legacy_joined`;
6. Devanagari + `continuous`.

The chosen IAST `surface_word` run must be one of the already accepted,
byte-identical replicas and its exact run identity must be recorded. The other
five inputs are collected only after their natural completion and final audit.
K16/K32, baseline conditions, scoped benchmarks, and any other condition are
not substitutes.

Every cell record explicitly supplies `run_id`, `metrics_id`, script,
condition, scientific commit, local run directory, local metrics directory,
and final-audit path. Relative paths are resolved against the input manifest;
there is no hidden artifact root. If the six inputs span more than one Git
commit, the manifest must list the exact commit set and an approved
cross-commit compatibility basis with tracked evidence. Undeclared mixed-SHA
input fails closed. This makes explicit the already-recorded gate design in
which accepted IAST `surface_word` replicas supply one cell and the five new
cells use the representation-gate checkpoint.

## Fail-closed local validation

`scripts/analysis/aggregate_six_representation.py` performs no SSH, audit,
collection, download, or source-artifact mutation. Before computing a
comparison it requires:

- exactly six formal cell identities, with no duplicate cell, run ID, or
  metrics ID;
- explicit traceable Git provenance for every cell;
- identical non-identity scientific configuration across cells;
- identical M0 freeze, representation-manifest hash, sandhi-rule hash/count,
  implementation identity, document count, and seed;
- unrestricted full-corpus configuration: no vocabulary budget, document list,
  document limit, or line limit;
- a completed checkpoint and a local `process_tree_summary.json` with
  `return_code == 0`;
- a final audit with `valid == true`, no failures, the same provenance, the
  same process summary, and the same run/representation identity;
- all canonical scientific files plus config, checkpoint, provenance, timing,
  and inspection report;
- local bytes and SHA-256 for each canonical scientific artifact equal to the
  final audit.

Any failure emits machine-readable diagnostics and produces no scientific
comparison. The output directory is created atomically only after successful
validation and is never overwritten.

The aggregator does not add a new rule that nonzero candidate overflow is
itself invalid. It reports overflow as a candidate-support diagnostic. The
independent final audit remains an upstream prerequisite and governs the
validity of the collected run under the frozen run contract.

## Fixed quantitative metrics

### Latent structure

For every cell report:

- active lexical types;
- expected lexical tokens from the inspection summary;
- independently streamed lexical expected-count total;
- total and mean identity posterior mass;
- total and mean latent posterior mass;
- mean top-1 posterior;
- mean posterior entropy;
- low-count type count, threshold, and fraction;
- raw and weighted complexity summary.

The lexicon TSV must already be ordered by `expected_count DESC, form_key ASC`.
The local reader checks this ordering and uses a bounded-memory two-pass scan.
It reports the smallest lexical type count reaching 90%, 95%, 99%, 99.9%, and
99.99% cumulative expected-count mass. Exact floating ties use `form_key ASC`;
no unstable input order is accepted.

### Candidate structure

Report documents, segments, characters, candidate factors, lattice nodes,
lexical edges, overflowed tokens, and overflowed tokens per segment. Overflow
is descriptive and is not automatically translated into a linguistic claim.

### External-sandhi usage

Preserve every rule ID and report total expected usage, normalized expected
usage, the 20 highest-usage rules ordered by `expected_usage DESC, rule_id
ASC`, and zero/nonzero usage coverage. Normalization uses the complete rule
inventory emitted by `rule_usage.tsv`.

### Runtime and engineering

Keep these separate from scientific-quality metrics:

- wall time;
- peak process-tree RSS;
- sampled process-tree CPU seconds;
- peak process count;
- sampled read bytes;
- sampled write bytes;
- logical CPU count.

## Fixed paired comparisons

The pair direction is always A to B and is recorded in every row.

Script pairs hold spacing fixed:

- IAST -> Devanagari for `surface_word`;
- IAST -> Devanagari for `legacy_joined`;
- IAST -> Devanagari for `continuous`.

Spacing pairs hold script fixed, separately for IAST and Devanagari:

- `surface_word` -> `legacy_joined`;
- `surface_word` -> `continuous`;
- `legacy_joined` -> `continuous`.

For each suitable scalar, report A, B, `B-A`, `abs(B-A)`,
`(B-A)/abs(A)`, and `B/A`. If A is zero, signed and absolute differences
remain defined while relative difference and ratio are null with an explicit
`denominator_zero` flag. No epsilon is inserted.

For normalized rule distributions on the union of rule IDs, report:

    TV(P,Q) = 1/2 * sum_i |P_i - Q_i|

and Jensen-Shannon divergence in nats using the natural logarithm. Zero
probability terms contribute zero. If either cell has zero total expected rule
usage, the normalized-distribution comparison is explicitly unavailable
rather than silently normalized.

The tooling reports descriptive statistics only. It does not print “script
invariant”, “spacing dominates”, or any equivalent conclusion.

## Deterministic qualitative inspection

Qualitative inspection uses the same logical material across all six cells.
The unit for cross-representation selection is `(relative document path,
line_number)`; all selected material is expanded to all available segments for
that logical line in every condition.

Before interpretation, select and freeze:

- 20 anchor logical lines by ascending SHA-256 of
  `freeze_id + "\0" + relative_path + "\0" + line_number` from the
  intersection present in all six cells;
- the union across cells of the 20 highest top-1 posteriors and 20 highest
  entropies, with segment ID as the secondary order;
- for every formal pair, the union of the 20 largest absolute differences in
  identity mass, top-1 posterior, and entropy after logical-line alignment;
- the 20 continuous-condition boundaries with highest binary entropy, with
  cell and boundary identity as secondary order;
- the 20 highest expected-usage rules, followed back to examples in every cell;
- the 20 lowest positive-count lexical identities and 20 highest-count
  identities per cell, with `form_key ASC` tie-breaking;
- up to 20 overflow-associated logical lines per cell in canonical identity
  order when the artifacts can localize them.

The union, its selection reason, source IDs, and selection code/version are
frozen before reading examples for interpretation. Empty strata are recorded
as empty. This protocol does not permit replacing difficult examples with
more attractive ones.

## Interpretation discipline

The continuous condition asks whether fixed external realization grammar plus
corpus-wide lexical reuse recover useful latent lexical-boundary structure
without a visible whitespace cue. It is not a test of unique gold morphology.
Canonical surface whitespace may serve as reference/evaluation evidence but
must not flow back into continuous training supervision.

A single MAP segmentation is not unique true morphology. Interpretation must
distinguish posterior mass, ambiguity/equivalence, reusable structure,
stability, economy, and predictive/generalization utility. Script conclusions
require all three audited spacing-matched script pairs. Spacing conclusions
require the six preregistered within-script pairs. Engineering resource metrics
must not be treated as model quality.

## Deterministic outputs and later command

A successful local run writes:

- `aggregation.json` with validation, provenance, cell metrics, pair metrics,
  and rule-distribution metrics;
- `cells.tsv`, `pairs.tsv`, `rule_usage.tsv`, and `rule_distances.tsv`;
- `summary.md`, containing tables but no automatic scientific conclusion.

After human audit and collection, prepare a filled local manifest from the
tracked template and run once:

    ./.venv/bin/python scripts/analysis/aggregate_six_representation.py \
      --manifest artifacts/post_gate/six_representation_gate_input.json \
      --output-dir artifacts/post_gate/six_representation_gate_aggregation

The canonical-artifact hashes and large lexicon scan may take more than five
minutes on the full collected payload. This command is therefore human-only;
Codex must not launch or poll it while the cloud gate is active.
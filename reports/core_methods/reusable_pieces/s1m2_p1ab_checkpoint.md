# S1M2-P1a/P1b production semantics and lazy candidates

Status: **coherent checkpoint; P1 is not complete; P1c composed exact
inference remains open**.

This checkpoint records the production scoring semantics and removes persistent
lexical-edge rows from the production candidate representation. It does not
implement the shared/composed piece-inference kernel, a full trainer, or any
full-corpus path.

## Production unseen-piece semantics

Let Sigma be the complete finite script-neutral 'Phoneme' enum and let q be
'base_stop_probability', strictly between zero and one. For every nonempty
piece p of length l:

    H(p) = q (1 - q)^(l - 1) |Sigma|^(-l)

Length is geometric and symbols are uniform over Sigma. H is normalized over
all finite nonempty phoneme sequences and is evaluated analytically; it is
never enumerated.

For a fixed pass, A is the finite active piece-count map, N is the sum of its
positive counts, and:

    P(p) = (count_A(p) + alpha H(p)) / (N + alpha)

An inactive or not-yet-materialized legal piece has count zero and positive
base mass. Candidate enumeration therefore does not change a denominator V,
and arbitrary unseen whole-form pieces remain exactly scoreable.

The existing complexity term is unchanged:

    log P(p)
      - lambda (kappa + beta len(p))
        log(1 + 1 / (tau + count_A(p)))

This adds no reward for using sandhi and no Sanskrit-specific or morphological
label. Singleton and whole-form segmentations remain legal competitors, and
every piece path still concatenates exactly to the grammar-licensed lexical
form.

## Fixed-pass and cross-pass inventory

The active map is frozen throughout one exact inference pass. Between tiny
synthetic passes, a piece becomes a persistent parameter only if:

- it is a singleton observed in the candidate piece support; or
- it has positive conditional posterior support in at least
  'min_reuse_occurrences' distinct observed lexical-form occurrences
  (default 2).

All other legal pieces remain inactive but scoreable through H. The activation
step changes the finite parameter state between passes; it does not prune the
legal inference candidate set. 'support_epsilon' is explicit and defaults to
zero.

The helper 'fit_production_piece_model' is intentionally tiny and in-memory. It
is a multi-pass correctness gate, not a streaming corpus trainer.

## Difference from P0

P0 is unchanged and remains the numerical oracle. Its
'ExpectedCountPieceScorer' still uses:

    (count(p) + alpha) / (N + alpha V)

over the current reference count inventory. The new
'BaseMeasurePieceScorer' is the production fixed-pass scorer and uses H instead
of V. P0 lattices, forward/backward, top-k inspection, and tests were not
rewritten.

## Lazy candidate representation

'src/sktlm/latent/lazy_candidates.py' preserves the existing M1:

- visible boundary-option construction and fixed grammar matching;
- internal-node construction, overflow behavior, and ordering;
- avagraha legality, vowel legality, direct/grammar boundary metadata;
- whitespace-merge membership and penalty metadata.

The graph stores token nodes but not a tuple of materialized
'LexicalEdge(word)' rows. When traversal requests node pair (i,j), the
transient span derives:

    left.right_underlying
      + phonemes(surface gap)
      + right.left_underlying

and the same boundary/rule/identity metadata. A comparator-only adapter
materializes spans for tiny fingerprint tests; production inference must not
call it.

## Focused validation

The following focused set passed:

    python -m pytest \
      tests/pieces/test_p1ab_checkpoint.py \
      tests/pieces/test_reference_piece_model.py \
      tests/latent/test_frontend_and_candidates.py -q

Result: 19 passed in 0.35 seconds.

Changed Python files also pass syntax compilation, and 'git diff --check'
passes. No full suite was run for this quota-limited checkpoint.

## P1c remains

P1c must implement an exact shared/composed piece kernel over lazy spans,
without an independent P0 'PieceLattice' per lexical form and without a beam.
Required tiny oracle gates still include:

- per-form prior normalizer, log score, and expected piece counts versus P0;
- lazy/materialized outer log partition and lexical expected counts;
- composed expected piece counts;
- identity/latent mass, expected lexical tokens, boundary posteriors, rule
  usage, and total posterior mass;
- instrumentation for candidate traversal, composed states/transitions,
  scoring/cache/store lookups, and explicit bounded pass-local cache state.

No claim of completed P1, production trainer readiness, or full-corpus
readiness is made here.

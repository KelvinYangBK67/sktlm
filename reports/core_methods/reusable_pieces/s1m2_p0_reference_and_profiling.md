# S1M2-P0 reference reusable pieces and M1 profiling

Status: **reference semantics implemented; production exact engine not
selected; full-corpus M2 not started**.

This checkpoint adds a deliberately simple numerical oracle for S1M2 and a
bounded, read-only profiler for the frozen M1 engine. It does not connect M2 to
the streaming/full-corpus trainer and does not implement a shared-prefix,
composed, or lazy production architecture.

## Reference semantics

For a script-neutral latent lexical form `u` with `n` phonemes, the piece DAG
has positions `0..n`. An edge `(i,j)` emits the exact phonological slice
`u[i:j]`. Every nonempty slice of length at most `max_piece_length` is legal,
and `(0,n)` is always legal even when the form exceeds that bound. Consequently
every complete path satisfies exact concatenation and both all-singleton
atomization and whole-form memorization remain genuine competitors.

For a segmentation `s=(p1,...,pk)`, the raw independent-boundary prior is

```text
(k - 1) log rho + (n - k) log(1 - rho).
```

The prior-only partition `Z0(u)` is computed by exact forward DP on the same
legal DAG. Each segmentation weight subtracts `log Z0(u)`, so neutral piece
scores give `PieceModel.score(u) = 0` regardless of form length or how many
legal segmentations survive the piece-length restriction.

The learned reference energy is exactly

```text
piece_score(p)
  = log P(p)
    - lambda * (kappa + beta * len(p))
      * log(1 + 1 / (tau + count(p)))

P(p) = (count(p) + alpha) / (N + alpha * V).
```

`PieceModel.evaluate(u)` uses exact forward/backward marginalization and
returns the normalized lexical-form log score, exact expected piece counts, and
only a bounded top-k inspection list. `PieceModel.score(u)` implements the
existing M1 `FormScorer` protocol. Evaluations are cached by
`PhonologicalForm` within a model/pass.

Outer-to-inner expected counts use the reference identity

```text
E[count(p) | x]
  = sum_u E[count(u) | x] * E[count(p) | u].
```

The tiny in-memory fitting loop starts with neutral piece scores, aggregates
fractional counts for every legal piece, constructs the declared count/MDL
scorer, and repeats. It is a synthetic correctness path only.

The `log P(p)` term is normalized over the current piece inventory, while the
combined variable-length segmentation score is intentionally the declared
energy/reweighted-MDL objective rather than a newly claimed normalized
generative distribution over all lexical forms. P0 does not alter the requested
formula to resolve that distinction.

## M1 runtime profiler

`python -m sktlm.latent.profiling` (installed entry point
`sktlm-profile-m1`) opens an existing unrestricted `learner.sqlite` read-only,
loads its exact scientific configuration, and runs unchanged training-time M1
inference on a bounded subset. Profiling values never feed into candidate or
posterior decisions. The command refuses fixed-vocabulary runs, mismatched
expected script/condition values, zero-sized bounds, empty subsets, and an
existing output path.

The result fingerprint hashes graph-size invariants plus all exact
training-inference scalar and expected-count results. A regression test runs
the same segment with profiling off and on and requires identical graph and
result fingerprints and equal inference objects.

Timing fields are nested rather than incorrectly presented as independent:
`inference_seconds` includes lexical scoring, and `lexical_scoring_seconds`
includes SQLite selects. Exclusive derived fields are also emitted.

### Fixed manual comparison commands

Run these only after the corresponding M1 job has completed naturally and a
valid run directory containing `config.json` and `learner.sqlite` is available
in the checkout where the command is executed. P0 did not contact or inspect
the active hosts.

Devanagari `legacy_joined`:

```text
python -m sktlm.latent.profiling --run-dir artifacts/latent_benchmarks/cloud_full_m0_devanagari_legacy_joined_p10_w8_p3 --repo-root . --document-list configs/benchmarks/latent_smoke_documents.txt --max-documents 1 --max-lines-per-document 5 --max-segments 32 --expected-script devanagari --expected-condition legacy_joined --output artifacts/m1_profiles/devanagari_legacy_joined_aitup_5lines.json
```

Devanagari `continuous`:

```text
python -m sktlm.latent.profiling --run-dir artifacts/latent_benchmarks/cloud_full_m0_devanagari_continuous_p10_w8_p3 --repo-root . --document-list configs/benchmarks/latent_smoke_documents.txt --max-documents 1 --max-lines-per-document 5 --max-segments 32 --expected-script devanagari --expected-condition continuous --output artifacts/m1_profiles/devanagari_continuous_aitup_5lines.json
```

Both commands select the same first smoke document,
`1_veda/4_upa/aitup__u.txt`, and the same first five physical lines. Do not
change bounds between the pair. Stop rather than extend the run if either is
projected to exceed five minutes.

### Field meanings

| Field | Meaning |
|---|---|
| `documents`, `lines`, `segments` | Actually processed bounded subset units. |
| `characters` | Python code-point length of observed segment strings. |
| `phonemes` | Script-neutral frontend phoneme count. |
| `candidate_factors` | Outer token/merge factors constructed by M1. |
| `raw_internal_matches` | Grammar matches surviving each factor's prefix/suffix window before the frozen overflow fallback, summed over factor lattices. |
| `retained_internal_matches` | Those matches retained after the unchanged overflow rule. |
| `lattice_nodes` | Token-lattice nodes, including start/end nodes, summed over factor lattices. |
| `lexical_edges` | Complete latent lexical-form edges scored by outer M1. |
| `overflowed_tokens` | Existing per-graph overflow count; the bound and fallback are unchanged. |
| `unique_lexical_forms` | Distinct script-neutral edge/merge forms in the bounded subset. |
| `candidate_build_seconds` | Wall time inside unchanged candidate construction. |
| `inference_seconds` | Wall time inside exact training inference, including lexical scoring. |
| `lexical_scoring_seconds` | Time inside calls to the existing lexical scorer, including its SQLite lookups. |
| `sqlite_seconds` | Existing scorer timing for SQLite lexical-row selects only. |
| `inference_non_scoring_seconds` | `inference_seconds - lexical_scoring_seconds`, floored at zero. |
| `lexical_scoring_non_sqlite_seconds` | `lexical_scoring_seconds - sqlite_seconds`, floored at zero. |
| `score_calls` | Calls reaching the persistent M1 lexical scorer after segment-local memoization. |
| `cache_hits`, `cache_misses` | Existing bounded lexical-score LRU outcomes. |
| `sqlite_selects` | Cache-miss lexical-row selects. |
| `edges_per_segment`, `edges_per_phoneme` | Candidate-density diagnostics. |
| `unique_forms_per_lexical_edge` | Potential cross-edge inner-evaluation reuse ratio. |
| `seconds_per_lexical_edge` | Inclusive inference seconds divided by lexical edges. |
| `result_fingerprint` | Deterministic hash of graph-size/result values, not a scientific metric. |

## Validation

- New P0 plus profiler tests: `12 passed in 0.31s`.
- New piece tests plus all existing latent tests: `55 passed in 9.19s`.
- Full repository suite: `554 passed, 2 warnings in 31.70s`; both warnings are
  the existing PyTorch nested-tensor warning.
- No corpus experiment, VM operation, cloud benchmark, or full M2 run was
  performed.

## P1 questions deliberately left open

The paired profiles must be inspected before selecting a production exact M2
architecture. In particular:

1. Does `continuous` time primarily track factor-expanded internal matches,
   nodes, and quadratic lexical edges during candidate construction?
2. How small is `unique_lexical_forms / lexical_edges`, and therefore how much
   exact reuse is available from shared/batched inner evaluation alone?
3. After segment-local and persistent cache effects, is lexical scoring/SQLite
   material, or is exact outer DP over the dense graph dominant?
4. Would shared-prefix/shared-inner DP remove the measured dominant work, or
   does the outer graph itself require a composed/lazy exact representation?

No shared-prefix trie, shared inner DP, joint reverse pass, composed lattice,
or lazy lexical-span engine is selected or implemented at this checkpoint.

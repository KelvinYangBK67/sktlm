# S1M2 reusable-piece research reports

S1M2 is in progress. This index orders the tracked scientific and
implementation record; it is navigation, not a new scientific checkpoint or a
claim of full-corpus readiness.

## Scientific contract and roadmap

- [Research roadmap](../../../docs/research_roadmap.md) — defines S1M2's
  reusable, untyped, script-neutral pieces and exact-concatenation boundary
  within the larger S1–S3 program.

## P0 — Exact reference semantics

- [P0 reference and M1 profiling](s1m2_p0_reference_and_profiling.md) — read
  this for the numerical oracle, legal piece support, normalized boundary
  prior, exact expected counts, and the profiling questions that motivated the
  production architecture.

## P1a / P1b — Production scoring and lazy lexical spans

- [P1a/P1b checkpoint](s1m2_p1ab_checkpoint.md) — specifies countable-base
  scoring for active and unseen pieces, between-pass activation, and the lazy
  candidate representation without persistent lexical-edge rows.

## P1c — Exact shared/composed inference

- [P1c closure](s1m2_p1c_closure_20260905.md) — records the completed exact
  shared/composed inference kernel and its P0/materialized equivalence gates.
- [P1c readiness checkpoint](s1m2_p1c_readiness_20260905.md) — preserves the
  historical pre-implementation contract and synchronized ancestry that the
  closure superseded.

## Trainer integration

- [Streaming-trainer integration](s1m2_trainer_integration_20260905.md) —
  records fixed-pass piece state, bounded-memory training, deterministic
  resume/parallel behavior, and emitted scientific artifacts.

## Continuous profiling and exact optimization

- [Continuous benchmark, profiling, and optimization record](s1m2_continuous_benchmark_definition_20260905.md)
  — freezes matched M₀′/Devanagari workloads and tracks the completed
  profiling gates, exact optimizations, and still-open runtime/storage path.

## Machine-readable evidence

- [`evidence/`](evidence/) — compact tracked envelopes for the frozen workload,
  representative measurement, paired probes, and accepted or rejected exact
  optimization decisions; bulk artifacts remain outside Git.

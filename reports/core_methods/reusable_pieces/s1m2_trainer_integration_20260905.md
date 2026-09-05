# S1M2 streaming-trainer integration

Date: 2026-09-05

```text
S1M2_TRAINER_INTEGRATION=COMPLETE
RESUME_EQUIVALENCE=PASS
FULL_M0_PROCESS_RUNNING=NO
FULL_M0_PROCESS_COMPLETED=NO
```

This checkpoint integrates the exact P1c reusable-piece model into the
existing streaming trainer. It does not claim continuous performance
readiness, six-cell bounded validation, or authority to start full-M0.

## Fixed-pass and between-pass computation

`reusable_pieces_v1` builds P1b lazy candidates and invokes P1c directly.
Pass 1 uses neutral piece scores. Every later pass reads the finite active
piece state from SQLite and applies the P1a score

```text
(count_A(p) + alpha H(p)) / (N + alpha)
```

plus the declared length-aware complexity increment. The active state is
immutable during a pass and is replaced transactionally between passes. An
inactive legal piece remains analytically scoreable through `H`; activation
never prunes legal support.

The trainer retains every positive expected piece count in the diagnostic
inventory. Persistent scoring parameters are positive-count singletons plus
longer pieces supported in at least `min_reuse_occurrences` distinct observed
lexical-form occurrences. With the default `support_epsilon=0`, support means
positive joint posterior mass under the numerical inference contract.
Alternative derivations of the same form at the same observed interval are
deduplicated for this support count. The full expected count, including piece
multiplicity within a form, is accumulated separately.

Lexical-form expected counts are stored and exported as diagnostics; they are
not S1M2 scoring parameters. A fresh P1c engine is constructed after each
piece-state update, so no mutable pass-specific state can leak across passes.
Training does not construct inspection paths. Bounded top-K piece
segmentations are produced only by final inspection and never restrict exact
inference support.

## Streaming, durability, and determinism

Serial training streams one document inside one SQLite transaction. Parallel
training writes checksum-protected, per-document shards and reduces them in
canonical document order with bounded rolling submission. S1M2 shards contain
separate lexical-diagnostic and piece-count/support rows. The durable SQLite
checkpoint is committed in the same transaction as each document's counts;
the JSON checkpoint is synchronized afterward. Pass finalization atomically
replaces the prior active piece map.

Resume validates the complete configuration identity. The frozen S1M1
configuration signature remains backward compatible: the default S1M1
payload omits the new model selector and all S1M2-only fields. S1M2 identities
include every scientific piece parameter and every engineering cache bound.

Scientific iteration history excludes cache-hit and store-lookup counters
whose values legitimately depend on an interruption boundary. Those counters
remain available in `timing_metrics.json`; cache entry and estimated-byte
gauges record observed maxima. This preserves byte-identical scientific
resume artifacts while retaining engineering evidence.

## Scientific and engineering artifacts

The S1M2 path emits:

- `piece_inventory.tsv`, including expected count, occurrence support,
  active state, active parameter count, probability, length, and score;
- `lexical_diagnostics.tsv`, including expected count and bounded
  surface/context summaries;
- exact segment analyses with aligned bounded top-K piece segmentations;
- boundary posteriors, external-rule usage, identity/latent mass, ambiguity,
  expected lexical and piece tokens;
- segmentation entropy, whole-form, singleton-path, and multi-piece mass;
- piece length, reuse, low-support, active-state, and complexity summaries;
- configuration, provenance, checkpoint, pass history, timing/counter data,
  SQLite state, and a human inspection report.

Inspection posterior paths are presentation-only. Exact lexical counts,
piece counts, boundaries, rules, and mass are accumulated from forward/backward
marginals rather than from the bounded display list.

## Validation

The bounded trainer fixture uses two documents, two passes, cross-form piece
reuse, and deliberately small flush bounds. It verifies:

- active piece-state creation and P1a SQLite scoring for active and inactive
  pieces against the in-memory production scorer;
- readability and content of the required scientific artifacts;
- finite cache counters and byte gauges;
- no top-path construction in the training kernel;
- byte-identical scientific output after a simulated interruption immediately
  after a durable document commit;
- byte-identical scientific output between one and two workers.

Validation results:

```text
focused S1M2/P1c/frontend tests: 34 passed
tests/pieces + tests/latent:     76 passed
full repository suite:          633 passed, 2 warnings
git diff --check:               passed
```

The warnings are the existing PyTorch nested-tensor warnings. No frozen
corpus, M0/M0-prime manifest or representation, sandhi rule, S1M1 artifact,
or `notes/**` content was changed.

## Next boundary

Freeze deterministic representative and long-span continuous benchmark
definitions, extend low-overhead profiling for missing continuous-specific
phases/resources, and measure the new S1M2 path before optimizing it. No
production-shaped workload has been launched at this checkpoint.

```text
S1M2_CONTINUOUS_PROFILING=READY_TO_START
```

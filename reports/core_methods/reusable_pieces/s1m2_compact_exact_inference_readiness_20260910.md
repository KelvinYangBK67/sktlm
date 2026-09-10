# S1M2 compact exact inference readiness checkpoint

Date: 2026-09-10

```text
ROUND2_FORMAL_SCIENTIFIC_STATUS=FAIL_CANDIDATE_OVERFLOW
COMPACT_EXACT_INFERENCE=READY_FOR_DESIGN_AUDIT
FULL_M0_AUTHORIZED=NO
```

## Scientific invariants

- Legal latent-analysis support is unchanged.
- Stage-1 sandhi grammar and lexical-boundary semantics are unchanged.
- Reusable-piece support and whole-form-piece legality are unchanged.
- All lexical, boundary, piece, and complexity scoring equations are unchanged.
- Inference remains exact: no truncation, pruning, beam, sampling, or approximate fallback.
- Posterior-derived scientific quantities and pass-to-pass expected-count semantics are unchanged.
- Top-K remains presentation-only and must not affect inference support or marginals.
- The current exact kernel remains the validation oracle wherever it completes.

## Engineering freedom

The refactor may change span materialization, DP state representation,
tries/DAGs/automata, traversal order, bounded caches, recomputation,
multiprocessing internals, counters, and timing instrumentation.

These changes are engineering-only and must not change scientific output.

## Equivalence requirement

Manageable old/new cases should remain byte-identical where feasible.
If floating-point accumulation order alone prevents byte identity, a strict
numerical comparator must be fixed before broad validation. Discrete support,
analysis identity, deterministic ranking, and top-K tie behavior remain exact.

## Exact next boundary

The next task is a read-only architecture audit. It must identify the smallest
compact exact representation that removes the long-token candidate-overflow
blocker while satisfying all invariants above. No implementation, workload
rerun, VM execution, or Full-M0 launch is authorized by this checkpoint.
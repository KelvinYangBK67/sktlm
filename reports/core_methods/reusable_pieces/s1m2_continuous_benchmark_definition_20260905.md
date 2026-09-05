# S1M2 continuous benchmark-definition freeze

Date: 2026-09-05

```text
S1M2_TRAINER_INTEGRATION=COMPLETE
CONTINUOUS_BENCHMARK_SELECTION_RULE=FROZEN
CONTINUOUS_STATIC_SCAN=READY_TO_LAUNCH
```

This checkpoint freezes workload selection before any S1M2 continuous timing
or optimization result is observed. It does not select documents from model
runtime, launch a model benchmark, or authorize full-M0.

## Inputs

The tracked configuration is
`configs/benchmarks/s1m2_continuous_selection.json`. It names exactly:

- validated M0-prime IAST `continuous`, frontend `iast_m0_prime`, manifest
  SHA-256 `3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`;
- frozen M0 Devanagari `continuous`, frontend `devanagari`, representation
  manifest SHA-256
  `c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520`.

The scan trusts the already validated per-file manifest hashes instead of
rehashing the full frozen/derived corpora. It does fail closed on manifest
identity, freeze ID, document membership, file presence, and recorded byte,
character, line, and (where present) phoneme counts.

## Static measurements and fixed selection

`sktlm.latent.continuous_structure` streams documents and observes only
frontend/static structure:

- bytes, written characters, lines, and phonemes;
- punctuation-delimited continuous span lengths;
- punctuation delimiter count;
- exact p50/p90/p95/p99/max span summaries;
- sum of span phonemes and sum of squared span lengths as a declared
  materialization-pressure proxy.

It builds no grammar candidate graph, computes no posterior, uses no learned
state, and measures no runtime outcome. It also requires per-document equality
of total phonemes and the ordered continuous-span-length digest between the
two frontends.

The Devanagari cell is the selection basis. The stress workload is the first
two documents under `(maximum span, sum of squared span lengths, phonemes)`
descending with relative path as the final ascending tie break. Those rows are
removed before representative selection. Remaining documents are ranked by
`(sum of squared span lengths, maximum span, phonemes, relative path)` and the
nearest distinct rows at the fixed 25th, 50th, and 75th percentile ranks are
selected. This rule cannot be changed after observing benchmark timings.

The full static summary supplies corpus totals for character-, document-, and
span/complexity-weighted runtime projections. The emitted document lists will
be promoted under `configs/benchmarks/` only after the detached scan passes
identity and completion validation.

## Validation and detached boundary

Tiny tests require deterministic output, the fixed representative/stress
selection behavior, cross-frontend structural identity, and fail-closed
behavior for a frontend mismatch. Focused continuous-structure,
representation-frontend, and M0-prime tests pass (`26 passed`). `git diff
--check` passes.

The one-time 240-document/two-frontend scan is conservatively treated as a
greater-than-five-minute workload because it parses roughly 199 MB of text.
It must be launched once from a clean committed checkout with durable logs,
an exact attempt identity, a non-overwriting output directory, and a recorded
Git/config identity. It is a static scan, not an S1M2 training run.

```text
FULL_M0_PROCESS_RUNNING=NO
FULL_M0_PROCESS_COMPLETED=NO
```

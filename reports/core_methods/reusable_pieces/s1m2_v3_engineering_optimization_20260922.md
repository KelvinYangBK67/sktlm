# S1M2 V3 frozen engineering optimization sweep

Date: 2026-09-22

Status: **COMPLETE**

Starting HEAD: `ee3586ddb987a71ac5c899faf140ab6cc155d2fa`

Branch: `exp/s1m2-reusable-pieces`

## Scope and frozen contract

This sweep changes execution and allocation only. The authoritative scientific
contract remains
`reports/core_methods/reusable_pieces/s1m2_v3_scientific_freeze_20260922.md`,
with its machine attestation at
`reports/core_methods/reusable_pieces/evidence/s1m2_v3_scientific_freeze_20260922.json`.

The frozen identity remains `reusable_pieces_v3`, three passes, exact composed
marginal inference, gamma 1.0, rho 0.4, script-neutral `PhonologicalForm` piece
identity, one latent script-neutral phonological wordform host, support pooled
by `(piece, host)` before Q, `R_cross=C-Q/C` for `C>0` and zero for `C=0`,
diagnostic-only M, and structural/diagnostic-only PieceRole.

`configs/production/s1m2_six_cell_v3.json` was not modified. Its frozen file
SHA-256 remains
`6a29480ba27d82ed334cdc6027f2aedab30e6fc7b3f5ebe2465ff6469b3022fa`.

## Completed engineering checklist

1. **Role-neutral production piece-score cache.**
   `NeutralPieceScorer`, `ExpectedCountPieceScorer`, and
   `BaseMeasurePieceScorer` in `src/sktlm/pieces/scorer.py`,
   `PieceStoreScorer` in `src/sktlm/latent/store.py`, and
   `ComposedPieceInference._score_piece_symbols()` in
   `src/sktlm/pieces/composed.py` use an explicit scorer capability. Frozen
   role-neutral scorers cache by phoneme tuple, while generic role-sensitive
   scorers retain `(phonemes, role)` keys.
   This removes role-only duplicate entries without enlarging a cache or
   changing generic scorer behavior.

2. **Segment object lifetime.**
   Segment iterators and the `_write_*`, `_coalesce_*`, `_apply_*`,
   `_training_pass()`, and `_inspection_pass()` loops in
   `src/sktlm/latent/training.py` release graphs, profiles, statistics,
   topologies, inference results, serialized rows, decoded records, and segment
   objects at their last use. This shortens overlap between consecutive large
   segment objects without adding collection work or retained state.

3. **Token-internal grammar-match reuse.**
   `_token_internal_nodes()` and `_internal_nodes()` in
   `src/sktlm/latent/candidates.py` derive and sort immutable internal nodes
   once per token; `build_candidate_graph()` and `build_lazy_candidate_graph()`
   reuse them for every compatible incoming/outgoing window. Window filtering,
   ordering, overflow accounting, source positions, rule IDs, and transformed
   flags remain unchanged. This removes repeated grammar traversal and
   equivalent node construction.

4. **Posterior-map copy removal.**
   `ComposedPieceInference` marginal aggregators,
   `_evaluate_lazy_token_legacy()`, `_evaluate_lazy_token_compact()`,
   `_evaluate_lazy_token_shared()`, and `infer_composed_segment()` in
   `src/sktlm/pieces/composed.py` accumulate ordinary dictionaries and return
   them directly. Update order is unchanged, while duplicate hash tables at
   return boundaries are removed.

5. **Piece-end simplification.**
   `_piece_ends()` and `build_piece_lattice()` in
   `src/sktlm/pieces/lattice.py` provide one ordered endpoint generator shared
   by the lattice and `ComposedPieceInference` paths. It yields the bounded
   contiguous range and then the distinct legal long whole-form endpoint,
   eliminating set construction, hashing, sorting, and tuple materialization.

6. **SQLite row materialization.**
   `LexiconStore.add_document_piece_counts()`,
   `add_document_piece_host_support()`,
   `add_document_piece_host_role_support()`, and
   `add_document_lexical_diagnostics()` in `src/sktlm/latent/store.py` stream
   rows into `executemany`. The pooled/role host-support path retains one
   reusable source collection and uses generators for both inserts. Row order,
   transactions, document atomicity, and separate role diagnostics remain
   unchanged, while simultaneous duplicate row lists are removed.

7. **Execution-bundle plan streaming.**
   `_update_digest_from_file()`, `_text_sha256()`, and
   `load_execution_bundle_plan()` in
   `src/sktlm/latent/execution_bundles.py` iterate bundle JSONL records and hash
   materialized plan files in fixed-size chunks. Text hashing preserves
   universal-newline canonicalization and the materialization digest retains
   the same filename/NUL/content/NUL sequence. This replaces whole-file plan
   and byte-buffer materialization.

8. **Slice and singleton-tuple allocation.**
   `_phonemes_between()`, `_contains_avagraha_between()`, lazy `span()` and
   `_count_legal_spans()`, compact support compilation, and
   `_compact_boundary()` across `src/sktlm/latent/candidates.py`,
   `src/sktlm/latent/lazy_candidates.py`, and
   `src/sktlm/pieces/composed.py` use integer ranges; compact trie extension has
   a single-symbol helper. This removes temporary slices and singleton tuples
   from nested loops without changing traversal.

9. **Scorer constant precomputation.**
   `GeometricPhonemeBaseMeasure.log_probability_for_length()` in
   `src/sktlm/pieces/scorer.py` uses three scorer-lifetime logarithmic
   constants; `PieceStoreScorer.score_from_count_and_length()` uses that
   method; and `ComposedPieceInference` stores rho logarithms once per engine.
   Only configuration constants are retained, removing repeated fixed
   logarithms.

10. **Training factor top paths.**
    `infer_composed_segment()` in `src/sktlm/pieces/composed.py` creates and
    appends `factor_top_paths` only when inspection Top-K is enabled. Training
    keeps no presentation-only list, while inspection decoding is unchanged.

11. **Count-only set removal.**
    `build_candidate_graph()` and `build_lazy_candidate_graph()` use per-token
    flags and scalar counts for overflow/pressure. Monotonic training,
    coalescing, application, and inspection loops in
    `src/sktlm/latent/training.py` count line transitions using the prior line
    number. Sets required for genuine nonmonotonic deduplication remain.

12. **JSONL record lifetime.**
    `_coalesce_training_bundle_shards()`,
    `_apply_compact_training_bundle_shards()`,
    `_coalesce_inspection_bundle_shards()`, and `_apply_inspection_shard()` in
    `src/sktlm/latent/training.py` release each decoded record after ordered
    consumption; bundle workers similarly release serialized records and their
    large source structures. This prevents the previous decoded record from
    overlapping the next parse.

13. **Single-pass candidate statistics.**
    `candidate_graph_statistics()` and `lazy_candidate_graph_statistics()` in
    `src/sktlm/latent/candidates.py` and
    `src/sktlm/latent/lazy_candidates.py` accumulate all factor and lattice
    fields in one deterministic traversal. No intermediate lattice list is
    retained, and `defer_legal_span_count` remains honored.

14. **ASCII stable-key length.**
    `_estimated_form_bytes()` and compact/shared top-segmentation cache-size
    calculations in `src/sktlm/pieces/composed.py` count stable
    `PhonologicalForm.key` characters directly. These keys contain only ASCII
    `Phoneme.value` identifiers and dots, so the value is identical without a
    temporary UTF-8 byte string.

## Static preservation review

The complete diff was reviewed for candidate-universe changes, scientific
accumulation reordering, host/piece identity changes, role-specific learned
state, increased cache or inflight limits, unbounded state, production-contract
changes, and unrelated edits. The changes remove duplicate work or state,
shorten object lifetimes, stream existing input, precompute scalar constants,
and remove redundant traversal or temporary allocation. They make no empirical
performance claim.

Only static hygiene and review commands were used, including `git diff`,
`git diff --check`, `git status`, and the production-contract file hash. No
project code or workload was executed.

```text
NO PERFORMANCE TEST OR BENCHMARK WAS RUN
NO SCIENTIFIC EXPERIMENT WAS RUN
NO VM/CLOUD/FULL-M0 JOB WAS RUN
```

## Next scientific gate

```text
NEXT_SCIENTIFIC_GATE = researcher-authorized frozen-V3 Full M0 confirmatory production evaluation
```

The gate is recorded only. Do not launch VM, cloud, or Full M0 automatically.

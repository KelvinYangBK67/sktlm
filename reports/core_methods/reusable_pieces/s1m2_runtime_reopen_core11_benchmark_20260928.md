# S1M2 V3 Full M0 runtime/RSS engineering reopen and Core-11 benchmark handoff

Date: 2026-09-28

## Status and scope

This engineering reopen starts from production-deployment commit
`5ec5d5c33a59abe06fadc9bde84f48b380b7fe39` and prepares the candidate at
`464e4dc4050e15bd9a233ae04f543211e7798ac7` on
`exp/s1m2-runtime-reopen`.

The candidate is ready for a researcher-operated before/after benchmark on
Core-11. It has **not** passed a production-scale performance gate, and this
report makes no claim that Full M0 is runtime-viable. No VM, SSH, cloud,
Core-07 through Core-10, representative/stress workload, Full M0 training, or
benchmark expected to exceed five minutes was run during this work.

Frozen scientific semantics remain:

- model `reusable_pieces_v3` and three configured passes;
- exact composed marginal inference;
- `gamma = 1.0`, `rho = 0.4`, and maximum piece length 8;
- support epsilon 0.0 and the unchanged support threshold;
- script-neutral phonological pieces and one latent script-neutral
  phonological wordform host;
- support pooled by `(piece, host)` and the V3 cross-host reuse objective;
- unchanged candidate, grammar, boundary, role, checkpoint, and pass
  semantics.

There is no pruning, beam search, sampling, candidate truncation,
`max_internal_matches` truncation, threshold tuning, probability change, host
change, or role change in the candidate.

The first Core-11 smoke against the earlier `4f8e097` candidate confirmed the
RSS improvement (about 1.54 GiB baseline main-process RSS versus about
287 MiB) but exposed a serialized reducer and roughly 61 GiB of transient
storage in both runs. All 39 completed bundle sidecars remained present while
the parent was still reducing. The later commits in this report are the
Round 3B/3C engineering response to that measured evidence; no new performance
claim is made until the researcher reruns the protocol below.

## Confirmed scaling mechanisms

Static audit of the production path confirmed the following mechanisms rather
than inferring them only from the slow Full runs:

1. The compact reverse pass retained
   `dict[node, dict[endpoint, float]]` across all active endpoints. A large
   continuous token could therefore make host-specific adjoint memory scale
   with live nodes times endpoint/host count.
2. A training worker first materialized all piece-host support in Python,
   converted every float to text, embedded the result in one JSON segment
   record, and the parent parsed and reconstructed the same key objects and
   counters.
3. The compact document scheduler waited for every bundle future before
   beginning canonical reduction. This prevented the already expensive
   reducer/SQLite phase from overlapping later worker computation. Historical
   Round2 measurements had already attributed about 2015/3159 seconds and
   3662/4797 seconds to reducer stall in the representative and stress cases.
4. `LexiconStore.add_document_piece_host_support()` materialized its full
   source iterable as a list even when role diagnostics were disabled.
5. The internal-match cache bounded entry count but retained complete match
   tuples for oversized continuous tokens; entry count was not a useful bound
   on token units or retained matches.
6. Pass 1 used `NeutralPieceScorer`, but the exact compact path still built
   learned-score/cache state whose value was identically zero.
7. The metrics wrapper recursively scanned the growing run tree every second,
   creating avoidable observer I/O while omitting physical-memory pressure and
   main-versus-worker detail.

## Candidate engineering changes

### Bounded observability and storage

- `src/sktlm/latent/store.py`,
  `LexiconStore.add_document_piece_host_support()`: when role diagnostics are
  off, rows now flow directly into bounded `executemany()` batches without a
  whole-document `source_rows` list. The role-diagnostic path retains its
  required reusable materialization.
- `src/sktlm/latent/grammar.py`, `StructuredSandhiGrammar`: the exact internal
  match cache is now bounded simultaneously by 100,000 entries, 1,000,000
  cached token units, and 1,000,000 cached matches. Tokens over 256 units and
  results over 4096 matches bypass long-lived retention. Exact computation is
  still performed once for that request. Telemetry reports hits, misses,
  current/peak retained units and matches, bypasses, and evictions.
- `src/sktlm/latent/training.py`, `_record_grammar_cache_telemetry()`: worker
  cache telemetry is merged into the normal runtime payload.
- `scripts/cloud/run_with_metrics.py`: process and host-memory sampling remains
  one second; filesystem usage defaults to five seconds; full run-tree scans
  default to thirty seconds. Samples now separate main RSS, worker RSS sum,
  maximum single-worker RSS, `MemAvailable`, swap, bundle markers, and training
  shard/host-support bytes. The summary records the peak process breakdown and
  explicitly warns that summed process RSS can double-count shared pages.
- `scripts/cloud/run_monitor.py`: the live table displays main RSS, maximum
  worker RSS, available memory, and swap.

### Exact neutral Pass-1 path

- `src/sktlm/pieces/scorer.py`, `NeutralPieceScorer`: exposes the exact
  invariant that every learned piece score is zero.
- `src/sktlm/pieces/composed.py`, `ComposedPieceInference`: neutral Pass 1
  reuses prior-only DP quantities by host length, avoids scorer calls and
  learned-score cache state, and removes redundant zero additions in compact
  and shared exact routes. Outer lexical/sandhi inference, whole-form edges,
  normalization, posterior marginals, and support emission remain exact.
- Runtime counters `neutral_prior_fast_path_forms`,
  `neutral_prior_fast_path_nodes`, and
  `neutral_prior_fast_path_transitions` make activation observable.

### Bounded host-specific reverse adjoints

- `src/sktlm/pieces/composed.py`, compact and shared marginal aggregation:
  host endpoints are processed in deterministic batches of 128. Global piece
  counts and expected score retain their original pass; host-specific reverse
  adjoints are released after each endpoint batch. Endpoint order and all
  exact transition calculations are retained.
- The batch size is an engineering cache bound in `ComposedCacheConfig`, not a
  scientific parameter.
- `host_adjoint_batches`, `host_adjoint_endpoints`, and
  `host_adjoint_peak_entries` expose the effective working set.
- `src/sktlm/latent/training.py` merges counter-like values by sum and
  gauge-like cache/peak values by maximum.

### Streaming bundles and incremental canonical reduction

- `src/sktlm/latent/training.py`, `_write_training_bundle_shard()`: bundle
  schema v2/segment schema v3 stream host and optional role support rowwise to
  a sidecar `*.host-support.tsv`; JSON retains deterministic row counts and
  checksum metadata instead of one giant support array. Existing v1 bundle
  shards remain resume-readable.
- `_consume_training_segment_support()`, `_load_training_bundle_shard()`,
  `_coalesce_training_bundle_shards()`, and
  `_apply_compact_training_bundle_shards()` consume the sidecar in canonical
  segment/row order and fail closed on count/checksum disagreement.
- `_parallel_training_bundles()` starts the single document transaction when
  canonical bundle 0 is available, consumes bundle 0, 1, and so on strictly by
  bundle index while later workers continue, commits only after the complete
  document, and only then advances the durable checkpoint. Floating reduction
  was not made completion-order-dependent.
- Telemetry includes `training_bundle_host_support_rows` and
  `training_bundle_host_support_bytes`.

### Round 3B reducer and transient-storage closure

- The compact reducer now retires a consumed bundle's segment payload,
  host-support payload, and marker immediately after complete identity,
  segment-order, row-count, and checksum validation and after its values have
  entered the current open document transaction. It does not wait for the
  document commit. A crash cannot expose partial document state because the
  SQLite document checkpoint remains the only durable boundary; absent retired
  bundles are recomputed on resume. Retirement count and bytes are reported.
- Bundle scheduling now limits submitted work to actual worker count and adds
  an execution-only soft byte bound over ready and known inflight spool files.
  The host-relative default is `max(256 MiB, min(physical RAM / 8,
  workers * 512 MiB))`; the canonical next bundle can always make progress, so
  backpressure cannot deadlock reduction. Current/peak ready and inflight
  bytes, waits, and wait seconds are telemetry. The bound is excluded from the
  scientific/config signature.
- `LexiconStore` has streaming raw-key APIs for piece counts, pooled
  piece/host support, optional role support, and lexical diagnostics. The
  compact reducer no longer reconstructs `PieceIdentity` and
  `PhonologicalForm` merely to serialize the same canonical keys again.
- New bundle writers use packed binary host-support schema v3 / segment schema
  v4. Each segment has deterministic piece and host dictionaries; rows retain
  canonical order and encode dictionary IDs plus IEEE-754 binary64 bits.
  Magic, schema, segment identity, row counts, and checksum are validated
  fail-closed. Existing embedded-v1 and TSV-v2 readers remain available for
  resume compatibility. Truncation or mutation never becomes accepted state.
- Reconstructible bundle segment/support spools no longer pay a full payload
  `fsync`: they close, atomically rename, and publish the checksum marker only
  after the payload. The durable SQLite/checkpoint authority is unchanged.
  Fsync on the separate shared topology authority was deliberately retained;
  the compact production route does not write that archive.

### Round 3C exact compute closure

- Neutral Pass 1 now compiles the normalized positional edge posterior once
  per observed host length and applies it in the unchanged endpoint order to
  actual phonological identities and `(piece, host)` support. The template
  covers lengths at and above the piece bound, the distinct long-whole edge,
  and all roles. Its LRU is bounded to 4096 lengths and 16 MiB. Global piece
  counts and expected raw score retain the original aggregate reverse pass;
  only the redundant host-indexed reverse adjoint is removed in the neutral
  route. Template compile/hit/eviction/endpoint/edge counters are exposed.
- Passes 2/3 now collect unique role-neutral keys for each compact/shared
  topology batch and call `PieceStoreScorer.score_many()`. Missing keys are
  still exact zero counts, SQL `IN` requests are deterministically chunked at
  900 parameters, the bounded LRU remains in force, and the scoring equation
  is unchanged. Telemetry reports bulk calls, fetched rows, cache hits/misses,
  SQLite time, and scalar fallbacks.
- V3 finalization materializes `MAX(S)` and `SUM(S*S)` together in one
  temporary SQLite grouped result, indexes it by canonical piece key, updates
  the existing pass table, runs the unchanged validation, and computes the
  unchanged `R_cross=C-Q/C`. It does not materialize the aggregate in Python.
- The power-of-two telemetry histogram now selects its bucket in O(1) with
  integer bit length.

### Evaluated but not implemented

- Compact-topology persistence across passes was not added. The production
  compact object includes factor-local hypothesis and optional occurrence
  structures; persisting it safely needs a new minimal packed identity and
  corruption/reconstruction contract. Without a Core-11 compile-versus-I/O
  profile it could recreate the large spool pressure this round removes.
- Integer-ID or packed-BLOB SQLite keys for `piece_host_support_next` were not
  added. Maintaining canonical grouping and floating accumulation order would
  require pass-local dictionaries plus fail-closed migration/finalization
  logic. The packed sidecar removes the dominant repeated wire keys first;
  the remaining SQLite redesign is left for evidence-driven follow-up.
- `PassMetrics` was not refactored into a mutable accumulator, and grammar
  matching received no speculative rewrite.

### Changed files in the Round 3B/3C closure

Runtime and tooling changes are in
`src/sktlm/latent/{store,telemetry,training}.py`,
`src/sktlm/pieces/composed.py`,
`src/sktlm/experiments/training/latent_lexicon.py`,
`scripts/cloud/run_with_metrics.py`, and
`scripts/analysis/compare_s1m2_artifacts.py`. Focused regressions are in
the corresponding composed-inference, V3 objective, bundle-scheduler, generic
planner, and S1M2 training files under `tests/pieces/`, plus
`tests/latent/test_s1m2_artifact_comparison.py`, and
`tests/cloud/test_run_with_metrics.py`.

### Benchmark and comparison tooling

- `scripts/analysis/run_s1m2_training_benchmark.py` invokes the normal CLI
  from the checkout selected by `PYTHONPATH` and writes the returned engineering
  runtime payload outside canonical run artifacts. This provides equivalent
  capture for the baseline, whose `--next-pass-only` path did not persist that
  payload.
- `src/sktlm/latent/training.py` now persists `timing_metrics.json` on the
  candidate's normal next-pass-only exit as well.
- `scripts/analysis/compare_s1m2_artifacts.py --training-state-only` compares
  pass-boundary state, iteration metrics, and every ordered row/column of both
  SQLite `lexicon` and `piece_lexicon`. It streams rows and retains the frozen
  default tolerance `rtol=1e-10`, `atol=1e-12`. Engineering-only counters are
  excluded; scientific learned state is not.
- The canonical artifact comparator recognizes all V3 piece-inventory numeric
  columns and applies the same frozen tolerance instead of treating them as
  byte-exact text.

## Local correctness evidence

Short local validation remained well below five minutes:

- the final combined selection passed 139 tests in 45.66 seconds;
- 84 composed/training/V3 tests passed in about 15 seconds. They cover neutral
  template parity, short and long whole forms, same-length distinct identities,
  raw-key store equivalence, one-scan moments, scalar-versus-bulk scoring,
  missing-row zero semantics, and the compact aligned-score route with a
  one-entry scorer LRU and zero scalar fallbacks.
- 53 bundle scheduler, generic planner, production wiring, metrics, and
  artifact-comparator tests passed in about 14 seconds. They cover immediate
  retirement, precommit crash/recompute, byte-backpressure progress, packed
  binary64 round-trip, deterministic dictionaries/order, corruption and
  truncation rejection, legacy reader compatibility, and recovery rollback.
- 13 focused grammar-cache, comparator, metrics, and new bundle regressions
  passed in about four seconds during the change-local check.
- The V3 artifact comparator accepts bundled/serial differences only under the
  unchanged `rtol=1e-10`, `atol=1e-12` contract and still compares identities
  exactly. The earlier tiny end-to-end maximum absolute difference remains
  `1.7763568394002505e-15`.

Touched Python modules compile and `git diff --check` passes. No tolerance was
widened, and no production-size or performance workload was executed.

## Remaining high-risk bottlenecks

The candidate deliberately stops before speculative secondary work:

- canonical reducer and SQLite apply remain a serialized single-writer phase;
  overlap removes avoidable waiting but cannot remove their intrinsic cost;
- non-neutral Passes 2/3 still use bounded host-adjoint reverse batches and may
  trade RSS for recomputation wall time;
- `piece_host_support_next` still indexes canonical TEXT piece/host keys, so
  SQLite B-tree/WAL size and compare cost may remain material even though the
  wire sidecar is now packed and the parent no longer reconstructs objects;
- compact trie/topology construction and Python candidate objects may still
  dominate giant-token RSS;
- compact topology is still rebuilt instead of reused across passes;
- the byte bound is soft and permits the canonical next bundle to progress;
  one giant bundle can therefore exceed it, which is observable but necessary
  for deadlock freedom;
- worker count remains 12 for the controlled rerun. It must not be changed to
  conceal per-worker or reducer scaling before this architecture is measured.

## First-document planning sanity

A planner-only local check, lasting about 1.5 seconds and performing no
training or inference, selected the first production Devanagari continuous
document:

```text
1_veda/2_bra/gopbra_u.txt
segments=5315
phonemes=195480
pressure=10579072
bundles=39
plan_sha256=e66b0363d19ea53b8023653ba33e27367466dbeaa8b3e30eaf103c31ab7d4d81
```

Its 39 normalized bundle-geometry records exactly matched document 0 in the
tracked Full M0 Devanagari continuous v2 plan. The temporary local subset plan
and document-list file were removed; Core-11 must rematerialize them using the
commands below.

## Core-11 benchmark protocol

This benchmark is intentionally one complete production document and Pass 1
only. Do not run baseline and candidate concurrently. Use an otherwise idle
Core-11, confirm enough free disk and memory, and preserve both output trees.
Do not run these commands on Core-07 through Core-10.

The candidate commit must first exist on the Core-11 source clone. Publishing
the branch, if authorized, is separate from this handoff. After it is
available, prepare two detached worktrees and the exact shared bundle plan:

```bash
set -euo pipefail

SOURCE_REPO=/root/sktlm
BENCH_ROOT=/root/sktlm-runtime-reopen
BASE_SHA=5ec5d5c33a59abe06fadc9bde84f48b380b7fe39
CANDIDATE_SHA=464e4dc4050e15bd9a233ae04f543211e7798ac7

git -C "$SOURCE_REPO" fetch origin exp/s1m2-runtime-reopen
git -C "$SOURCE_REPO" cat-file -e "${BASE_SHA}^{commit}"
git -C "$SOURCE_REPO" cat-file -e "${CANDIDATE_SHA}^{commit}"

mkdir -p "$BENCH_ROOT"
git -C "$SOURCE_REPO" worktree add --detach "$BENCH_ROOT/baseline" "$BASE_SHA"
git -C "$SOURCE_REPO" worktree add --detach "$BENCH_ROOT/candidate" "$CANDIDATE_SHA"
printf '%s\n' '1_veda/2_bra/gopbra_u.txt' > "$BENCH_ROOT/first-document.txt"

env PYTHONPATH="$BENCH_ROOT/candidate/src" python \
  "$BENCH_ROOT/candidate/scripts/analysis/plan_s1m2_execution_bundles.py" \
  --repo-root "$BENCH_ROOT/candidate" \
  --output-dir "$BENCH_ROOT/first-document-plan" \
  --cell-id s1m2_m0_devanagari_continuous \
  --manifest data/manifests/representations.csv \
  --script devanagari \
  --condition continuous \
  --document-list "$BENCH_ROOT/first-document.txt" \
  --target-pressure 279047 \
  --max-segments-per-bundle 256 \
  --max-segment-tokens 128

PLAN="$BENCH_ROOT/first-document-plan" python - <<'PY'
import json
import os
from pathlib import Path

summary = json.loads((Path(os.environ["PLAN"]) / "summary.json").read_text())
expected = {
    "actual_bundle_count": 39,
    "total_segments": 5315,
    "total_phonemes": 195480,
    "total_pressure": 10579072,
    "plan_sha256": "e66b0363d19ea53b8023653ba33e27367466dbeaa8b3e30eaf103c31ab7d4d81",
}
for key, value in expected.items():
    assert summary[key] == value, (key, summary[key], value)
print(json.dumps(expected, indent=2, sort_keys=True))
PY

uname -a > "$BENCH_ROOT/host.txt"
lscpu >> "$BENCH_ROOT/host.txt"
free -b >> "$BENCH_ROOT/host.txt"
df -B1 "$BENCH_ROOT" >> "$BENCH_ROOT/host.txt"
python --version >> "$BENCH_ROOT/host.txt" 2>&1
```

Set the common paths once:

```bash
METRICS_WRAPPER="$BENCH_ROOT/candidate/scripts/cloud/run_with_metrics.py"
HARNESS="$BENCH_ROOT/candidate/scripts/analysis/run_s1m2_training_benchmark.py"
PLAN="$BENCH_ROOT/first-document-plan"
DOCS="$BENCH_ROOT/first-document.txt"
```

### Baseline command

Run once from the detached baseline worktree. The output paths must not already
contain a run with the same ID.

```bash
cd "$BENCH_ROOT/baseline"
env \
  PYTHONHASHSEED=0 \
  OMP_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 \
  PYTHONPATH="$BENCH_ROOT/baseline/src" \
  python "$METRICS_WRAPPER" \
  --output-dir "$BENCH_ROOT/metrics-baseline" \
  --watch-dir "$BENCH_ROOT/runs-baseline/s1m2_runtime_baseline_pass1" \
  --interval 1 \
  --filesystem-interval 5 \
  --storage-interval 30 \
  -- \
  python "$HARNESS" \
  --runtime-output "$BENCH_ROOT/metrics-baseline/training_runtime.json" \
  -- \
  --manifest data/manifests/representations.csv \
  --document-list "$DOCS" \
  --output-root "$BENCH_ROOT/runs-baseline" \
  --run-id s1m2_runtime_baseline_pass1 \
  --model reusable_pieces_v3 \
  --script devanagari \
  --condition continuous \
  --passes 3 \
  --workers 12 \
  --execution-bundle-plan "$PLAN" \
  --lexical-alpha 0.1 \
  --complexity-weight 0.5 \
  --complexity-tau 1.0 \
  --whitespace-merge-penalty 8.0 \
  --sandhi-transformation-penalty 1.0 \
  --no-whitespace-merge \
  --max-internal-matches 512 \
  --max-segment-tokens 128 \
  --lexicon-cache-size 100000 \
  --flush-types 50000 \
  --analysis-top-k 8 \
  --usage-posterior-threshold 0.01 \
  --high-confidence-threshold 0.8 \
  --low-count-threshold 1.0 \
  --seed 0 \
  --piece-max-length 8 \
  --piece-boundary-probability 0.4 \
  --piece-alpha 0.1 \
  --piece-complexity-weight 0.5 \
  --piece-complexity-kappa 1.0 \
  --piece-complexity-beta 0.25 \
  --piece-complexity-tau 1.0 \
  --piece-base-stop-probability 0.5 \
  --piece-min-reuse-host-types 2 \
  --piece-host-support-threshold 1.0 \
  --piece-support-epsilon 0.0 \
  --piece-score-cache-entries 65536 \
  --piece-score-cache-bytes 33554432 \
  --piece-form-cache-entries 8192 \
  --piece-form-cache-bytes 268435456 \
  --piece-shared-prefix-nodes 262144 \
  --piece-shared-top-k-piece-references 4194304 \
  --next-pass-only
```

### Candidate command

Run only after the baseline command exits and host pressure has returned to its
idle state.

```bash
cd "$BENCH_ROOT/candidate"
env \
  PYTHONHASHSEED=0 \
  OMP_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 \
  PYTHONPATH="$BENCH_ROOT/candidate/src" \
  python "$METRICS_WRAPPER" \
  --output-dir "$BENCH_ROOT/metrics-candidate" \
  --watch-dir "$BENCH_ROOT/runs-candidate/s1m2_runtime_candidate_pass1" \
  --interval 1 \
  --filesystem-interval 5 \
  --storage-interval 30 \
  -- \
  python "$HARNESS" \
  --runtime-output "$BENCH_ROOT/metrics-candidate/training_runtime.json" \
  -- \
  --manifest data/manifests/representations.csv \
  --document-list "$DOCS" \
  --output-root "$BENCH_ROOT/runs-candidate" \
  --run-id s1m2_runtime_candidate_pass1 \
  --model reusable_pieces_v3 \
  --script devanagari \
  --condition continuous \
  --passes 3 \
  --workers 12 \
  --execution-bundle-plan "$PLAN" \
  --training-bundle-ready-bytes 4294967296 \
  --lexical-alpha 0.1 \
  --complexity-weight 0.5 \
  --complexity-tau 1.0 \
  --whitespace-merge-penalty 8.0 \
  --sandhi-transformation-penalty 1.0 \
  --no-whitespace-merge \
  --max-internal-matches 512 \
  --max-segment-tokens 128 \
  --lexicon-cache-size 100000 \
  --flush-types 50000 \
  --analysis-top-k 8 \
  --usage-posterior-threshold 0.01 \
  --high-confidence-threshold 0.8 \
  --low-count-threshold 1.0 \
  --seed 0 \
  --piece-max-length 8 \
  --piece-boundary-probability 0.4 \
  --piece-alpha 0.1 \
  --piece-complexity-weight 0.5 \
  --piece-complexity-kappa 1.0 \
  --piece-complexity-beta 0.25 \
  --piece-complexity-tau 1.0 \
  --piece-base-stop-probability 0.5 \
  --piece-min-reuse-host-types 2 \
  --piece-host-support-threshold 1.0 \
  --piece-support-epsilon 0.0 \
  --piece-score-cache-entries 65536 \
  --piece-score-cache-bytes 33554432 \
  --piece-form-cache-entries 8192 \
  --piece-form-cache-bytes 268435456 \
  --piece-shared-prefix-nodes 262144 \
  --piece-shared-top-k-piece-references 4194304 \
  --next-pass-only
```

Role diagnostics are intentionally absent from both commands. Shared token
marginals remain enabled by default in both. The candidate's explicit 4 GiB
spool bound is the deterministic value of its host-relative default on a
32 GiB, W12 machine; it is execution-only. The historical baseline does not
have that CLI option.

### Exact scientific comparator command

Run this before interpreting any performance result. A nonzero exit or any
status other than `PASS` rejects the candidate; do not widen tolerances.

```bash
cd "$BENCH_ROOT/candidate"
env PYTHONPATH="$BENCH_ROOT/candidate/src" python \
  "$BENCH_ROOT/candidate/scripts/analysis/compare_s1m2_artifacts.py" \
  "$BENCH_ROOT/runs-baseline/s1m2_runtime_baseline_pass1" \
  "$BENCH_ROOT/runs-candidate/s1m2_runtime_candidate_pass1" \
  --training-state-only \
  --expected-completed-passes 1 \
  > "$BENCH_ROOT/training-state-comparison.json"

python -m json.tool "$BENCH_ROOT/training-state-comparison.json"
```

The comparator must report both `lexicon_rows` and `piece_lexicon_rows`, plus
the maximum absolute/relative differences under the frozen tolerance.

## Telemetry to inspect

Compare `metrics-baseline/summary.json` with
`metrics-candidate/summary.json`:

- `wall_seconds`, return code, sampled CPU seconds/capacity, read/write bytes,
  and I/O-wait seconds;
- `peak_main_process_rss_bytes`, `peak_worker_rss_bytes`, and
  `peak_process_tree_rss_bytes`;
- `minimum_mem_available_bytes`, `peak_swap_used_bytes`, peak process count,
  and `peak_sample_process_breakdown`;
- peak SQLite/WAL, topology, training shard, host-support shard, and watched
  run bytes.

Treat process-tree RSS as a simultaneous accounting signal, not unique
physical pages. Use `MemAvailable` and swap as the independent host-pressure
signals.

Inspect `samples.csv` for phase shape and concurrency:

- process count, main RSS, summed worker RSS, maximum single-worker RSS;
- CPU capacity, `MemAvailable`, swap, and load;
- `training_bundle_marker_count`, `training_shard_bytes`, and
  `training_host_support_shard_bytes` to locate worker completion and reducer
  overlap.

Compare both `training_runtime.json` files. The candidate adds or sharpens:

- `grammar_cache.internal_matches` and
  `training_grammar_cache_{hits,misses,evictions,long_token_bypasses,large_match_bypasses}`;
- `training_grammar_cache_{currsize,cached_token_units,cached_match_count,peak_entries,peak_cached_token_units,peak_cached_match_count}`;
- `training_neutral_prior_fast_path_{forms,nodes,transitions}`;
- `training_neutral_host_template_{compiles,cache_hits,cache_evictions,endpoints,edges}`;
- `training_piece_store_bulk_calls`,
  `training_piece_store_bulk_rows_fetched`, and
  `training_piece_store_scalar_fallbacks`;
- `training_host_adjoint_batches`, `training_host_adjoint_endpoints`, and the
  `training_host_adjoint_peak_entries` gauge;
- existing candidate/internal-match and compact prefix node/transition
  counters/histograms;
- `training_reducer_stall`;
- `sqlite_piece_count_upsert`, `sqlite_piece_count_upsert_rows`,
  `sqlite_piece_host_support_upsert`,
  `sqlite_piece_host_support_upsert_rows`, and `sqlite_document_commit`;
- `training_bundle_host_support_rows` and
  `training_bundle_host_support_bytes`;
- `training_bundle_ready_shard_bytes_{current,peak}`,
  `training_bundle_inflight_shard_bytes_{current,peak}`,
  `training_bundle_backpressure_waits`,
  `training_bundle_backpressure_wait_seconds`, and exact retired shard
  count/bytes.

The decisive evidence is: comparator PASS first, then wall time, maximum
single-worker/main RSS, host `MemAvailable`/swap, reducer stall, and the bundle
timeline. No automatic performance PASS threshold is asserted here.

## Commit sequence

```text
5ec5d5c33a59abe06fadc9bde84f48b380b7fe39 baseline
f22502c perf: bound S1M2 runtime telemetry state
ba07b73 perf: add exact neutral pass fast path
16cf561 perf: bound host adjoint working state
fa2b690 perf: stream bundle host support reduction
83cbd3d feat: prepare Pass 1 runtime comparison telemetry
58233d9 feat: add runtime benchmark capture harness
4f8e097 test: compare complete Pass 1 learned state
7dc3495 perf: stream raw reducer keys and host moments
4961efd perf: bound and pack training bundle spools
ac0224b perf: bulk reusable-piece score lookups
b0780a3 perf: reuse exact neutral host templates
2b2c99f test: compare bundled V3 outputs at frozen tolerance
464e4dc perf: align compact batch piece scores
```

## Deliberately unexecuted work

The Core-11 commands above, representative and stress workloads, worker
calibration at 12/8/6, repeated trials, Passes 2/3, all 240 documents, Full M0,
cloud/VM actions, and interaction with Core-07 through Core-10 were deliberately
not executed because they can exceed five minutes or affect live production.
They require explicit researcher operation and review of the first-document
result.

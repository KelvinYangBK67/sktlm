# S1M2 V3 Full M0 runtime/RSS engineering reopen and Core-11 benchmark handoff

Date: 2026-09-28

## Status and scope

This engineering reopen starts from production-deployment commit
`5ec5d5c33a59abe06fadc9bde84f48b380b7fe39` and prepares the candidate at
`4f8e09707ab283a0a796d89d882e4b45c6621762` on
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

## Local correctness evidence

The final focused selection passed 38 tests in 3.43 seconds. It covers the
bounded grammar cache, streaming SQLite host support, V3 objective invariants,
neutral fast-path parity with the prior exact zero-score route, batch-size-one
versus wide host-adjoint marginals/support, counter/gauge merging, restartable
next-pass-only state, row-streamed bundle support, reducer/worker overlap,
metrics sampling, and the Pass-1 learned-state comparator.

Additional change-local checks during implementation passed:

- 27 cache/store/metrics tests in 0.78 seconds;
- 5 neutral fast-path tests;
- 6 host-adjoint batching tests;
- 3 bundle streaming/overlap tests;
- an end-to-end tiny bundled-versus-legacy training comparison with identical
  146 learned keys and maximum absolute numeric difference
  `1.7763568394002505e-15`;
- a two-run Pass-1 fixture accepted by the frozen comparator with the same
  maximum absolute difference.

Touched Python modules compile and `git diff --check` passes. A broad legacy
test invocation was not represented as green: the complete bundle scheduler
file still has 7 passes and 15 failures from stale pre-existing shard-schema
and byte-exact inspection expectations, and a broad composed/reference set has
42 passes and 10 failures from stale `_raw_prior_score` and role-aware fixture
assumptions. The new focused regressions pass; these unrelated stale tests were
not rewritten to manufacture a green matrix.

## Remaining high-risk bottlenecks

The candidate deliberately stops before speculative secondary work:

- canonical reducer and SQLite apply remain a serialized single-writer phase;
  overlap removes avoidable waiting but cannot remove their intrinsic cost;
- host-adjoint batching bounds retained endpoint state but performs bounded
  reverse recomputation and may trade RSS for wall time;
- the host-support sidecar still uses lossless hexadecimal text and reconstructs
  scientific key objects in the parent; an ordered binary/SQLite shard may
  offer further gains but was not justified without the Core-11 profile;
- compact trie/topology construction and Python candidate objects may still
  dominate giant-token RSS;
- Passes 2/3 still use scalar score lookups/caches rather than a proven bulk
  fetch path;
- worker count/inflight calibration remains unchanged at 12. It must not be
  used to conceal per-worker or reducer scaling before the architecture is
  measured.

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
CANDIDATE_SHA=4f8e09707ab283a0a796d89d882e4b45c6621762

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
marginals remain enabled by default in both.

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
- `training_host_adjoint_batches`, `training_host_adjoint_endpoints`, and the
  `training_host_adjoint_peak_entries` gauge;
- existing candidate/internal-match and compact prefix node/transition
  counters/histograms;
- `training_reducer_stall`;
- `sqlite_piece_count_upsert`, `sqlite_piece_count_upsert_rows`,
  `sqlite_piece_host_support_upsert`,
  `sqlite_piece_host_support_upsert_rows`, and `sqlite_document_commit`;
- `training_bundle_host_support_rows` and
  `training_bundle_host_support_bytes`.

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
```

## Deliberately unexecuted work

The Core-11 commands above, representative and stress workloads, worker
calibration at 12/8/6, repeated trials, Passes 2/3, all 240 documents, Full M0,
cloud/VM actions, and interaction with Core-07 through Core-10 were deliberately
not executed because they can exceed five minutes or affect live production.
They require explicit researcher operation and review of the first-document
result.

# Continuous-condition performance: static source analysis and future profiling plan

Status: **source-only plan; no active cloud metric or partial scientific result
was inspected**.

This note records candidate bottleneck mechanisms visible in the current source
and separates implementation-equivalent work from changes to the scientific
hypothesis space. It does not modify runtime code, candidate bounds, or the
configuration of any running representation-gate job.

## Current execution path

The continuous representation removes lexical whitespace within a line while
preserving line breaks and punctuation/daṇḍa delimiters
(`representations/spacing.py`). `iter_observed_segments` parses a complete line,
uses punctuation as an inference delimiter, and shards only by observed-token
count. Without spaces, a long punctuation-free span can therefore remain one
large `ObservedToken`; `max_segment_tokens` does not subdivide that token by
phoneme count.

For each segment, `build_candidate_graph` constructs visible-boundary options,
then every compatible incoming/outgoing factor. `_internal_nodes` asks the
structured grammar for all whole-token internal matches, filters them for the
factor's consumed prefix/suffix, and, while within the frozen bound, constructs
lexical edges for ordered node pairs. With many internal boundary nodes this
edge construction is quadratic in node count. If the existing
`max_internal_matches` bound is exceeded, the current frozen fallback removes
those internal matches and retains the legal fallback path; this is scientific
candidate-support behavior, not a tuning knob for this note.

`StructuredSandhiGrammar` already indexes surface patterns with a trie and
caches whole-token internal-match tuples in a 100,000-entry LRU. The token key
is reused, but each factor can still refilter the cached tuple and rebuild its
nodes/lattice. Visible-boundary matching is bucketed by the adjacent surface
keys and runs once per observed boundary during graph construction.

Exact token inference builds outgoing/incoming adjacency, scores each distinct
form once per segment through `_MemoizedFormScorer`, performs forward/backward
DP, then (inspection only) repeatedly extends and trims bounded top-k paths at
lattice nodes and outer states. Training correctly skips inspection-only top-k,
boundary, rule, and entropy work. Inspection additionally constructs expected
counts/rule usage/boundary marginals, top analyses, JSONL rows, bounded report
heaps, surface/context usage, and final TSV/Markdown exports.

Document multiprocessing uses a bounded rolling window of `2 * workers`.
Workers read the lexicon and write checksummed per-document shards; the master
reduces documents in canonical order and commits checkpoint/count state.
Correctness and crash reuse require that order. A slow early document can
therefore block canonical reduction even while later shards finish. SQLite
stores compact `form_key` count tables, batches upserts, and provides bounded
lexical-score LRU caches. Inspection surface/context association tables and
large deterministic JSONL/TSV serialization remain separate costs. Existing
telemetry distinguishes candidate generation, inference, count aggregation,
frontend I/O, serialization, SQLite row/upsert/commit activity, worker CPU,
score calls, and grammar-cache statistics, but does not yet expose graph-size
percentiles or time by candidate subphase.

## Likely semantics-preserving candidates

These are future experiments only. Every candidate still requires focused
invariants and byte/numeric scientific equivalence before acceptance.

1. **Token/factor structural reuse.** Cache immutable internal-node templates
   and compatible edge skeletons by `(surface-unit key, consumed prefix,
   consumed suffix)` so factor construction does not repeatedly filter and
   allocate equivalent objects. Preserve exact rule IDs, node/edge order,
   overflow behavior, and fallback.
2. **Indexed match windows.** Store cached internal matches in start/end indexed
   immutable arrays so prefix/suffix window filtering avoids scanning every
   match for every factor. This changes access, not membership.
3. **DAG structural interning.** Intern identical `PhonologicalForm`, boundary,
   and adjacency tuples within a segment/document and reuse immutable lattice
   structures across compatible factors. Preserve stable sorting and serialized
   identities.
4. **Top-k allocation reduction.** Keep the exact same bounded ordering while
   reducing tuple concatenation, repeated sort-key construction, and temporary
   `TokenPath` churn. Any heap/merge replacement must reproduce current ties
   exactly; a prior generic heap variant showed no reproducible benefit and
   should not be resurrected without a measured mechanism.
5. **Forward/backward adjacency reuse.** Build outer factor adjacency once and
   share it among forward, backward, identity-only, and top-path passes rather
   than rebuilding `by_start` mappings. Preserve iteration order.
6. **Inspection-only fused accumulation.** Fuse read-only walks over factor/edge
   posteriors where it avoids repeated Python traversal, while keeping exact
   marginal equations, rule-sharing division, boundary identities, and
   deterministic accumulation order.
7. **Serialization buffering.** Reuse JSON payload encoders/buffers, batch small
   writes, and avoid recreating presentation-only structures. Scientific JSONL
   bytes must remain deterministic unless a separately versioned equivalent
   artifact format is explicitly adopted.
8. **SQLite batching/data layout.** Measure larger equivalent count/usage
   batches, prepared access patterns, and compact association representation.
   Preserve document-transaction/checkpoint coupling and crash-safe resume.
9. **Deterministic scheduling.** Instrument canonical-reducer stalls and bounded
   queue occupancy, then evaluate schedule changes that keep the same maximum
   pending-state bound and canonical reduction. Do not infer cloud tuning from
   active partial runs.
10. **Phase-specific immutable caches.** Size or partition caches from future
    completed profiling data, with bounded memory and explicit hit/miss/eviction
    counters. Avoid caching objects whose identity contains mutable scorer or
    checkpoint state.

## Scientific-semantic changes, not ordinary optimization

The following alter the model, evidence, exactness, or candidate hypothesis
space and must be proposed as new scientific conditions if ever pursued:

- pruning any currently legal candidate or changing candidate ordering when it
  affects bounded support;
- changing `max_internal_matches`, its overflow fallback, or any other
  candidate limit;
- changing visible-whitespace, avagraha, punctuation, or continuous frontend
  semantics;
- changing the 1,218-rule grammar, forward reconstruction, boundary licensing,
  or rule competition;
- replacing exact forward/backward with beam search, approximate posterior,
  sampling, or early hard decoding;
- changing lexical scores, smoothing, complexity prior/penalty, initialization,
  or expected-count equations;
- changing representation identity or conflating script-specific phonological
  symbols;
- discarding ambiguity, merging currently distinct paths/types, or otherwise
  changing the candidate hypothesis space.

Calling any of these “performance work” would hide a scientific intervention.

## Future post-freeze profiling counters

After the unrestricted gate is complete, audited, analysed, and S1M1 is frozen,
add low-overhead counters before choosing an implementation experiment. Record
at least:

- time per document and per segment by phase;
- observed tokens and phonemes per segment/token;
- internal raw match count, retained match count, and overflow incidence;
- visible boundary option count and incoming/outgoing factor combinations;
- factors, nodes, and edges per segment, with maximum and fixed percentiles;
- grammar-match, match-window filtering, node creation, edge creation, and
  overall graph-build time;
- token forward/backward, outer forward/backward, identity-only DP, top-k path,
  and posterior-accumulation time;
- expected-count, rule-usage, boundary, surface/context aggregation time;
- lexical score calls, segment memo hits, LRU hits/misses/evictions, SQLite
  selects, and SQLite select time;
- count serialization/upsert, transaction commit, checkpoint, and SQLite flush
  time;
- JSONL, TSV, report, and final-replacement serialization time/bytes;
- worker CPU, queue occupancy, completed-but-blocked shards, canonical reducer
  stall time, and worker utilization;
- simultaneous process-tree memory by phase and bounded pending-shard bytes.

Counters must be deterministic or explicitly engineering-only and must not feed
back into posterior/scoring decisions. Profile a completed frozen local
reference with one preregistered short workload before any long measurement.
Do not use the currently running VM jobs or their partial numbers to select an
optimization.
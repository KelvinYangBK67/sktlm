# S1M2 Execution Bundle Scheduler — 2026-09-09

## Audit conclusion

The pre-full audit passed. Planner enumeration can use the trainer's existing
`_iter_document_segments` directly, so frontend semantics are unchanged. Each
existing `ObservedSegment` remains atomic: bundle boundaries never split a
segment or cross a document.

The selected full M0 / Devanagari / continuous plan remains
`candidate_008192`:

- bundles: 8,479
- plan SHA-256: `7acf4b292adffe35dcdbdf3755c18d699b5659bb806ad2c7342a03db5d4279c9`
- scan signature: `73ea0638684ba1fa249fa9c802837c26f334b4efa0657efb18ad3f2bcc5e252e`
- target pressure: 279,047
- maximum segments per bundle: 256

The pressure proxy is the sum of squared segment phoneme counts for static
load balancing only; it is not a claim that inference has O(n²) complexity.

## Scheduler architecture

The plan is an explicit S1M2 execution-only input. It is validated against its
schema, planner identity, manifest and planner-config hashes, representation
and segment-sequence identities, materialized files, document order, and exact
contiguous bundle coverage. A stale or changed plan fails closed. With no plan,
the legacy document scheduler remains unchanged; S1M1 is not opted in.

Bundle workers process the plan's complete segment ranges with the existing
candidate, topology, and inference implementations. True inflight futures and
ready results are separate states. As soon as any future completes it leaves
inflight and the scheduler refills immediately, even when canonical reduction
is waiting for an earlier bundle.

## Canonical exactness and topology

Workers serialize each segment's float results exactly rather than pre-summing
at bundle boundaries. The parent consumes bundle records in original document
and segment order and recreates the legacy left fold and flush behavior before
calling the existing document-shard apply path. Document transactions,
`next_document_index`, checkpoint state, and scientific reduction order are
therefore unchanged by completion order.

During pass 1, bundle-local temporary topology records are coalesced in
canonical `(line_number, segment_index)` order into the original document
archive format. During later passes the document archive is validated or
reconstructed through the existing bounded cache-repair contract, then bundle
workers read their exact ranges from that pass-1 archive. No mutable score,
posterior, or expected-count state enters the topology archive.

Bundle markers retain only current-attempt resumable state. They bind plan,
config, pass, document, range, and file checksums. A resumed active pass reuses
valid completed bundles, rejects a different plan, and applies each document
only through its existing canonical transaction.

## Tiny validation

The focused test file covers:

- exact planner/trainer segment identity on multiline danda input;
- exact-once, contiguous, document-local bundle coverage with atomic segments;
- exact legacy-vs-bundle learned piece state and pass metrics;
- identical decoded topology contents and record order;
- refill beyond an intentionally delayed early future;
- partial-bundle resume and fail-closed plan replacement.

The initial targeted run reported `1 passed, 3 failed` because the new fixture
omitted an existing required loader argument. After that test-only correction,
the three affected tests reported `2 passed, 1 failed`; the remaining assertion
incorrectly compared run-specific archive headers byte-for-byte. The corrected
content/order comparison then passed (`1 passed`). Thus all four targeted gates
are passing. Syntax compilation also passed.

No representative, stress, Round1, Round2, VM, full-M0, profiling, RAM, or
runtime workload was executed. Those validations remain manual.

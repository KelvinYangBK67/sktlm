# S1M2 V3 Round 3D.1 numerical closure and Round 3E-A transient SQLite closure

Date: 2026-09-29

## Status and scope

This is a local engineering closure on `exp/s1m2-runtime-reopen`. It changes
neither the frozen V3 objective nor the authoritative
`cross_host_reusable_count()` eight-ULP rule. It does not alter candidate,
host, role, posterior, accumulation order, checkpoint, comparator tolerance,
journal, synchronous, or transaction semantics. No VM, SSH, cloud, Full M0,
representative/stress workload, or Passes 2/3 production run was performed.

Round 3D.1 closes the observed finalization failure with a suspect-row-only
persisted-support proof and failure-safe partial timing telemetry. Round 3E-A
uses the existing phonological BLOB codec for both transient piece and host
keys and raises the ordered UPSERT bind cap only after one bounded local
benchmark. External sorted runs/LSM and bundle-wire changes remain out of
scope.

## Production evidence and root cause

The Round 3D candidate completed the first Devanagari continuous document on
Core-08: 5,315 segments, 195,480 phonemes, 39 bundles, W12, Pass 1 only. The
document commit is durable at `active_pass=1`, `completed_passes=0`, and
`next_document_index=1`. Bundle shards retired to zero and peak process-tree
RSS was 9,328,275,456 bytes, below 10 GiB. Wall time was 4,037.440 seconds;
peak main RSS was 1,400,217,600 bytes, peak worker RSS was 3,453,743,104 bytes,
minimum `MemAvailable` was 23,432,577,024 bytes, and swap remained zero.

The remaining pressure moved to the single SQLite writer: peak database was
22,113,447,936 bytes, peak WAL was 22,243,068,392 bytes, watched run bytes were
44,399,742,972, and process writes were 181,185,982,464 bytes. This is a major
improvement over the stopped Core-07 baseline, which was still in document 0
after about 86 minutes with 60.08 GiB of retained shards, but it is not yet a
scientific comparator or Full M0 qualification.

Finalization stopped on:

```text
C=6.394964438799327e-09
Q=4.089557017350827e-17
```

`C` follows segment piece expected counts through bundle piece counts, the
canonical parent reducer, and ordered additions into
`piece_counts_next.expected_count`. `Q` follows segment `(piece, host)`
support through host aggregation, canonical reducer flushes, persisted
`piece_host_support_next`, and the final grouped `SUM(support * support)`.
The two paths are scientifically equivalent but have different positive-sum
parenthesizations. For the failed values, `Q-C^2` is
`2.834968878138011e-31`; `C-Q/C` is `-4.4667753077863494e-23`, or exactly
`-54 ulp(C)`, while `sqrt(Q)` is 27 ULP above C. The ordinary eight-ULP helper
therefore correctly rejected the pair. This is not evidence for widening that
helper, and persisted support still has to exclude corruption.

## Numerical-finalization repair

Ordinary SQL-valid rows take the unchanged fast path. The existing Python
helper and its eight-ULP band are byte-for-byte unchanged. Only the first SQL
suspect row takes the fallback:

1. reselect the persisted support for that exact piece, and role when
   applicable, in canonical host-key order;
2. reject nonnumeric, nonfinite, or negative support;
3. recompute C and Q independently with `math.fsum` over bounded cursors;
4. require the stored Q to equal a fresh SQLite moment of those same persisted
   rows, excluding stale or fabricated Q;
5. validate the support-derived C/Q with the authoritative helper;
6. require piece-count C versus support-derived C to fit the standard
   binary64 positive-summation forward-error envelope
   `2*gamma_n*scale/(1-gamma_n)`, plus only the existing eight-ULP floor.

`n` is taken from durable pass work measures (`characters`, candidate edges,
or lazy span traversals), never from a new scientific epsilon. Missing or
malformed work metadata falls back to the persisted support-row count. Large
C disagreement, Q disagreement, corrupt schema, negative/nonfinite values,
and `C=0,Q!=0` still fail closed. The same mechanism is wired for optional
role diagnostics. Normal rows do no support rescan and retain exact previous
values.

The local regression reproduces the supplied production-scale C/Q pair and
accepts it only after a valid persisted-support proof. This does not assert
that the actual Core-08 support rows pass: that remains the next VM resume
gate.

## Failure-safe partial timing telemetry

`timing_metrics.partial.json` is now atomically replaced after each durable
S1M2 document commit, after successful pass finalization, and on a pass-final
exception. It contains the current runtime telemetry, reducer timings,
upsert/batch/row counts, peaks, SQLite storage bytes, runtime variable limit,
journal/synchronous/schema labels, the authoritative durable SQLite
checkpoint, a lifecycle marker, and exception type/message when applicable.

The file declares `engineering_telemetry_only` and
`comparator_authority=false`. It does not change the checkpoint or any
scientific artifact. Resume replaces it with the newest snapshot. A telemetry
write failure is swallowed and counted so it cannot replace the original
training/finalization exception. Successful execution still writes the
unchanged formal `timing_metrics.json` path.

## Round 3E-A piece-key compaction and compatibility

New active passes create
`piece_host_support_next(piece_key BLOB, host_key BLOB, support REAL)` and
record `s1m2_transient_support_schema=piece_host_blob_v2`. Piece and host use
the same fixed v1 phonological codec: one version byte and one explicit byte
per phoneme. The mapping is bijective, independent of Enum position and
Python hash, prefix-preserving, and bytewise ordered exactly like canonical
dotted keys.

The reducer packs each piece once at the bundle dictionary boundary and keeps
piece/host BLOBs through its compact integer-pair accumulator and hot SQLite
flush. Bundle wire format is unchanged. At pass finalization a deterministic
SQLite scalar decodes one piece key per grouped identity into canonical TEXT;
the persistent scientific `piece_lexicon.form_key` remains canonical TEXT.
Role diagnostics also remain canonical TEXT and diagnostic-only.

Resume is explicit and fail-closed:

| Declared piece/host types | Required metadata | Status |
| --- | --- | --- |
| BLOB/BLOB | `piece_host_blob_v2` | new layout |
| TEXT/BLOB | `host_blob_v1` | Round 3D active-pass compatibility |
| TEXT/TEXT | `host_text_v1_legacy` or historically absent | older compatibility |

Unknown metadata, missing Round 3D metadata, or a metadata/type conflict is
rejected. Tests finalize all three layouts to exactly equal persistent piece
rows. No persistent scientific schema expansion was required.

## SQLite variable limit and one bounded batch benchmark

`LexiconStore` now queries
`Connection.getlimit(SQLITE_LIMIT_VARIABLE_NUMBER)` when available. Python
versions without that API retain the historical safe 900-bind fallback. The
production cap is `min(runtime_limit, 3600)`, so current three-column support
batches contain at most 1,200 rows. Runtime telemetry records the discovered
limit, source, and effective cap.

The single local benchmark used WAL + NORMAL, the default page cache, 120,000
ordered input rows, 40,000 final BLOB/BLOB rows, and three fresh databases. It
completed all cases in 0.916 seconds. The runtime bind limit was 32,766.

| support batch rows | statements | wall seconds | rows/second | observed DB+WAL+SHM max |
| ---: | ---: | ---: | ---: | ---: |
| 300 | 400 | 0.286 | 419,628 | 1,091,616 B |
| 600 | 200 | 0.275 | 437,083 | 1,091,616 B |
| 1,200 | 100 | 0.234 | 511,741 | 1,091,616 B |

All cases had identical exact row counts and support totals and passed
`quick_check`. Exact peak RSS was not sampled because no dependency-free
process-RSS source was introduced; one 3,600-value parameter tuple is tiny
relative to the established sub-10-GiB process-tree result. The 1,200-row
case was about 18% faster than 300 rows with no observed storage increase, so
the conservative cap changed. Journal, page cache, and transaction boundaries
did not.

Machine evidence:
`evidence/s1m2_round3ea_sqlite_batch_microbenchmark_20260929.json`.

## Finalization write-path audit

The current path is one grouped support scan into temporary moments, two
correlated in-place updates of `piece_counts_next`, V3 validation, one
in-place reusable-count update, and the existing rename into
`piece_lexicon`. Building the final table directly could remove updates, but
would also entangle canonical BLOB-to-TEXT conversion, suspect-row fallback,
invalid-row rollback, and Decision 119's already-qualified in-place rename
lifecycle. Without a representative finalization write profile it is not a
small exact change. It was audited and deliberately not implemented in this
round.

## Local validation and residual risk

Focused numerical/schema/bundle tests passed 73 tests in 11.17 seconds.
Adjacent phonology, V2, storage-lifecycle, S1M2 training, and generic training
tests passed 38 tests in 20.69 seconds. The final combined selection, including
the artifact comparator, passed 116 tests in 33.59 seconds. These cover production-scale values,
material corruption, NaN/inf/negative values, `C=0,Q!=0`, ordinary-row exact
behavior, role fallback, all three resume layouts, schema conflicts, codec
ordering/prefix behavior, no compact-flush piece reconstruction, partial
telemetry exception preservation, and runtime batching.

Residual risk is concentrated in the actual Core-08 support proof, real
single-writer/WAL performance, and Passes 2/3 behavior. The local batching
probe is strategy evidence, not a production-scale speedup claim. Full M0
runtime remains unqualified.

```text
ROUND3D1_STATUS=PASS
ROUND3EA_STATUS=PASS
VM_REQUIRED=YES
NEXT_VM_GATE=CORE08_RESUME_DURABLE_ROUND3D_PASS1_FINALIZATION_THEN_COMPARE_WITH_ONE_CLEAN_ROUND3EA_FIRST_DOCUMENT_RUN
```

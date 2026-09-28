# S1M2 V3 Round 3D reducer and transient-SQLite closure

Date: 2026-09-28

## Status

Round 3D code candidate is
`38557dab9bff522dfb886452b4786da04e627458` on
`exp/s1m2-runtime-reopen`. It is an engineering-only response to the measured
Core-11 reducer/storage tail. It has not been performance-qualified on
Core-11 and does not requalify Full M0. The frozen V3 scientific contract,
canonical document/bundle/segment order, floating reduction order, and
comparator tolerance are unchanged.

## Compact reducer and host identity

The production compact reducer now interns canonical piece keys and versioned
host BLOBs into flush-local integer IDs. Its hot support state is
`Counter[(piece_id, host_id)]`, with a separate role-bearing compact counter
only when diagnostics are enabled. Interners and counters are cleared together
at every existing `flush_types` boundary.

Host BLOB codec v1 is one version byte followed by one fixed byte per
phoneme. The 50-code table is explicit, independent of Enum declaration
position and Python hash, and ordered by canonical phoneme identifier. This
makes same-version BLOB ordering identical to canonical dotted host-key
ordering, including prefix forms. The codec is bijective and rejects empty,
truncated, unknown-version, zero-code, and out-of-range-code payloads.

New packed bundle wire uses bundle schema v4, segment schema v5, and format
`segment_dictionary_u32_host_blob_v1_binary64_le_v2`: piece dictionaries stay
short UTF-8 keys, host dictionaries contain the codec BLOB directly, and rows
retain their original dictionary IDs plus exact IEEE-754 binary64 values.
Embedded v1, TSV v2, and packed-string v3 bundle readers remain accepted and
are converted into the compact accumulator in canonical stream order.

At flush, integer IDs are assigned canonical ranks from the actual piece keys
and host BLOBs; pair IDs are sorted by those ranks. ID assignment order and
process-randomized hashes therefore cannot affect output order.

## Transient SQLite and resume

New active passes create:

```sql
piece_host_support_next(
    piece_key TEXT,
    host_key BLOB,
    support REAL,
    PRIMARY KEY(piece_key, host_key)
) WITHOUT ROWID
```

Metadata key `s1m2_transient_support_schema=host_blob_v1` records the
engineering layout without entering scientific configuration identity.
Resume checks the declared `host_key` type and metadata. Existing active
legacy `TEXT` tables are explicitly admitted as `host_text_v1_legacy`; compact
hosts are decoded only at that compatibility boundary. Conflicting or unknown
schema/metadata fails closed with an engineering restart message. No table or
scientific checkpoint is silently dropped or reinterpreted.

Finalization still performs one grouped scan for per-piece `MAX(S)` and
`SUM(S*S)` and drops the transient table only inside the existing pass-final
transaction. BLOB lexical ordering is deliberately identical to the old host
string order, so the grouped floating input order is unchanged.

## Bounded multi-row upsert

Piece counts, pooled piece/host support, lexical diagnostics, and the optional
role diagnostic path now use bounded multi-row `VALUES` statements. The fixed
900-bind ceiling gives batches of 450 two-column rows, 300 three-column rows,
and 225 four-column rows. Input is consumed one batch at a time; no complete
document iterable is materialized. Tests compare repeated same-key conflicts
within and across batches to ordered `executemany` results exactly.

## Canonical floating order

The production sequence remains:

```text
document -> bundle index -> segment -> support row
-> per-key Counter += in stream order
-> unchanged unique-key flush boundary
-> canonical (piece key, host key) order
-> SQLite statements in that row order
```

Multi-row statements contain rows in the same canonical sequence. A focused
test covers multiple bundle groups, repeated keys, and multiple flushes, and
compares every flush row and float exactly against the old string-Counter
reference. Another test proves multi-row conflict evaluation matches ordered
single-row stepping across batch boundaries.

## Journal strategy evidence

The tracked benchmark is
`scripts/analysis/benchmark_s1m2_sqlite_journal.py`; machine evidence is
`evidence/s1m2_round3d_sqlite_journal_microbenchmark_20260928.json`.
It used a temporary directory, 40,000 compact-BLOB keys, 10,000 preexisting
rows, four conflict rounds, realistic short/long piece keys, and 160,000
measured input rows. Total wall was 16.96 seconds.

| Mode | transaction before commit | commit | peak DB+journal/WAL |
| --- | ---: | ---: | ---: |
| WAL + NORMAL | 2.410 s | 0.014 s | 4,028,808 B |
| DELETE + NORMAL | 6.331 s | 0.022 s | 4,008,960 B |
| TRUNCATE + NORMAL | 7.046 s | 0.019 s | 4,008,960 B |

All modes passed uncommitted-close rollback, committed-state reopen, and
`quick_check`. DELETE/TRUNCATE saved only about 0.5% peak bytes in this local
workload while taking about 2.6-2.9x as long before commit. This small local
result cannot qualify Core-11 behavior and does not justify the recovery and
reader-locking risk of a production switch. Production therefore remains
WAL + NORMAL. Runtime payload now records the journal mode, synchronous mode,
and transient support schema explicitly.

## External-run audit

Append-only packed runs were audited but not implemented. A correct design
would require immutable per-flush records carrying document ordinal, flush
ordinal, canonical key order, and binary64 support; checksum-named files
published before an atomic SQLite document-manifest/checkpoint commit; orphan
rejection after precommit crashes; and a pass-final multiway merge that adds
each key's flush values in original document/flush order before computing M/Q.

That is not a small extension: it creates a new cross-filesystem durability,
garbage-collection, merge-order, and recovery contract. Round 3D's compact
identity and batched B-tree path is materially smaller and fully covered by
the current transaction semantics. External runs remain a concrete follow-up
only if the next Core-11 comparator passes and telemetry still shows SQLite
support flush as the dominant reducer tail.

## Telemetry

New reducer telemetry covers decoded support/role rows; decode, accumulation,
sort, and SQLite flush seconds; flush calls and rows; peak unique piece keys,
host keys, and pairs; canonical versus compact host dictionary bytes and
avoided bytes. Store telemetry adds statement batch calls, rows, and maximum
rows for piece counts, pooled support, lexical diagnostics, and role support.
Existing upsert totals, document commit time, and storage high-water metrics
remain.

## Local validation

- touched modules and benchmark script compile;
- 63 focused codec/V3/bundle tests passed in 14.16 seconds;
- 98 selected phonology/storage/comparator/V2/V3/training/bundle/Round-3 tests
  passed in 36.48 seconds;
- one broader 112-test selection had 111 passes and one unrelated existing
  Round-4 control-plane fixture failure because its monkeypatched lambda does
  not accept the current `repo_root=` keyword; no Round-4 code was changed;
- corrected journal benchmark: 16.96 seconds;
- `git diff --check` passed.

No representative/stress workload, Passes 2/3 production benchmark, Full M0,
VM, cloud, SSH, or Core-07 through Core-11 action occurred.

## Remaining risk and next gate

The reducer/SQLite phase remains single-writer and still maintains a transient
B-tree; multi-row stepping and compact identities reduce its Python/object,
comparison, and VM-step costs but do not remove serialization or random page
updates. The next evidence gate is the unchanged complete first-document
Core-11 baseline/candidate/comparator protocol. Comparator PASS at frozen
`rtol=1e-10`, `atol=1e-12` remains mandatory before interpreting runtime,
RSS, WAL/storage, or reducer telemetry.

DATE=2026-09-29
BRANCH=exp/s1m2-runtime-reopen
STATUS=S1M2_V3_ROUND3D1_3EA_CANDIDATE_AWAITING_CORE08_VM_GATE

BASELINE_SHA=5ec5d5c33a59abe06fadc9bde84f48b380b7fe39
ROUND3D_SHA=38557dab9bff522dfb886452b4786da04e627458
ROUND3D_HANDOFF_SHA=9b4950cad98778fd53f5f360eb468573c7f55d11
ROUND3D1_3EA_CANDIDATE_SHA=ddd5e0dd34d9cc9ff15d43776821691c11855f2d
SCIENTIFIC_SEMANTICS=FROZEN
ROUND3D1_STATUS=PASS
ROUND3EA_STATUS=PASS
PERFORMANCE_RESULT=LOCAL_MICROBENCH_ONLY
FULL_M0_RUNTIME_VIABLE=NOT_REQUALIFIED
PRODUCTION_JOURNAL_MODE=WAL_NORMAL_UNCHANGED

Core-08 completed and durably committed the complete first Devanagari
continuous document under Round 3D, then failed V3 finalization on one
production-scale C/Q row. Peak process-tree RSS was 9,328,275,456 bytes with
zero swap and all bundle shards retired; transient SQLite/WAL and the single
writer are now dominant. The durable checkpoint remains active Pass 1 at next
document index 1, with no completed pass.

Round 3D.1 keeps the normal SQL validator and authoritative eight-ULP helper
unchanged. A suspect row alone re-reads persisted supports in canonical order,
uses math.fsum for C/Q, validates Q provenance and support legitimacy, applies
the authoritative helper to support-derived moments, and admits C drift only
under the standard positive binary64 summation-error envelope. Material
mismatch and corrupt/nonfinite/negative/zero-inconsistent state fail closed.
Optional role diagnostics use the same mechanism.

Atomic timing_metrics.partial.json is written after durable document commits,
pass-final success, and pass-final exceptions. It is engineering-only,
non-comparator telemetry and cannot mask an original exception. Formal timing
metrics and checkpoint semantics remain unchanged.

Round 3E-A uses the fixed phonological BLOB codec for both transient piece and
host keys. Persistent piece_lexicon keys remain TEXT. Resume admits only
metadata/type-consistent BLOB/BLOB v2, Round 3D TEXT/BLOB v1, and historical
TEXT/TEXT layouts. The bundle wire is unchanged and compact hot flushes do not
reconstruct piece strings.

Runtime SQLITE_LIMIT_VARIABLE_NUMBER is queried when available. A single
0.916-second benchmark compared 300/600/1200 support rows per statement;
1,200 rows reduced wall time about 18% with exact equal results and no observed
storage increase. Production uses min(runtime limit, 3600 binds). WAL, page
cache, and transactions are unchanged. Direct final-table construction was
audited and deferred.

Validation completed locally:

- 73 focused tests passed in 11.17 seconds;
- 38 adjacent tests passed in 20.69 seconds;
- final combined selection passed 116 tests in 33.59 seconds;
- touched modules compile, evidence JSON parses, and git diff --check passes.

No representative/stress workload, Passes 2/3 production benchmark, Full M0,
VM/cloud/SSH action, push, fetch, or pull occurred. DECISIONS.md is unchanged
because no research/scientific decision changed.

NEXT_ACTION=RESEARCHER_OPERATES_CORE08_VM_GATE
NEXT_VM_GATE=CORE08_RESUME_DURABLE_ROUND3D_PASS1_FINALIZATION_THEN_COMPARE_WITH_ONE_CLEAN_ROUND3EA_FIRST_DOCUMENT_RUN

Authority:
`reports/core_methods/reusable_pieces/s1m2_runtime_reopen_round3d1_3ea_20260929.md`

Local revalidation command:

```powershell
python -m pytest tests\latent\test_phonology.py tests\pieces\test_reusable_objective_v2.py tests\pieces\test_reusable_objective_v3.py tests\pieces\test_s1m2_bundle_scheduler.py tests\latent\test_s1m2_storage_lifecycle.py tests\pieces\test_s1m2_training.py tests\latent\test_training.py tests\latent\test_s1m2_artifact_comparison.py -q
```

Do not launch VM/cloud/Full M0 automatically. Do not touch Core-07 through
Core-10 or any live run/checkpoint/artifact state without a new explicit
researcher instruction.

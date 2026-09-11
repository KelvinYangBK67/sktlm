# S1M2 Round 3 Closure

Date: 2026-09-11  
Repository: `KelvinYangBK67/sktlm`  
Branch: `exp/s1m2-reusable-pieces`

## 1. Scope and conclusion

Round 2 completed the engineering scaling comparison, but formal scientific
closure failed because exact candidate support could exceed the historical
internal-match ceiling. Round 3 removed that truncation exactly, preserved the
frozen scientific semantics, checked a real offender and the known pressure
tail, confirmed worker-independent scientific output, and reconciled the
production audit and Full control plane.

```text
ROUND3_STATUS=PASS
ROUND3_VM_REQUIRED=NO
```

## 2. Round 2 inherited state

```text
ROUND2_FORMAL_SCIENTIFIC_STATUS=FAIL_CANDIDATE_OVERFLOW
ROUND2_FORMAL_WINNER=NONE
ROUND2_ENGINEERING_PREFERENCE=w12
```

Round 3 does not rewrite the historical Round 2 result. It resolves the
candidate-overflow blocker while retaining, but not re-running, the separate
Round 2 engineering preference.

## 3. Compact exact inference closure

The production path uses a direct structural form trie and retains exact legal
support without internal-match truncation. It introduces no approximation,
beam, pruning, or sampling. Whole-form handling, piece expected counts, and
`piece_occurrence_support` remain exact; Top-K remains presentation-only.

The implementation checkpoints are:

- `7752da2c453804a000dac83a36bd4aa58b9a0b8c` — `perf: add compact exact S1M2 inference`
- `ba4cc5f99752e66d01944869bea92b77b0dd32b7` — `perf: compact exact piece occurrence support`

## 4. Real-offender exactness

The raw-520 real offender retained all 520 internal matches. Scalars, lexical
expected counts, piece expected counts, piece occurrence support, rule usage,
boundary posteriors, and total posterior mass all passed compact-versus-legacy
exactness. `support_truncation_tokens=0` and `shared_batch_fallbacks=0`.

Evidence: `artifacts/s1m2_candidate_pressure/round3_real_offender_exactness_raw520.json`  
SHA-256: `23f5006a3845b7bae108186cf335ff7c8f49f0b5b862d619715f87f47f914ec6`

## 5. Local worker scientific equivalence

The w2 and w4 runs used the same bundle plan. Training history and piece
lexicon state were exact, and all recorded scientific artifacts were
byte-identical. This verifies scientific worker-independence; it does not
reopen performance worker selection.

```text
WORKER_SELECTION_REOPENED=NO
ROUND2_ENGINEERING_PREFERENCE_RETAINED=12
```

Evidence: `artifacts/s1m2_candidate_pressure/round3_local_worker_equivalence_w2_w4.json`  
SHA-256: `e4089aa98fb2e777b098ee97f17bb58f3cda76123c9873347a238d12cc7ab6ea`

## 6. Compact pressure-tail gate

| raw | retained | phonemes | inference seconds | truncation | fallback | posterior mass |
|---:|---:|---:|---:|---:|---:|---:|
| 1002 | 1002 | 1014 | 68.443 | 0 | 0 | 1.0 |
| 1410 | 1410 | 1559 | 55.571 | 0 | 0 | 1.0 |
| 1841 | 1841 | 1778 | 162.569 | 0 | 0 | 1.0 |
| 2484 | 2484 | 2634 | 106.330 | 0 | 0 | 1.0 |

Raw 2484 is the known maximum raw internal-match pressure from the full-corpus
pressure census. Runtime is diagnostic only: no monotonicity claim or runtime
threshold is part of the scientific gate.

```text
COMPACT_PRESSURE_TAIL_GATE=PASS
FULL_MAX_RAW_2484=PASS
```

## 7. Production audit and control-plane closure

Commit `ce2046b035f4163523de23b1d964b2d48cc5c19e` (`prod: close S1M2 round3
control plane`) makes retained legacy topology archives optional for compact
exact completed runs while continuing to reject topology metadata that claims
mutable scientific state. The formal Round 3 closure binds the immutable Round
2 result, frozen production contract, implementation commits, and all evidence
files by SHA-256. Final-plan construction requires a validated closure.

```text
COMPACT_PRODUCTION_AUDIT=PASS
LEGACY_TOPOLOGY_REQUIRED=NO
ROUND3_TO_FULL_CONTROL_PLANE=PASS
```

## 8. Worker and Full handoff

The Round 2 formal winner remains `NONE`. Full uses 12 workers on the distinct
basis `round2_engineering_preference_retained_by_round3_closure`; worker
selection was not reopened. All six Full cells retain their existing mapping.
The Full Devanagari-continuous cell remains bound to:

```text
artifacts/s1m2_execution_bundle_plans/full_m0_devanagari_continuous_tp279047
SHA256=9c828b6612d3e60b443511907dc2f731a08548be07caf513ea346e43b7d6414a
```

```text
WORKER_SELECTION_REOPENED=NO
FULL_WORKERS=12
FULL_BUNDLE_SCHEDULER_WIRING=PASS
W20_ACTIVE_PATH=RETIRED
LEGACY_3H_GATE=NOT_APPLICABLE
```

## 9. Final status

```text
ROUND3_STATUS=PASS
ROUND3_VM_REQUIRED=NO

COMPACT_REAL_OFFENDER_EXACT_EQUIVALENCE=PASS
COMPACT_LOCAL_WORKER_EQUIVALENCE=PASS
COMPACT_PRESSURE_TAIL_GATE=PASS
FULL_MAX_RAW_2484=PASS

ROUND2_FORMAL_RESULT=PRESERVED_FAIL
ROUND2_FORMAL_WINNER=PRESERVED_NONE
ROUND2_ENGINEERING_PREFERENCE_RETAINED=12
WORKER_SELECTION_REOPENED=NO

CANDIDATE_OVERFLOW_BLOCKER=RESOLVED_BY_COMPACT_EXACT_INFERENCE

COMPACT_PRODUCTION_AUDIT=PASS
LEGACY_TOPOLOGY_REQUIRED=NO

ROUND3_TO_FULL_CONTROL_PLANE=PASS
FULL_BUNDLE_SCHEDULER_WIRING=PASS
FULL_WORKERS=12
FULL_ELIGIBILITY=PASS

W20_ACTIVE_PATH=RETIRED
LEGACY_3H_GATE=NOT_APPLICABLE

FULL_M0_AUTHORIZED=NO
```

Full eligibility records a closed local control plane. It is not authorization
to launch Full M0.

## Evidence appendix

| Artifact | SHA-256 | Purpose | Result |
|---|---|---|---|
| `artifacts/s1m2_candidate_pressure/round3_real_offender_exactness_raw520.json` | `23f5006a3845b7bae108186cf335ff7c8f49f0b5b862d619715f87f47f914ec6` | Real-offender compact/legacy exactness | PASS |
| `artifacts/s1m2_candidate_pressure/round3_local_worker_equivalence_w2_w4.json` | `e4089aa98fb2e777b098ee97f17bb58f3cda76123c9873347a238d12cc7ab6ea` | Scientific worker-independence | PASS |
| `artifacts/s1m2_candidate_pressure/round3_compact_tail/raw1002_postfix.json` | `f1bec7a7e282b4d2aaa0cb4cd66596b4c5672cfa1bece1d78be3af2882a0c158` | Compact pressure tail, raw 1002 | PASS |
| `artifacts/s1m2_candidate_pressure/round3_compact_tail/raw1410_postfix.json` | `970ccb7723e7d975b877991655c68980f17e00f5ce076a93a47765a132455eb9` | Compact pressure tail, raw 1410 | PASS |
| `artifacts/s1m2_candidate_pressure/round3_compact_tail/raw1841_postfix.json` | `898e01fade615ca1cbde54122628cf8889ab1f3d534bf3b494c55406a60c73b7` | Compact pressure tail, raw 1841 | PASS |
| `artifacts/s1m2_candidate_pressure/round3_compact_tail/raw2484_postfix.json` | `b117144d5f0cc16ddfd5c1aee8bf2b2d09f4f1afb31040d3e3e3b1abec5afd71` | Known full-census maximum pressure | PASS |
| `artifacts/s1m2_production/round3_closure_local.json` | `2344765871123568255175cf3f863598e62ddda171d22a48c04a250b258313cf` | Machine-readable Round 3 closure | PASS |
| `artifacts/s1m2_production/final_plan_local.json` | `c70d67dac207ac2226018a60496953b6d3aa893ad1f50a0a7eaa3593dbf51214` | Local six-cell Full-plan eligibility | PASS |

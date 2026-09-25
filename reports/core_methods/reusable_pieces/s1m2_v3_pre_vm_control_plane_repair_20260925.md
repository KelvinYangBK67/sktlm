# S1M2 V3 pre-VM control-plane repair

Date: 2026-09-25

Status: **CONTROL-PLANE REPAIR COMPLETE; FINAL PLAN MUST BIND POST-REPAIR HEAD**

```text
ROOT_CAUSE_1=STALE_ACTIVE_V1_BUNDLE_ARTIFACTS
ROOT_CAUSE_2=ACTIVE_FOUR_VM_DEPLOYMENT_NOT_EXPLICITLY_ENCODED

SCIENTIFIC_SEMANTICS_MODIFIED=NO
RUNTIME_SCIENTIFIC_IMPLEMENTATION_MODIFIED=NO
CONTROL_PLANE_MODIFIED=YES
EXECUTION_METADATA_REMATERIALIZED=YES

CURRENT_ACTIVE_VM_COUNT=4
CURRENT_ACTIVE_CELL_COUNT=4
CURRENT_EXECUTION_SCOPE=EXPLICIT_SUBSET
```

## Preserved scientific authority

The frozen scientific matrix remains the six cells in
`configs/production/s1m2_six_cell_v3.json`. The file remains byte-identical at
SHA-256 `6a29480ba27d82ed334cdc6027f2aedab30e6fc7b3f5ebe2465ff6469b3022fa`
and canonical SHA-256
`03c524b8978919bbfb98f65caaf75625e4cd053314c704f433ad002009b27bd2`.
The accepted runtime implementation remains
`7ae18240b2e81125cc2fc159969760e4deccafc6`.

The six-cell scientific matrix and the current active deployment are distinct
objects. The current deployment is the following operational subset:

| Active cell | VM role |
|---|---|
| `s1m2_m0_prime_iast_continuous` | `core-07` |
| `s1m2_m0_devanagari_continuous` | `core-08` |
| `s1m2_m0_iast_surface_word` | `core-09` |
| `s1m2_m0_iast_legacy_joined` | `core-10` |

`s1m2_m0_devanagari_surface_word` and
`s1m2_m0_devanagari_legacy_joined` remain scientific-matrix members and are
outside the current deployment scope.

## Bundle compatibility repair

The current loader requires planner, scan, plan, and bundle schema v2. The two
continuous active plans already passed that loader. The active IAST
`surface_word` and `legacy_joined` plans were v1 and failed closed, so they were
rematerialized once each with target pressure 279047, at most 256 segments per
bundle, at most 128 tokens per segment, and the full frozen 240-document input.

| Cell | Old | New | New plan SHA-256 | New materialization SHA-256 |
|---|---|---|---|---|
| IAST surface_word | planner/scan/plan/bundle v1 | planner/scan/plan/bundle v2 | `1eaade371365aa527f010d036165ed2621dcaa5a0152e0f79bd190af5bf7bdcd` | `55ae6730b6eed6ae739e5658e8a843e285150a56200a1db6787be48d9c29289d` |
| IAST legacy_joined | planner/scan/plan/bundle v1 | planner/scan/plan/bundle v2 | `6cd1c29159b5905fd1897a1698c42212d759f0edd5cf0c01355176fd01bea04f` | `3723ecbe0c1cbdda8fb8d60f35d96bdcbf6d3ee4e14dc0fe34f15eeee04af4da` |

For each rematerialized cell, old and new metadata have identical manifest
identity, script, condition, document-list state, 240-document coverage,
complete segment count, phoneme count, pressure, segment-sequence SHA-256,
representation-set SHA-256, target pressure, maximum segments per bundle, and
maximum segment tokens. The planner configuration path is provenance only and
changed from the historical production configuration to the current planner's
authoritative configuration. Expected v2 differences are schema and planner
versions, first-line byte offsets, plan digest, materialization digest, and
artifact path.

The active bundle identities are:

| Cell | Plan SHA-256 | Materialization SHA-256 |
|---|---|---|
| IAST-prime continuous | `80bb77722abe9863865331a1f67809d4db703d7eb52cf75e6e36ddbf3b06ed4d` | `0bced4aa2e3377ff084432fae9eedc715a7c04aba4633eda689c31a2e26591f3` |
| Devanagari continuous | `d664239965cf9a629a9b3953f137860cd57c7a81184a1497039e843431f4c224` | `19e444d6b9b341a9df93faa33c452ef0393841cef3986109ccd6709c4867762c` |
| IAST surface_word | `1eaade371365aa527f010d036165ed2621dcaa5a0152e0f79bd190af5bf7bdcd` | `55ae6730b6eed6ae739e5658e8a843e285150a56200a1db6787be48d9c29289d` |
| IAST legacy_joined | `6cd1c29159b5905fd1897a1698c42212d759f0edd5cf0c01355176fd01bea04f` | `3723ecbe0c1cbdda8fb8d60f35d96bdcbf6d3ee4e14dc0fe34f15eeee04af4da` |

## Active deployment authority

`configs/deployment/s1m2_v3_active_four_vm.json` is the tracked authority for
the current topology. Its file SHA-256 is
`f91b26900b5000c5bd2354a60f5fa6dbb883f5db0a9d0fab2e643fc533880e89`.
It binds the frozen contract identity, exact active and inactive cell sets,
four unique host roles, and all four current v2 bundle plan and materialization
identities.

`plan-final --deployment-manifest ...` now validates this authority and derives
cell selection, order, host roles, and bundle identities from it. The plan
stores deployment path, file SHA-256, and deployment ID. Plan validation and
the run path re-resolve the manifest and its four bundles, so changed topology
or artifacts fail closed. Omitting the deployment manifest preserves the
historical contract-owned planning behavior.

## Local validation

The following cheap deterministic checks passed:

- current v2 loader validation for all four active bundle plans;
- exact old/new metadata coverage comparison for both rematerialized plans;
- active deployment manifest validation;
- in-memory four-job final-plan construction and plan validation;
- historical Round3 closure validation, closure SHA-256
  `0062e2a5442b298e2ceae2ad97b811f8f57775a0d67ac6d7ab295528bc8dd937`;
- bound real-offender exactness, local worker equivalence, and pressure-tail
  evidence validation;
- Python syntax parsing, JSON parsing, hash inspection, and `git diff --check`.

The historical Round2 artifact is identity-valid and retains its formal
`FAIL` result; Round3 explicitly preserves that result while supplying the
accepted 12-worker engineering closure.

The private local inventory contains distinct `core-07`, `core-08`,
`core-09`, and `core-10` profiles whose machine IDs and roles match their
profile names. It does not record SKU, RAM, or data-disk capacity fields. No
network, SSH, cloud, or VM operation was used.

No test suite, benchmark, profiler, scientific workload, training, inference,
or performance validation was run. This repair makes no runtime or RSS claim.

## Post-commit final-plan and launch rule

The final launch candidate must be generated only after the repair commit is
pushed and the tracked worktree is clean, so it binds that post-repair Git
identity. It must use this deployment manifest, exactly four jobs,
`FULL_EXECUTION_SCOPE=EXPLICIT_SUBSET`, and `FULL_WORKERS=12`.

Every later Full launch command requires the plan-specific authorization:

```text
--authorization <artifact>
```

Plan construction does not create that artifact. Full authorization, VM power
on, SSH, cloud contact, and production execution remain researcher actions.

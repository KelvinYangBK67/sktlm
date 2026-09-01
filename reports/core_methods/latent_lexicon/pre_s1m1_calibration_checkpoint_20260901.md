# Pre-S1M1 calibration checkpoint (2026-09-01)

Status: **CLOSED**. This records completed calibration evidence and the
decision to proceed with the six unrestricted M0 representation cells. It
does not authorize or record any cloud launch.

## Unrestricted replica closure

Four independent full-M0 IAST + surface_word replicas completed at 8 workers
and three passes. Their six canonical scientific artifacts are byte-identical.

| Replica | Wall seconds | Peak process-tree RSS (bytes) |
|---|---:|---:|
| rep01 | 13,058.676 | 3,711,254,528 |
| rep02 | 12,615.774 | 3,729,432,576 |
| rep03 | 13,103.272 | 3,728,773,120 |
| rep04 | 13,165.096 | 3,708,420,096 |

The unrestricted inspection has 19,068,580 active lexical rows, 18,851,674
with expected count at most 1.0. Its expected lexical-token total is
4,959,352.982; identity/latent mass is 0.146671/0.853329, mean top-1 posterior
0.655637, and mean entropy 0.920788. Final-count coverage needs 1,026,927
identities for 90%, 1,492,759 for 95%, and 2,084,311 for 99%; the top 16,384
and 32,768 cover only 0.619975 and 0.656458.

## Fixed-K sensitivity closure

K16 and K32 share an identical neutral Pass 1 with unrestricted training:
12,703,571.324 expected lexical tokens, identity/latent mass
0.029399/0.970601, log partition 14,259,900.999, 303,120,539 candidate edges,
19,889,992 factors, and 80,127,806 nodes. Divergence begins only after the
deterministic Pass-1 vocabulary freeze and base-unit projection.

| Measure | Unrestricted | K16 | K32 |
|---|---:|---:|---:|
| active inspection rows | 19,068,580 | 16,382 | 32,766 |
| expected lexical tokens | 4,959,352.982 | 22,410,480.125 | 18,864,970.926 |
| mean identity mass | 0.146671 | 0.051348 | 0.056446 |
| mean latent mass | 0.853329 | 0.948652 | 0.943554 |
| mean top-1 posterior | 0.655637 | 0.140614 | 0.162740 |
| mean entropy | 0.920788 | 5.512865 | 4.968037 |
| rule expected usage | 3,216,466.447 | 9,191,227.169 | 8,929,638.109 |
| singleton-base mass fraction | n/a | 0.598042 | 0.502949 |

Relative to unrestricted, expected lexical-token totals are 4.518831x and
3.803918x; rule usage is 2.857554x and 2.776226x. Both rule distributions are
far from unrestricted (total variation 0.523658 and 0.508165) but close to
each other (total variation 0.023012; Jensen-Shannon 0.000460 nats).

K16 and K32 therefore form the same strong capacity-stress regime, not two
sides of a natural sweet spot. Fixed-K sensitivity is closed: do not add K
values, reopen a grid, or run the previously contemplated 18-cell matrix.
K16/K32 remain appendix sensitivity evidence.

Interpretation limits:

- identities are lexical word forms, not stems or morphemes;
- singleton-base mass is a projection-pressure proxy, not an exact OOV rate;
- unrestricted final top-K mass and fixed-K Pass-1 selection are not directly
  comparable;
- final exports include only inspection-active rows (16,382/32,766 and 48
  singleton bases), while checkpoint vocabularies retain 16,384/32,768
  identities and all 50 bases;
- near-universal multi-surface/context coverage under fixed K reflects
  compression/projection, not linguistic quality.

The small inputs used for this closure remain under
artifacts/calibration_analysis/fixed_k_sensitivity_20260901/. No benchmark,
audit, or hash was rerun.

## Representation-gate readiness

The CLI/config now select all six frozen M0 cells while preserving IAST +
surface_word defaults and unrestricted semantics. The script-neutral
phonological interface includes the generated-M0 Devanagari frontend. Direct
full-M0 audit handles formal selectors, metrics binding, and fixed-vocabulary
contracts. Collection has keepalives, verified resume, and exact partial
identity protection. Focused validation passed: **80 tests in 8.33 seconds**.

The active path is unrestricted M0 for IAST + legacy_joined, IAST + continuous,
and all three Devanagari spacing conditions. IAST + surface_word is supplied by
the accepted replicas. The five assignments are PREPARED only; human commands
are in six_representation_gate_launch_plan_20260901.md.

Baseline/tokenizer comparison, common evaluation, S1M1 specification freeze,
aggregation, and paper outputs remain deferred until this gate is complete.

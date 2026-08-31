# P10 medium worker-scaling checkpoint — 2026-08-31

This report promotes the completed local 4-worker and 8-worker P10 medium runs
out of gitignored `artifacts/` into the durable research record. The first
8-worker attempt was manually interrupted and is diagnostic-only.

## Frozen scientific contract

Both formal runs use:

- branch: `exp/m0-core-methods`;
- implementation: `latent-lexicon-v1`, with P10 code at `dc68089`;
- condition: IAST + `surface_word`;
- medium list: `configs/benchmarks/latent_medium_documents.txt`, 20 documents;
- medium list SHA-256:
  `52ac2647807670f7c29a35715432d4ff724c1b0b6bb3886a84fd7ebc4d421fab`;
- M₀ freeze ID:
  `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`;
- representation manifest SHA-256:
  `c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520`;
- 1,218-rule external-sandhi inventory, SHA-256:
  `76f00baca78f97472731ff6ba1e24fca56985bc229523fb2dcc7a2018fa73f00`;
- 3 training passes plus final inspection;
- exact inference and equivalence diagnostics;
- alpha 0.1, lambda 0.5, tau 1.0;
- ignored-whitespace penalty 8.0;
- top-k 8, lexical cache 100,000, flush bound 50,000;
- candidate limits: 512 internal matches and 128 segment tokens.

The runs used the same Windows host: 16 logical CPUs, Intel64 Family 6 Model
154, Python 3.11.9, SQLite 3.45.1, NumPy 2.4.6, SentencePiece 0.2.2, and
PyTorch 2.13.0.

## Run inventory

| role | run ID / artifact path | provenance commit | workers | status |
|---|---|---|---:|---|
| production local reference | `medium_optimized_p10_w4_p3/` | `9be29eadf1c3ca67f922847b5547ae32dd1b8f49` | 4 | complete and audited |
| interrupted diagnostic | `medium_optimized_p10_w8_p3_interrupted/` | `25998f0d05948c02b04ff1b4971cf398656b8799` | 8 | manual Ctrl+C; excluded |
| clean scaling run | `medium_optimized_p10_w8_p3_rerun1/` | `25998f0d05948c02b04ff1b4971cf398656b8799` | 8 | complete and audited |

All paths are below `artifacts/latent_benchmarks/`.

## Clean 8-worker integrity audit

The clean rerun satisfies every gate:

- `completed_passes = 3` and `inspection_complete = true`;
- 20 documents, 95,847 segments, and 4,231,365 characters per pass;
- 1,659,294 candidate factors, 6,507,811 nodes, and 23,089,593 edges;
- zero overflow in every pass and final inspection;
- `benchmark_metrics.runtime` exactly equals `timing_metrics.json`;
- no training/inspection shard, `*.tmp`, WAL, or SHM residue;
- SQLite `PRAGMA quick_check = ok`;
- training lexicon: 1,888,526 rows, count sum 394,031.7571645344;
- inspection counts: 1,888,526 rows, count sum 395,770.48199961643;
- surface usage: 715,523 rows;
- context usage: 1,033,306 rows.

The 4-worker database has the same row counts and numeric totals. Database bytes
need not be identical because run metadata differs; the scientific exports
below are exactly identical.

## Exact scientific equivalence

The canonical scientific set established by the earlier P8/P10 audit is:

| file | bytes | SHA-256 |
|---|---:|---|
| `iteration_metrics.json` | 1,504 | `c0d7effebb2a1070474a55aa70ad586f31bc79cc5979c9cfeca2a51a4dfd20d3` |
| `summary.json` | 1,119 | `e64f6f13cf06facc8e2198980ad71c66fbf46ab9ab3826ce1402d6db033195c3` |
| `analyses.jsonl` | 1,036,072,476 | `27f6b5ace1f7e145c02d8fd9cb88193ef9a79ab045db76494dfd595d81f5caa4` |
| `boundary_posteriors.jsonl` | 442,298,527 | `b620f71b832547790c101d5dd8d8c5f1c801716f3a1dbb85c4a03d464ae7e579` |
| `latent_lexicon.tsv` | 323,003,959 | `223141327fd83d6f06cf73ea554135a94c2fccf224c7917b9fd2e14d0af1062a` |
| `rule_usage.tsv` | 27,962 | `bd47ab7c7026c4491b03ad000b090017285d0a4d4574fb65946f9a89373498c6` |

All six size/hash pairs are identical between the clean 4-worker and 8-worker
runs. This is stronger evidence than tolerance-based numerical equivalence.
The legacy `sktlm.latent.equivalence` command was not used because it
materializes multi-gigabyte JSONL/TSV files; the audit used bounded-memory
streaming SHA-256.

Important scientific diagnostics are consequently unchanged:

- mean identity / latent mass: 0.070468 / 0.929532;
- mean entropy: 1.044665;
- mean top-1 posterior: 0.594393;
- active / low-count types: 1,888,526 / 1,866,960;
- expected inspection lexical tokens: 395,770.4820;
- expected external-rule usage: 262,181.0102.

## 4-worker versus 8-worker performance

| measurement | 4 workers | 8 workers | 8-worker change |
|---|---:|---:|---:|
| wall | 1,216.915 s | 1,526.624 s | +309.709 s / +25.45% |
| training document wall | 625.509 s | 708.879 s | +83.369 s / +13.33% |
| inspection document wall | 523.347 s | 664.893 s | +141.546 s / +27.05% |
| benchmark total CPU | 2,859.047 s | 3,539.859 s | +680.813 s / +23.81% |
| character throughput | 13,908.50/s | 11,086.85/s | -2,821.65/s / -20.29% |
| artifact bytes | 2,571,478,809 | 2,571,478,853 | metadata-only difference |
| main-process peak RSS | 78,397,440 B | 78,729,216 B | not process-tree memory |

The 8-worker wall “speedup” is 0.797x: it is a regression. Both training and
inspection regress, total CPU rises, and throughput falls. This is consistent
with contention/oversubscription on the 16-logical-CPU Windows host rather than
a single isolated phase.

The local production sweet spot is therefore 4 workers. There is no empirical
reason to spend additional local time on 12 or 16 workers. This conclusion is
host-specific and must not be extrapolated to the Ubuntu cloud VM.

The current local full-M₀ projection remains the 4-worker estimate: 4.60 hours
by characters or 4.06 hours by document count. The inferior 8-worker result
would project to 5.77 or 5.09 hours respectively.

## Interrupted 8-worker diagnostic

`medium_optimized_p10_w8_p3_interrupted/` was stopped manually with Ctrl+C.
Its checkpoint has zero completed passes, `active_pass = 1`,
`next_document_index = 0`, and no durable document metrics. It has no
`benchmark_metrics.json`. The preserved directory contains 24 shard files,
including 8 zero-byte `*.tmp` files, totaling about 85.1 MB across all files.

This state is useful evidence that out-of-order worker shards can exist before
the first canonical document commits. It is not a completed/resumed benchmark,
and no partial time, shard count, or work estimate from it is included in the
performance table.

## Decision

Local scaling is closed:

1. use 4 workers for any local production fallback;
2. do not benchmark local 12/16 workers;
3. move to the independent cloud 4→8 medium gate;
4. collect simultaneous process-tree RSS, CPU utilization, and I/O on cloud;
5. do not start full M₀ until cloud medium results establish a worker sweet spot
   and credible storage/memory headroom.

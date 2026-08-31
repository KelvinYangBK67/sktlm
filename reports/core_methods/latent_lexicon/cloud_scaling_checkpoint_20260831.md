# Cloud P10 scaling checkpoint - 2026-08-31

This is the authoritative tracked closure of the cloud medium-scaling gate.
Operational instructions remain in `cloud_deployment_ubuntu22.md`; local
4-vs-8 evidence remains in `medium_scaling_p10.md`.

## Fixed scientific condition

| Item | Authoritative value |
|---|---:|
| frozen corpus | GRETIL M0, 240 documents |
| freeze ID | `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40` |
| representations | 1,440 |
| external-sandhi rules | 1,218 |
| script / spacing | IAST / `surface_word` |
| inference | exact |
| lexical alpha | 0.1 |
| complexity lambda / tau | 0.5 / 1.0 |
| whitespace penalty | 8.0 |
| passes | 3 |
| scientific checkpoint | `fbd0a499701d6a13dcbf8374d5b5ce3a357a7b04` |
| cloud host class | Ubuntu 22.04, 16 vCPU, approximately 32 GB RAM |

## Completed cloud medium results

All four runs reached DONE and all four remote audits reported `valid = true`.

| Rank | Machine | Run | Workers | Wall seconds | Throughput (chars/s) | CPU seconds | Benchmark peak RSS bytes | Aggregate artifact bytes |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `core-02` | `cloud_medium_p10_w8_p3` | 8 | 740.9371817360001 | 22843.313059744156 | 2157.7326972640003 | 75,665,408 | 2,571,276,002 |
| 2 | `core-04` | `cloud_medium_p10_w16_p3` | 16 | 849.243166304 | 19930.051452355478 | 2901.433185465 | 77,217,792 | 2,571,276,026 |
| 3 | `core-03` | `cloud_medium_p10_w12_p3` | 12 | 853.409434638 | 19832.754728308642 | 2752.580497107 | 77,148,160 | 2,571,276,019 |
| 4 | `core-01` | `cloud_medium_p10_w4_p3` | 4 | 972.1771821109978 | 17409.851117105878 | -- | -- | 2,571,276,027 |

The w4 report-profile collection additionally recorded an aggregate
process-tree peak RSS of 978,272,256 bytes across six observed processes.
That aggregate measurement is not interchangeable with the benchmark's
main-process-only `peak_rss_bytes` field shown for w8/w12/w16.

## Selection decision

The preregistered rule selects the fastest configuration directly when it is
at least 10% faster than the runner-up. Eight workers finished approximately
12.8% faster than the runner-up, 16 workers. Therefore:

- the cloud production worker count is **8**;
- the choice is frozen for the next full-M0 stage;
- no same-host tie-break is needed;
- no further cloud medium scaling run is planned.

The ranking is w8, w16, w12, w4 by wall time.

## Cost context

The observed fixed cost remains approximately 2.76802 CNY per VM-hour (about
66.43 CNY per VM-day). A 1,000 CNY budget is about 361.3 VM-hours; the
theoretical 24-hour ceiling is 15 such VMs, while the current practical fleet
is six.

## Scientific equivalence

The worker count changed runtime and resource behavior, not the accepted
scientific output. Every worker count produced identical byte sizes and
SHA-256 values for all six canonical scientific artifacts:

| File | Bytes | SHA-256 |
|---|---:|---|
| `analyses.jsonl` | 1,036,066,517 | `44fd8e5dda79db1ca8a79751ba13953c885755eed1e1ba6f6eabaa22e83b9b69` |
| `boundary_posteriors.jsonl` | 442,296,701 | `3b05630c3d86bb5d8a14b752276a72c274230bae1a9d4a1fd48953534c48af3d` |
| `iteration_metrics.json` | 1,504 | `c53235006acb9fc475e2cc972c168cb6490ae1e2132b99a62d4f933aa2cfc24a` |
| `latent_lexicon.tsv` | 323,005,526 | `3387d0219c6c076446ab8519f2a66b60504253b4e800be3ea931feb20c723d7b` |
| `rule_usage.tsv` | 27,993 | `2cc99a3c418f536142bbf352dd9e77b8a01dae960c506ef13068c3398d2321a7` |
| `summary.json` | 1,121 | `85d71e88c98ea1cde6f76057d79688c83807d09a5941b08a62779643b7300605` |

The small differences in aggregate benchmark `artifact_bytes` are not
scientific mismatches. That aggregate includes runtime/benchmark metadata
outside the six canonical artifacts; the canonical artifact bytes and hashes
are identical.

## Scaling interpretation

Moving from 4 to 8 workers produced a substantial wall-time and throughput
improvement. Moving from 8 to 12 or 16 workers produced negative scaling, and
12/16 form a practical plateau. The selected w8 run also consumed fewer total
CPU seconds than either w12 or w16. These observations establish the measured
host-class result without asserting a hardware-level cause.

## Next scientific execution gate

Four full-M0 replicas are prepared at the frozen 8-worker setting. They are
assignments only; no full-M0 run has started.

| Machine | Replica | Workers | State |
|---|---|---:|---|
| `core-01` | `rep01` | 8 | PREPARED |
| `core-02` | `rep02` | 8 | PREPARED |
| `core-03` | `rep03` | 8 | PREPARED |
| `core-04` | `rep04` | 8 | PREPARED |

`core-05` and `core-06` remain unassigned READY/STANDBY capacity.

The replica stage is intended to produce the production scientific result,
provide failure insurance, measure cross-host runtime variance, and verify
deterministic reproducibility across hosts. Launch remains a separate,
explicitly user-operated gate.

Machine/run records and planned replica identities are in
`configs/cloud/experiment_registry.toml`. Real addresses and SSH identity
paths remain only in the ignored `.sktlm-bridge.toml`. Exact launch,
monitor, and audit commands are prepared in `full_m0_launch_plan.md`.

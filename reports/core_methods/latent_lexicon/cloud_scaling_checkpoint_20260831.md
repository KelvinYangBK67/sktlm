# Cloud P10 scaling checkpoint — 2026-08-31

This is the authoritative tracked status page for the current cloud
medium-scaling gate. Operational instructions remain in
`cloud_deployment_ubuntu22.md`; local 4-vs-8 evidence remains in
`medium_scaling_p10.md`. Pending runs below are not results.

## Fixed scientific condition

| Item | Authoritative value |
|---|---:|
| frozen corpus | GRETIL M₀, 240 documents |
| freeze ID | `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40` |
| representations | 1,440 |
| external-sandhi rules | 1,218 |
| script / spacing | IAST / `surface_word` |
| inference | exact |
| lexical alpha | 0.1 |
| complexity lambda / tau | 0.5 / 1.0 |
| whitespace penalty | 8.0 |
| passes | 3 |

## COMPLETED

### Local medium P10

| Host | Workers | Wall seconds | Throughput | Decision |
|---|---:|---:|---:|---|
| local Windows host | 4 | 1,216.915 | 13,908.50 chars/s | local sweet spot |
| local Windows host | 8 | 1,526.624 | — | negative scaling |

The local conclusion is host-specific and is not transferred to the cloud
fleet.

### Cloud medium P10 reference

| Machine | Run | Workers | Wall seconds | Throughput | Artifact bytes |
|---|---|---:|---:|---:|---:|
| `core-01` / `sktlm-m0-core-01` | `cloud_medium_p10_w4_p3` | 4 | 972.1771821109978 | 17409.851117105878 chars/s | 2,571,276,027 |

The report-profile collection at
`artifacts/cloud_collected/cloud_medium_p10_w4_p3/` is ignored runtime data.
Its remote audit reports three completed passes, completed inspection, zero
overflow, no residue, `PRAGMA quick_check = ok`, and 1,888,526 rows in each
training/inspection lexical table. Provenance commit is
`fbd0a499701d6a13dcbf8374d5b5ce3a357a7b04`. The process-tree wrapper measured
978,272,256 bytes peak RSS across six observed processes; this aggregate value
supersedes main-process-only RSS for capacity planning.

Remote-audited canonical scientific identities are:

| File | Bytes | SHA-256 |
|---|---:|---|
| `iteration_metrics.json` | 1,504 | `c53235006acb9fc475e2cc972c168cb6490ae1e2132b99a62d4f933aa2cfc24a` |
| `summary.json` | 1,121 | `85d71e88c98ea1cde6f76057d79688c83807d09a5941b08a62779643b7300605` |
| `analyses.jsonl` | 1,036,066,517 | `44fd8e5dda79db1ca8a79751ba13953c885755eed1e1ba6f6eabaa22e83b9b69` |
| `boundary_posteriors.jsonl` | 442,296,701 | `3b05630c3d86bb5d8a14b752276a72c274230bae1a9d4a1fd48953534c48af3d` |
| `latent_lexicon.tsv` | 323,005,526 | `3387d0219c6c076446ab8519f2a66b60504253b4e800be3ea931feb20c723d7b` |
| `rule_usage.tsv` | 27,993 | `2cc99a3c418f536142bbf352dd9e77b8a01dae960c506ef13068c3398d2321a7` |

## RUNNING

| Machine | Run | Metrics ID | Workers | State |
|---|---|---|---:|---|
| `core-02` | `cloud_medium_p10_w8_p3` | `medium_p10_w8_p3` | 8 | RUNNING |
| `core-03` | `cloud_medium_p10_w12_p3` | `medium_p10_w12_p3` | 12 | RUNNING |
| `core-04` | `cloud_medium_p10_w16_p3` | `medium_p10_w16_p3` | 16 | RUNNING |

No runtime, completion, audit, or scientific-equivalence claim is made for
these runs. `core-05` and `core-06` are standby machines. Logical machine IDs
are stable; the current roles are not permanent.

## Cost and selection gate

The observed fixed cost is approximately 2.76802 CNY per VM-hour (about 66.43
CNY per VM-day). A 1,000 CNY budget is about 361.3 VM-hours; the theoretical
24-hour ceiling is 15 such VMs, while the current practical fleet is six.

After all four medium runs complete:

- at least 10% between winner and runner-up: select the winner directly;
- 5–10%: inspect aggregate RSS, CPU, and I/O;
- below 5%: treat as a plateau and prefer fewer workers;
- if host variation could reverse the top two: run one same-host tie-break.

## PLANNED

Medium worker scaling → consolidated comparison → worker selection → multiple
full-M₀ replicas using that worker count → host-runtime variance → deterministic
scientific-artifact comparison. Full M₀ remains gated and has not started.

Machine/run assignments are script-readable in
`configs/cloud/experiment_registry.toml`. Real addresses and SSH identity paths
remain only in the ignored `.sktlm-bridge.toml`.

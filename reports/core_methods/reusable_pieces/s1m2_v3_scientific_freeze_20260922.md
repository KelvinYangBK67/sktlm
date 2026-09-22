# S1M2 V3 scientific freeze

Date: 2026-09-22
Status: **SCIENTIFICALLY FROZEN**
Researcher decision: `S1M2_V3_SCIENTIFIC_SEMANTICS=FROZEN`

## Decision

The researcher accepts the qualified S1M2 V3 objective and interface. The
scientific semantics defined below are frozen before subsequent confirmatory
production evaluation. Ordinary follow-up work may improve execution only and
must preserve these semantics exactly.

This freeze is supported by bounded controlled evidence for
`noun_high_deva`, IAST `surface_word`, E000/E100, three passes, one worker,
exact inference, gamma 1.0, and rho 0.4. That scope is sufficient to freeze the
objective and its interface. It does not claim that Full M0 has succeeded,
that Sanskrit morphology has been learned generally, that cross-script or
cross-spacing invariance has been established, that S2/S3 has been completed,
or that surface-only grammar induction has been solved.

The machine-readable attestation is
`evidence/s1m2_v3_scientific_freeze_20260922.json`.

## Frozen scientific identity

The frozen model is `reusable_pieces_v3` with three scientific passes, exact
composed marginal inference, `sandhi_transformation_penalty` gamma 1.0, and
`piece_boundary_probability` rho 0.4.

For a script-neutral phonological piece form `q` and one latent
script-neutral phonological wordform host `h`:

```text
S(q,h)       = posterior expected piece usage aggregated by host wordform
C(q)         = sum_h S(q,h)
Q(q)         = sum_h S(q,h)^2
M(q)         = max_h S(q,h)                       # diagnostic only
R_cross(q)   = 0                                  if C(q)=0
R_cross(q)   = C(q) - Q(q)/C(q)                   otherwise
```

The square in Q is taken only after all repeated occurrences and derivation
paths yielding the same `(piece, host)` have been pooled. Different latent
phonological wordforms remain different hosts. Learned piece identity is the
script-neutral `PhonologicalForm` alone.

`WHOLE`, `LEFT`, `RIGHT`, and `INTERNAL` remain lattice, structural, and
diagnostic metadata. PieceRole does not enter learned identity or learned
score. Role-separated C/Q/R state remains diagnostic-only. V3 probability and
complexity use `R_cross`; `M` remains diagnostic-only.

Candidate admissibility, scorer semantics, posterior accumulation, canonical
reduction, and exact inference are part of this scientific interface.

## Qualified contract identity

The freeze binds the existing contract without modifying its bytes:

| Field | Value |
|---|---|
| Path | `configs/production/s1m2_six_cell_v3.json` |
| Contract ID | `s1m2-six-cell-v3-prefreeze-v1` |
| Contract file SHA-256 | `6a29480ba27d82ed334cdc6027f2aedab30e6fc7b3f5ebe2465ff6469b3022fa` |
| Contract canonical SHA-256 | `03c524b8978919bbfb98f65caaf75625e4cd053314c704f433ad002009b27bd2` |
| Model | `reusable_pieces_v3` |
| Passes | 3 |
| Gamma | 1.0 |
| Rho | 0.4 |

The contract retains its qualification-time status string. The separate
freeze attestation records the later researcher decision, so the freeze does
not alter the identity already bound by the forensic evidence.

Historical V1 and V2 contracts, artifacts, and interpretations retain their
original identities. The V1 Full M0 whole-form memorization failure is not
rewritten as a V3 result, and no V1/V2 state is reinterpreted as V3.

## Evidence chain

The authoritative chain is:

1. `s1m2_v3_cross_host_objective_20260921.md` defines V3 semantics and version
   isolation.
2. `s1m2_v3_prefreeze_forensic_audit_20260922.md` records the bounded
   qualification interpretation and contract closure.
3. `evidence/s1m2_v3_prefreeze_audit_20260922.json` contains exact read-only
   audit results and selection provenance. Its embedded audit payload SHA-256
   is `12b02a17fb18c04849aeb42dde880fc2cad6258dd6a9adc78d05411907be997f`.
4. `configs/experiments/s1m2_lexeme_evidence_probe_v3.yaml` records the
   qualification scope.
5. This report and its machine attestation record the researcher's final
   lifecycle decision.

The attestation binds the exact file SHA-256 for each item.

## E000/E100 interpretation

Both conditions contain 1,000 selected rows. E100 replaces 100 E000
background rows with 100 target-evidence rows; 900 source rows are shared.
This is a **controlled evidence-condition contrast**. It is not a strict
single-variable causal contrast.

Micro recovery is approximately unchanged: E000 recovers 34 of 76 evaluable
occurrences (0.447368), and E100 recovers 34 of 77 (0.441558). The unchanged
numerator does not mean the same occurrences were recovered. Among the 76
occurrences evaluable in both conditions:

| Paired transition | Count |
|---|---:|
| correct -> correct | 28 |
| correct -> wrong | 6 |
| wrong -> correct | 6 |
| wrong -> wrong | 36 |

Among 57 occurrences with piece metrics in both conditions:

| Representation transition | Count |
|---|---:|
| whole -> whole | 5 |
| multi -> whole | 41 |
| multi -> multi | 11 |
| whole -> multi | 0 |

Direct exact-form evidence strongly shifts representation toward whole-form
analyses. It does not uniformly improve recovery.

The unweighted macro-average across the ten gold wordform types is:

| Condition | Recovery | Mean pieces | Whole-form use |
|---|---:|---:|---:|
| E000 | 0.547123 | 1.838889 | 0.161111 |
| E100 | 0.454901 | 1.326250 | 0.673750 |

Wordform effects are heterogeneous. For example, `devebhyaḥ` moves from 4/4
correct to 0/4, while `devāḥ` moves from 1/16 to 5/16. The accepted
interpretation is therefore: exact target evidence strongly changes
representation toward whole-form analyses, aggregate micro recovery remains
approximately unchanged, and wordform-level recovery includes both gains and
losses.

## Numerical and posterior-tail conclusion

Read-only fail-closed validation recomputed all stored piece and
role-diagnostic C/Q/R rows under the current authoritative contract. It found
no nonfinite, negative, gross-bound, or stored-versus-recomputed failure. The
extreme `0<C<0.01` tail supplies 0.2146% of total `R_cross` in E000 and
0.2134% in E100; most reusable mass lies at higher C.

This establishes internal consistency and legality of the stored C/Q/R state.
It does not claim that occurrence-level historical posteriors were independently
reconstructed from scratch. Host aggregation semantics are jointly supported
by the implementation, reference calculation, SQLite behavior, and focused
serial/parallel equivalence tests. The evidence does not justify a posterior
cutoff, new reuse threshold, or extra penalty.

## Requalification triggers

Any of the following reopens scientific qualification:

- changing or expanding the learned host key;
- adding lemma, occurrence, derivation-path, or surface-spelling identity to
  the host key;
- adding PieceRole to learned identity or putting role-specific state into the
  scorer;
- posterior pruning that changes learned posterior mass;
- replacing exact inference with approximate inference;
- a scientific change to candidate admissibility;
- a scientific change to canonical accumulation or reduction semantics;
- changing gamma, rho, or the number of scientific passes;
- changing the `R_cross` formula, learned piece identity, or score semantics.

These changes cannot be classified as ordinary engineering optimization.

## Allowed engineering scope

The next phase is `ENGINEERING_OPTIMIZATION_SWEEP`. Permitted work includes
allocation and object-lifecycle reduction, cache and layout changes,
SQLite/storage and I/O optimization, multiprocessing and scheduling changes,
execution-bundle and topology/archive optimization, continuous/non-continuous
code-path unification, duplicate-work removal, and control-plane cleanup.

Such work requires unchanged scientific semantics and exact equivalence at the
appropriate interface. This freeze task starts none of that work and
authorizes no automatic VM, cloud, representative, stress, or Full M0 run.

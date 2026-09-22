# S1M2 V3 pre-freeze forensic audit and contract closure

Date: 2026-09-22
Status: **pre-freeze contract closure complete; pending researcher scientific freeze decision**

This audit is a read-only examination of the completed
`noun_high_deva_E000_v3_p3` and `noun_high_deva_E100_v3_p3` runs. It did not
invoke training or inference, add an experiment cell, change the objective, or
modify any run artifact. The machine-readable evidence is
`evidence/s1m2_v3_prefreeze_audit_20260922.json`; its embedded canonical payload
SHA-256 is
`12b02a17fb18c04849aeb42dde880fc2cad6258dd6a9adc78d05411907be997f`.

## Qualification identity

Both runs independently record the required identity:

- objective: `reusable_pieces_v3`;
- passes: 3;
- workers: 1;
- sandhi transformation penalty gamma: 1.0;
- piece boundary probability rho: 0.4;
- role diagnostics: enabled, diagnostic only;
- training Git commit: `9bd73b65b462284c3cd87f7daa38735664f41c1f`;
- held-out challenge SHA-256:
  `6f13a88fa49c0c05034f630cf63fb5ca7fa0ebd125c077e1f90dffc56d26ee59`.

No qualification metadata conflict was found.

## Phase A: fail-closed C/Q/R retrovalidation

Each SQLite database was opened with `mode=ro&immutable=1` and
`PRAGMA query_only=ON`. Every stored row was recomputed with the current
authoritative `cross_host_reusable_count()` implementation.

| Run | Table | Rows | Nonfinite | C < 0 | Q < 0 | C=0,Q>0 | Gross bound violation | Stored/recomputed mismatch | Max absolute / ULP discrepancy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E000 | `piece_lexicon` | 140,077 | 0 | 0 | 0 | 0 | 0 | 0 | 0 / 0 |
| E000 | `piece_role_diagnostics` | 187,204 | 0 | 0 | 0 | 0 | 0 | 0 | 0 / 0 |
| E100 | `piece_lexicon` | 142,541 | 0 | 0 | 0 | 0 | 0 | 0 | 0 / 0 |
| E100 | `piece_role_diagnostics` | 190,761 | 0 | 0 | 0 | 0 | 0 | 0 | 0 / 0 |

The combined row counts are 327,281 for E000 and 333,302 for E100. Phase A
passes without a roundoff exception or hard-gate failure.

## Phase B: posterior tail and host diversity

The audit bins all learned piece forms by raw expected count `C`. Percentages
below are fractions of the run total.

| Run | C bin | Piece types | C total | C share | R_cross total | R_cross share | Median R/C | Median effective hosts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| E000 | 0<C<0.01 | 126,820 | 36.4283 | 0.3605% | 13.4883 | 0.2146% | 0.1070 | 1.1198 |
| E000 | 0.01<=C<0.1 | 6,132 | 220.6819 | 2.1842% | 78.5118 | 1.2491% | 0.3378 | 1.5102 |
| E000 | 0.1<=C<1 | 6,229 | 3,352.9845 | 33.1861% | 1,099.6564 | 17.4953% | 0.3210 | 1.4727 |
| E000 | 1<=C<10 | 813 | 1,799.1362 | 17.8069% | 964.1917 | 15.3401% | 0.5372 | 2.1610 |
| E000 | C>=10 | 83 | 4,694.3591 | 46.4623% | 4,129.5786 | 65.7008% | 0.9292 | 14.1200 |
| E100 | 0<C<0.01 | 129,144 | 37.7950 | 0.3591% | 13.9696 | 0.2134% | 0.1009 | 1.1123 |
| E100 | 0.01<=C<0.1 | 6,167 | 224.5579 | 2.1335% | 79.0166 | 1.2069% | 0.3371 | 1.5085 |
| E100 | 0.1<=C<1 | 6,303 | 3,408.2722 | 32.3810% | 1,102.7469 | 16.8437% | 0.3194 | 1.4692 |
| E100 | 1<=C<10 | 845 | 1,982.8247 | 18.8383% | 1,063.6207 | 16.2461% | 0.5389 | 2.1688 |
| E100 | C>=10 | 82 | 4,872.0734 | 46.2882% | 4,287.5825 | 65.4899% | 0.9318 | 14.6641 |

There are no `C=0` rows. Total `(C, R_cross)` is
`(10103.589970428158, 6285.426747929442)` for E000 and
`(10525.52308683911, 6546.936238323656)` for E100. Counts below 0.1 account
for about 1.46% and 1.42% of total `R_cross`; counts at least 10 account for
65.70% and 65.49%. Thus most learned mass is not supplied by the extreme
posterior tail.

The largest effective host counts among `C>=1` are 300.463 (E000) and
301.286 (E100), both for `m`. The five largest low-count (`0<C<1`) pieces by
`R_cross` are `āna, re, tī, tṛ, vis` for E000 and `ri, sr, ve, ṣ, calajjih`
for E100. The evidence JSON records the complete top-20 lists for `R_cross`,
`R/C` with `C>=1`, effective host count with `C>=1`, and low-count
`R_cross`, including C/Q/M/R values and exact form keys.

No numerical or distributional anomaly triggers researcher review. This is a
descriptive stability statement; it does not turn `R_cross` into a
morphological truth measure.

## Phase C: exact occurrence-paired E000/E100 audit

All 80 held-out occurrences in each run have unique and identical keys over
`(target_id, sentence_index, dcs_id, dcs_occ_id, match_index)`. Among the 76
occurrences evaluable in both runs, transitions are:

| Transition | Count |
|---|---:|
| correct -> correct | 28 |
| correct -> wrong | 6 |
| wrong -> correct | 6 |
| wrong -> wrong | 36 |

One occurrence changes from E000 unscorable to E100 wrong; three remain
unscorable in both. The paired result explains why the aggregate correct
numerator is unchanged while individual outcomes move in both directions.

Among the 57 occurrences with piece metrics in both runs, representation
transitions are 5 whole-to-whole, 41 multi-to-whole, 11 multi-to-multi, and 0
whole-to-multi. E100 reduces piece count by one in 41 cases and leaves it
unchanged in 16. Across the ten gold wordform types, the unweighted macro
averages are:

| Run | Recovery | Mean pieces | Whole-form use |
|---|---:|---:|---:|
| E000 | 0.547123 | 1.838889 | 0.161111 |
| E100 | 0.454901 | 1.326250 | 0.673750 |

The evidence JSON contains all ten wordform rows, their denominators, and their
paired transition counts. In particular, `devebhyaḥ` moves from 4/4 correct
to 0/4, while `devāḥ` moves from 1/16 to 5/16. The paired evidence supports a
clear shift toward whole-form representations, but does not support a uniform
per-wordform recovery improvement.

## Phase D: exact selection provenance

Selection identity is the repository-relative source JSONL path plus its
one-based physical line number, bound to the source file SHA-256. Rows are
reconstructed by queuing target evidence before background evidence by exact
text and consuming one row per corpus line in corpus order.

| Quantity | E000 | E100 |
|---|---:|---:|
| Selected rows | 1,000 | 1,000 |
| Target rows | 0 | 100 |
| Background rows | 1,000 | 900 |
| Reconstructed selection SHA-256 | `78f3c09b...9236e` | `642c2ba6...ff00f` |

The conditions share exactly 900 source rows and 900 text rows; each has 100
condition-only source and text rows. Neither selection has duplicate text.
E100 reconstruction exactly matches its stored run selection. E000 diagnostics
used the original background JSONL (`291c2366...b9897`) rather than a stored
corpus-order selection; both carry the same 1,000 uniquely identified rows.

This is a controlled evidence-condition contrast: E100 replaces 100 E000
background rows with 100 target-evidence rows while holding `n=1000`. It is
not a strict single-variable causal contrast.

## Production contract and version isolation

The historical `configs/production/s1m2_six_cell.json` remains byte-for-byte
unchanged. The active control-plane default is now the versioned
`configs/production/s1m2_six_cell_v3.json`, which fails closed unless it
selects V3, three passes, gamma 1.0, and rho 0.4. Production jobs carry the
contract model into both the emitted trainer command and `TrainingConfig`.
Gamma is now an explicit scientific configuration field, so plans, manifests,
commands, and provenance bind it along with rho.

The control-plane validator passes with canonical contract SHA-256
`03c524b8978919bbfb98f65caaf75625e4cd053314c704f433ad002009b27bd2`.

Model, gamma, and rho already participate in the training configuration
signature. Focused tests now assert that changing any of them changes the
signature and that the production loader rejects a nonqualified value. V1 and
V2 artifacts and checkpoints are historical identities and cannot be resumed
or scored as V3.

## Host invariant for S2/S3

The learned host identity is exactly one latent script-neutral
`PhonologicalForm` wordform. Supports from different derivation paths that
yield the same wordform aggregate under one `(piece, host)` key before Q is
calculated. Different phonological wordforms remain different hosts. Piece
roles pool into the form-only learned identity; role-separated moments remain
diagnostic shadow state and never enter scoring.

Focused Tests A/B/C cover these three properties at the reference and SQLite
seams. Existing serial/parallel V3 training coverage also verifies identical
learned rows and identical role diagnostic rows for workers 1 and 2.

S2/S3 must preserve the same host key. A future representation that inserts
lemma, occurrence, surface spelling, derivation-path identity, or role into
the learned host key requires explicit requalification. Requalification is
also required if posterior pruning or approximation changes tail mass, or if
role-specific state enters the learned score.

## Researcher decision still required

The bounded V3 empirical and engineering contracts are closed. The remaining
decision is scientific: accept or reject V3 as the frozen S1M2 objective and
authorize any subsequent S2/S3 design work. This report does not declare the
objective frozen and does not authorize a Full M0 run.

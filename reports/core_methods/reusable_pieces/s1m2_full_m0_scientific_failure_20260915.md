# S1M2 reusable-pieces Full M₀ scientific failure report

Date: 2026-09-15
Repository: `KelvinYangBK67/sktlm`
Branch: `exp/s1m2-reusable-pieces`

## 1. Scope and decision

This report closes the scientific interpretation of the present
`reusable_pieces_v1` Full M₀ attempt. It does not change the implementation,
scientific configuration, production contract, artifacts, or recorded run
statuses.

The completed evidence from two independently trained Devanagari
non-continuous cells shows the same failure mode: expected-count learning
moves posterior mass steadily away from reusable multi-piece composition and
toward whole-form memorization. By Pass 3, whole-form mass is approximately
75%; final inspection raises it to 84.46–87.11%. Over the same passes,
pieces per expected lexical token approaches one and segmentation entropy
falls sharply. The final piece inventories also contain a very large
low-expected-count region.

The scientific decision is therefore:

```text
S1M2_REUSABLE_PIECES_V1=SCIENTIFIC_FAILURE
FAILURE_MODE=WHOLE_FORM_MEMORIZATION_COLLAPSE
FULL_M0_RERUN_WITH_UNCHANGED_OBJECTIVE=NOT_JUSTIFIED
NEXT_OBJECTIVE_SELECTED=NO
```

This is not a repair report. It does not select a replacement objective.

## 2. Experiment identity

The evidence was produced by a scoped four-cell Full invocation. The relevant
identity recorded in the captured provenance and run manifests is:

| Field | Value |
|---|---|
| Model | `reusable_pieces_v1` |
| Scientific/deployment Git HEAD | `5bd9bb7ce90e854b1eb896f80feafc4b15c29878` |
| Production contract SHA-256 | `c32c195901f989d7b41ab0875f31d05280a36b3462e93d73ceeb2a185c920809` |
| Final plan SHA-256 | `329b9ec674a904f15422833ffb444729e07f68fbf313b46778fc83d01b7880bd` |
| M₀ freeze ID | `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40` |
| Training passes | 3 |
| Workers | 12 |
| `piece_max_length` | 8 |

The repository HEAD at report preparation is
`e6ae3996cedc06a48020716731c55f965c13e7fb`, after the evidence-producing
deployment HEAD. Later monitoring or artifact-finalization code is not part of
the scientific identity of these runs. No rerun was performed at the later
HEAD, and this report does not reinterpret the historical artifacts through
it.

The frozen scientific universe remains six cells. The invocation considered
here executed the four currently selected cells on core-07 through core-10;
the two previously completed IAST non-continuous cells were outside this
invocation and are not used as replicated evidence for the failure claim.

## 3. Cell status at termination

| Host | Cell | Evidence state | Report-level classification |
|---|---|---|---|
| core-07 | M₀-prime / IAST / `continuous` | Pass 1 active; 0 completed passes; next document 109/240; no inspection | `MANUALLY_TERMINATED_AFTER_SCIENTIFIC_OBJECTIVE_FAILURE` |
| core-08 | M₀ / Devanagari / `continuous` | Pass 1 active; 0 completed passes; next document 109/240; no inspection | `MANUALLY_TERMINATED_AFTER_SCIENTIFIC_OBJECTIVE_FAILURE` |
| core-09 | M₀ / Devanagari / `surface_word` | 3/3 passes; 240/240 documents; inspection complete; overflow 0; subprocess return code 0 | Scientifically completed; production result `AUDIT_FAILED` |
| core-10 | M₀ / Devanagari / `legacy_joined` | 3/3 passes; 240/240 documents; inspection complete; overflow 0; subprocess return code 0 | Scientifically completed; production result `AUDIT_FAILED` |

The `MANUALLY_TERMINATED_AFTER_SCIENTIFIC_OBJECTIVE_FAILURE` text is a report
classification, not a rewrite of the stored manifests. Those manifests record
`FAILED` after the operator sent SIGTERM; the stop records show the signalled
wrapper, no matching process afterward, and safe process state. The phase
summaries record return code `-15`, while the control manifests record 143.
This is evidence of intentional termination, not a runtime crash or OOM.

Within this attempt, only core-09 and core-10 completed enough work to support
a final scientific result. Core-07 and core-08 do not have completed-pass or
final-inspection evidence and are not treated as if they did.

## 4. Quantitative failure evidence

Each pass statistic below is computed from the recorded expected-count totals:
whole-form uses, multi-piece uses, piece tokens, and segmentation entropy are
divided by expected lexical tokens. They are aggregate posterior quantities,
not counts of selected top-1 examples.

### 4.1 Devanagari surface-word (core-09)

| Pass | Whole-form mass | Multi-piece mass | Pieces / lexical token | Entropy / lexical token |
|---:|---:|---:|---:|---:|
| 1 | 26.576% | 73.424% | 2.4904 | 2.0646 |
| 2 | 50.244% | 49.756% | 1.8387 | 1.4487 |
| 3 | 76.424% | 23.576% | 1.3476 | 0.5771 |

Final inspection reports:

| Statistic | Value |
|---|---:|
| Whole-form memorization mass | 0.8711347994040385 |
| Multi-piece compositional mass | 0.12886520059584078 |
| Singleton atomization mass | 0.019293805535430815 |
| Mean segmentation entropy / expected lexical token | 0.22474596085710027 |

From Pass 1 to Pass 3, whole-form mass rises by 49.85 percentage points while
multi-piece mass falls by the same amount. Pieces per lexical token falls from
2.4904 to 1.3476, and entropy falls from 2.0646 to 0.5771. Final inspection
continues the same direction rather than reversing it.

### 4.2 Devanagari legacy-joined (core-10)

| Pass | Whole-form mass | Multi-piece mass | Pieces / lexical token | Entropy / lexical token |
|---:|---:|---:|---:|---:|
| 1 | 24.541% | 75.459% | 2.6284 | 2.2549 |
| 2 | 49.524% | 50.476% | 1.8968 | 1.5432 |
| 3 | 74.851% | 25.149% | 1.3921 | 0.6120 |

Final inspection reports:

| Statistic | Value |
|---|---:|
| Whole-form memorization mass | 0.8446105156101084 |
| Multi-piece compositional mass | 0.1553894843900024 |
| Singleton atomization mass | 0.01813775691480871 |
| Mean segmentation entropy / expected lexical token | 0.24594484179058104 |

From Pass 1 to Pass 3, whole-form mass rises by 50.31 percentage points.
Pieces per lexical token falls from 2.6284 to 1.3921, and entropy falls from
2.2549 to 0.6120. Final inspection again continues the same direction.

### 4.3 Cross-condition replication

The two cells are separate Full M₀ trainings under different non-continuous
spacing conditions. Their trajectories align at every observed stage:

| Stage | Surface-word whole-form mass | Legacy-joined whole-form mass |
|---|---:|---:|
| Pass 1 | 26.576% | 24.541% |
| Pass 2 | 50.244% | 49.524% |
| Pass 3 | 76.424% | 74.851% |
| Final inspection | 87.113% | 84.461% |

The supporting variables also agree: multi-piece mass decreases, pieces per
lexical token moves toward one, and segmentation entropy decreases. This
replication is sufficient to reject an explanation based on one sentence,
one sampled analysis, or one of the two spacing conditions. Both completed
cells are Devanagari, so it does not establish cross-script equivalence.

## 5. Qualitative inspection evidence

Two operator-preserved inspection excerpts illustrate the same behavior. In
the first, only `om` is internally divided, while the remaining lexical forms
are retained as whole pieces:

```text
SURFACE:
ॐ नमो ऽथर्ववेदाय नमः

LATENT:
om | namo | tharvavedāya | namaḥ

PIECES:
o·m | namo | tharvavedāya | namaḥ
```

In the second, even the long middle lexical form remains a single piece:

```text
SURFACE:
तद् अभ्यस्राम्यद् अभ्यतपत् समतपत्

LATENT:
tat | abhyasrāmyadabhyatapat | samatapat

PIECES:
tat | abhyasrāmyadabhyatapat | samatapat
```

These examples are illustrations, not the basis of the decision. The primary
evidence is the pass-by-pass expected-count trajectory, final posterior
aggregates, and independently replicated inventory diagnostics. The captured
`inspection_report.md` files additionally preserve aggregate posterior values,
highest-frequency pieces, and bounded qualitative tables, but the two excerpts
above are not present verbatim in the compact extracted reports; they remain
operator-provided excerpts rather than independently file-addressable rows in
this capture.

## 6. Piece-inventory diagnostics

The repository schema distinguishes the reported counts:

- `piece_types` is the row count of `inspection_piece_counts`. Rows are added
  only for pieces with positive final-inspection expected count. It is an
  observed/materialized posterior inventory, not the number of all legal
  candidates and not automatically an active parameter vocabulary.
- `active_piece_types` is the row count of the final `piece_lexicon`, the
  persistent active parameter state. All legal pieces remain scoreable; the
  active table is not the full legal support.
- `low_support_piece_types` counts final-inspection rows whose expected count
  is at most the configured `low_support_threshold`, here 1.0. Despite its
  field name, this particular threshold is on expected count.
- `piece_types_by_occurrence_support` separately groups the same positive
  final-inspection rows by occurrence support. Occurrence support counts
  distinct observed lexical-form occurrence identities with positive joint
  posterior support, not expected-token multiplicity.

| Cell | `active_piece_types` | `piece_types` | `low_support_piece_types` | Low-support share |
|---|---:|---:|---:|---:|
| core-09 surface-word | 22,044,858 | 42,505,659 | 42,103,710 | 99.054% |
| core-10 legacy-joined | 25,787,328 | 51,382,241 | 50,917,831 | 99.096% |

The occurrence-support distributions are:

| Cell | 1 | 2–4 | 5–9 | 10–99 | 100+ |
|---|---:|---:|---:|---:|---:|
| core-09 | 20,460,801 | 10,052,402 | 4,034,949 | 6,500,570 | 1,456,937 |
| core-10 | 25,594,913 | 10,929,912 | 4,642,125 | 8,184,135 | 2,031,156 |

Thus the overwhelming majority of positive expected-count inspection types
lies in the low-expected-count region, and tens of millions of types have
occurrence support no greater than four. In conjunction with the posterior
trajectory, this is evidence of broad low-support proliferation rather than a
compact reusable inventory. It is not a claim that the active vocabulary is
42–51 million types, and inventory size alone does not identify the causal
component of the objective.

## 7. Failure interpretation

The present method makes every nonempty contiguous piece through
`piece_max_length=8` legal and also preserves an initial whole-form edge when
the lexical form is longer than that limit. The production composed inference
path explicitly permits only that initial whole-form edge to exceed the bound.
Long whole pieces in inspection are therefore legal model outcomes, not a
display error or an accidental violation of `piece_max_length`.

The observed progression is consistent with a self-reinforcing expected-count
learning trajectory: increasing whole-form mass is followed across passes by
still higher whole-form mass, fewer expected pieces per lexical token, and
lower segmentation entropy. The current scoring and complexity structure did
not prevent that trajectory. The evidence supports calling the resulting
behavior an objective collapse toward whole-form memorization.

This report does not isolate the whole-form edge, any single hyperparameter,
or any one scoring term as a proven sole cause. The design point requiring
reconsideration is the interaction between the legal whole-form path,
expected-count feedback, and the complete current objective.

## 8. Continuous-cell termination rationale

Core-07 and core-08 shared the same `reusable_pieces_v1` objective as the two
completed cells. When stopped, both had processed 109 documents in active
Pass 1, had completed zero passes, and had not begun inspection. Their
checkpoint metrics cannot support a final whole-form-collapse estimate.

Continuing them would have spent Full M₀ resources after two independent
non-continuous cells had already reproduced the same strong scientific failure
trajectory. The operator therefore terminated both wrappers with SIGTERM.
The captured stop and safety records show successful termination and no
remaining S1M2 processes.

This was a budget and scientific-governance decision, not evidence that the
continuous cells themselves reached 84–87% whole-form mass. It was also not
an OOM, runtime crash, or infrastructure failure. Any scientific claim about
the completed behavior of either continuous cell remains unavailable.

## 9. Separation from the SQLite artifact-audit defect

Two independent failures must not be conflated.

### A. Scientific failure

The completed posterior and training histories demonstrate whole-form
memorization collapse. These quantities were produced before the final
artifact audit and remain the core evidence of this report.

### B. Control-plane/artifact-finalization defect

The core-09 and core-10 audit files both have `valid=false`, and each records
one failure only:

```text
temporary/SQLite sidecar residue: ['learner.sqlite-shm', 'learner.sqlite-wal']
```

Their control manifests therefore retain `result_status=AUDIT_FAILED`. This
report does not change that status. At the same time, the audit completion
records show 3/3 passes, 240 documents, completed inspection, and zero
overflow; the aggregate process summaries show four successful scientific
phases and return code 0. The sidecar residue is an artifact-finalization
defect, not evidence that the reported posterior summaries are a scientific
failure to compute.

The operator separately reports `PRAGMA quick_check = ok` and a successful
`wal_checkpoint(TRUNCATE)`. Those manual checks are not stored as a dedicated
machine-readable file in the local capture inspected for this report, so they
are recorded here as operator evidence, not as an independently reproducible
capture artifact. No SQLite database was opened or scanned for this report.

The current repository contains later artifact-finalization work, but these
historical runs were not rerun under it. No claim is made here that the stored
`AUDIT_FAILED` results have become `PASS` or that the operational defect has
been production-validated by a new Full run.

## 10. Scientific conclusions

The evidence supports the following formal conclusions:

1. In Full M₀ Devanagari `surface_word`, `reusable_pieces_v1` moves from
   26.576% whole-form mass in Pass 1 to 76.424% in Pass 3 and 87.113% in final
   inspection.
2. In independently trained Full M₀ Devanagari `legacy_joined`, it moves from
   24.541% to 74.851% and then 84.461%.
3. In both cells, the decline in multi-piece mass, pieces per lexical token,
   and segmentation entropy supports the same interpretation.
4. The final observed/materialized piece inventories are dominated by rows
   with expected count at most 1.0 and contain broad low-occurrence-support
   tails; this is consistent with low-support proliferation rather than the
   intended compact reuse behavior.
5. The current objective therefore fails its reusable-composition purpose in
   both completed non-continuous spacing conditions.
6. Re-running Full M₀ with the unchanged objective is not scientifically
   justified. A redesigned objective must first pass smaller preflight gates.
7. The SQLite sidecar audit failure is operationally real but logically
   independent of the scientific objective failure.

## 11. Claims explicitly not made

This report does not claim that:

- either continuous cell completed or reached the final collapse percentages;
- IAST and Devanagari are scientifically equivalent under S1M2;
- all six frozen cells independently reproduce the failure;
- every one of the 42–51 million `piece_types` rows is an active vocabulary
  parameter or a distinct legal candidate generated at once;
- one qualitative example or top-1 rendering proves the failure;
- the whole-form edge alone is the proven causal mechanism;
- a particular replacement objective, penalty, prior, or hyperparameter has
  been selected;
- the SQLite sidecar issue invalidates the completed posterior summaries;
- the existing `AUDIT_FAILED` manifests have been repaired or converted to
  `PASS`.

## 12. Required gate before any rerun

Before another Full M₀ run, a replacement scientific objective must satisfy a
pre-registered, bounded gate that includes at least:

1. **Synthetic identifiable sanity:** on data with known reusable structure,
   multi-pass learning must recover the identifiable reuse signal rather than
   prefer whole-form memorization.
2. **Small real-corpus multi-pass learning direction:** pass-by-pass posterior
   diagnostics must rule out the monotone 25% → 50% → 75% whole-form trajectory
   observed here.
3. **Held-out reuse/compositionality:** reusable pieces must provide evidence
   on held-out forms or occurrences rather than only fitting training forms.
4. **Bounded qualitative inspection:** a predeclared sample must be inspected
   together with aggregate posterior and inventory diagnostics, so favorable
   or unfavorable top-1 examples cannot substitute for the gate.

The acceptance thresholds and replacement objective require a separate
scientific design decision. This report neither defines nor implements them.

## 13. Evidence inventory and gaps

All local failure evidence used here is under:

`artifacts/s1m2_failure_capture/20260915T183343/`

The following exact roots abbreviate the long paths in the inventory:

```text
C07_RUN=core-07/evidence/artifacts/latent_benchmarks/s1m2_full_m0_prime_iast_continuous_full_p3
C07_METRICS=core-07/evidence/artifacts/cloud_metrics/full_m0_prime_iast_continuous_full_p3
C08_RUN=core-08/evidence/artifacts/latent_benchmarks/s1m2_full_m0_devanagari_continuous_full_p3
C08_METRICS=core-08/evidence/artifacts/cloud_metrics/full_m0_devanagari_continuous_full_p3
C09_RUN=core-09/evidence/artifacts/latent_benchmarks/s1m2_full_m0_devanagari_surface_word_full_p3
C09_METRICS=core-09/evidence/artifacts/cloud_metrics/full_m0_devanagari_surface_word_full_p3
C10_RUN=core-10/evidence/artifacts/latent_benchmarks/s1m2_full_m0_devanagari_legacy_joined_full_p3
C10_METRICS=core-10/evidence/artifacts/cloud_metrics/full_m0_devanagari_legacy_joined_full_p3
```

| Evidence | Purpose |
|---|---|
| `capture_summary.json` | Capture completeness and per-host safety state |
| `core-07/stop_stdout.json`, `core-08/stop_stdout.json` | Explicit SIGTERM and no matching process afterward |
| `core-07/safety_stdout.json`, `core-08/safety_stdout.json` | No active S1M2 process after stop |
| `C07_RUN/checkpoint.json`, `C08_RUN/checkpoint.json` | Partial Pass 1 boundary: 109 documents, zero completed passes |
| `C07_RUN/config.json`, `C08_RUN/config.json` | Exact model, representation, workers, and piece settings |
| `C07_RUN/provenance.json`, `C08_RUN/provenance.json` | Deployment HEAD and frozen-input identity |
| `C07_METRICS/run_manifest.json`, `C08_METRICS/run_manifest.json` | Intentional signal represented as failed execution return |
| `C09_RUN/checkpoint.json`, `C10_RUN/checkpoint.json` | Three exact pass histories and completion boundary |
| `C09_RUN/iteration_metrics.json`, `C10_RUN/iteration_metrics.json` | Pass-level expected-count metrics |
| `C09_RUN/summary.json`, `C10_RUN/summary.json` | Final posterior and piece-inventory diagnostics |
| `C09_RUN/inspection_report.md`, `C10_RUN/inspection_report.md` | Bounded generated inspection summaries |
| `C09_RUN/audit.json`, `C10_RUN/audit.json` | Exact sidecar-residue failure and scientific completion fields |
| `C09_METRICS/process_tree_summary.json`, `C10_METRICS/process_tree_summary.json` | Four phases and overall return code 0 |
| `C09_METRICS/run_manifest.json`, `C10_METRICS/run_manifest.json` | Plan/contract/Git identity and retained `AUDIT_FAILED` status |
| `src/sktlm/pieces/lattice.py` | Legal long initial whole-form edge in reference support |
| `src/sktlm/pieces/composed.py` | Same long whole-form support in production composed inference |
| `src/sktlm/latent/store.py` | Formal definitions of active, inspection, low-support, and occurrence-support diagnostics |
| `src/sktlm/latent/training.py` | Pass/final posterior aggregation and generated report semantics |

The following evidence gaps remain and limit the claims above:

- `capture_summary.json` records `archive_valid=false`, `collect_rc=1`, and
  `local_evidence_ok=false` for all four hosts. The extracted tree nevertheless
  contains the compact files cited above, but the capture as a whole did not
  pass its own completeness gate. This report does not promote it to a valid
  complete archive.
- Core-07 and core-08 have only partial Pass 1 evidence; no completed-pass or
  inspection summaries exist locally.
- The two qualitative excerpts quoted in Section 5 were supplied by the
  operator and are not present verbatim in the extracted compact
  `inspection_report.md`.
- The reported manual SQLite `quick_check` and WAL checkpoint outcome has no
  dedicated file in this capture.
- Large scientific rows referenced by the audit manifests were not rescanned,
  rehashed, or extracted for this documentation task. The report relies on
  existing compact summaries and recorded artifact identities.

These gaps prevent broader continuous-cell, cross-script, archive-completeness,
or repaired-audit claims. They do not erase the independently completed
core-09/core-10 pass histories and final posterior summaries on which the
bounded scientific failure conclusion rests.

## Final status

```text
SCIENTIFIC_FAILURE=WHOLE_FORM_MEMORIZATION_COLLAPSE
COMPLETED_FAILURE_EVIDENCE_CELLS=2
COMPLETED_FAILURE_EVIDENCE_SCOPE=DEVANAGARI_SURFACE_WORD_AND_LEGACY_JOINED
CONTINUOUS_CELLS=MANUALLY_TERMINATED_AFTER_SCIENTIFIC_OBJECTIVE_FAILURE
CONTINUOUS_FINAL_SCIENTIFIC_RESULT=NOT_AVAILABLE
CORE09_CORE10_CONTROL_STATUS=AUDIT_FAILED
AUDIT_FAILURE=SQLITE_WAL_SHM_SIDECAR_RESIDUE
AUDIT_FAILURE_IS_SCIENTIFIC_FAILURE=NO
CAPTURE_COMPLETENESS_GATE=FAIL
OBJECTIVE_REDESIGN_REQUIRED=YES
REPLACEMENT_OBJECTIVE_SELECTED=NO
FULL_M0_RERUN_AUTHORIZED=NO
```

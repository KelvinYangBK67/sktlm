# PROJECT_STATE.md

This file records durable shared project state. It is not a task prompt.

## Frozen M0

- Commit: `dbff6836eb35ecb1933653443ca793b1ab890c63`
- Annotated tag: `m0` (unchanged)
- Freeze ID: `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`
- Canonical root: `data/canonical/gretil_iast`
- Canonical manifest: `data/manifests/canonical_corpus.csv`
- Representation manifest: `data/manifests/representations.csv`
- Documents: 240; representation files: 1,440

The six frozen observation trees remain immutable: IAST and Devanagari under
`surface_word`, `legacy_joined`, and `continuous`. Frozen IAST `continuous`
remains historical data but is retired from experiments; this decision does not
regenerate, repair, or delete M0.

## Branch division

- `exp/m0-core-methods`: latent/sandhi core-method line.
- `exp/m0-baseline-validation`: baseline production and validation line.

The baseline line does not import, copy, merge, or modify `src/sktlm/latent/`.

## Historical and production baseline matrices

`configs/experiments/baselines/m0_matrix.yaml` is manifest version
`m0-baselines-v2`:

- historical design: 22 cells;
- valid production: 18 cells;
- retired: BPE, Unigram, Unicode code point, and Surface-lattice under IAST
  `continuous` (4 cells), all carrying decision
  `iast-continuous-representation-validity-v1` and one reason.

Valid counts are BPE 5, Unigram 5, Unicode code point 5, Akṣara-safe BPE 1
(Devanagari `continuous`), and Surface-lattice 2 (IAST `surface_word` and
`legacy_joined`). Runner, generic experiment/controlled LM gates, production
queue, TransLIST adapter, and formal aggregator reject IAST `continuous`.

The interrupted external S1M1 diagnostic facts are recorded without invented
timestamps in `reports/baselines/iast_continuous_retirement.md`: Pass 1 and Pass
2 completed; Pass 3 stopped at document 86. No tracked run artifact exists on
this branch and it was not resumed, deleted, or rewritten.

## Pre-cloud production implementation

- `a30741c`: versioned 22/18/4 manifest and retirement gates.
- `63fa334`: CI, explicit NumPy dependency, deterministic environment capture,
  and shared-infrastructure reconciliation.
- `1527116`: unknown semantics, script-scoped diagnostics, and explicit
  SentencePiece whitespace contracts.
- `4008404`: bounded-memory `m0-common-downstream-lm-v1` with common BPC/BPB/
  canonical-unit normalization and separate Surface-lattice intrinsic metrics.
- `d78829d`: diagnostic/production execution gates, full artifact completion
  hashes/provenance, and fail-closed 18-cell aggregation.
- `e79c5e1`: independent TransLIST adapter and first-cell audit classifier.

Formal production uses fresh tokenizer and LM initialization per cell, frozen
train/test membership, a fixed tiny Transformer/AdamW budget, deterministic
buffered training order, segment-contained context, and each-target-once
autoregressive scoring. Artifacts record config, commit, freeze/manifests, data
and tokenizer fingerprints, environment and deterministic requirements freeze,
training instance, runtime, peak RSS, unknown behavior, and completion hashes.

Formal aggregation requires exactly 18 valid production bundles at one commit,
seed, freeze, manifest identity, and environment. It rejects bounded, retired,
missing, duplicate, extra, wrong-seed, tampered, incompletely hashed, or
non-independent bundles. Comparison structure has no continuous script pair.

TransLIST is not a nineteenth cell. Its executable JSONL adapter, split
fingerprint, comparable segmentation/desandhi metrics, provenance, and isolated
artifact layout are implemented; external model deployment remains optional
and non-blocking.

## Verified local state (2026-09-02)

- Full suite: 366 passed.
- Frozen canonical: 240 files, exact freeze ID, zero invalid characters and
  apostrophes.
- Frozen representations: 1,440 files, exact freeze ID.
- Plan/queue: 22 historical, 18 valid, 4 retired, 18 non-launching jobs, zero
  retired jobs.
- Environment capture: repeated `environment.json` and
  `requirements-freeze.txt` were byte-identical.
- Valid-cell smoke: all 18 cells completed tokenizer diagnostics and one CPU
  downstream step with finite metrics and completion manifests under `/tmp`;
  first 15 used at most 5,000 train/3 test segments, and the shorter-token
  Akṣara/Surface-lattice cells used at most 50,000 train/3 test segments.
- Explicit retired gate passed without launching an experiment.
- No IAST-continuous tokenizer, LM, smoke, or production run was launched.
- No formal full-corpus production was launched.

The relocated local `.venv` activation script still points at its old path and
its installed packages lack newly declared NumPy. Tests were run with the
embedded Python framework paths explicitly set and therefore retain one NumPy
warning plus existing Torch nested-tensor warnings. A production host must
create a fresh environment from declared dependencies rather than reuse this
local venv.

## Full-M0 baseline pre-production closure (2026-09-07)

`configs/experiments/baselines/m0_matrix.yaml` remains the historical
`m0-baselines-v2` 22/18/4 contract. Current production is separately declared
by `configs/experiments/baselines/full_m0_matrix.yaml` as
`full-m0-baselines-v1`:

- historical M0 design: 22 cells;
- original M0 IAST-continuous cells still retired: 4;
- unchanged valid M0 production cells: 18;
- explicit M0-prime corrected-continuous replacements: 4;
- runnable full-M0 cells: 22.

The M0-prime read-only consumer pins derivation
`m0-prime-iast-continuous-v1` and manifest SHA-256
`3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`.
It validates the formal manifest, frozen canonical/source identity, all 240
document IDs/splits/order, output membership/paths/sizes/hashes, and exposes
only `M0-prime/iast_m0_prime/continuous`. Together with five valid M0
conditions, the production catalog is exactly 6 x 240 = 1,440 files. The
consumer and baseline adapter import no latent implementation.

M0-prime tokenizer inputs carry
`m0-prime-tokenizer-compatibility-v1` in their fingerprints. BPE, Unigram,
Unicode code point, and Surface-lattice passed bounded controlled-fixture
round-trip/unknown tests for `ē`, `ō`, and modifier `ʰ`. Surface-lattice uses
the separately versioned `iast_m0_prime_surface_lattice_v1` contract rather
than broadening ordinary `iast_surface_lattice_v1` silently.

Runner, non-launching queue, first-cell audit, and fail-closed aggregate accept
both historical and full-M0 configuration explicitly. Full-M0 artifacts record
substrate and per-cell observation-manifest identity. The aggregate requires
exactly 22 complete formal bundles, independently initialized training IDs,
one commit/seed/environment/downstream contract, and the correct M0 or
M0-prime manifest per cell; it rejects original IAST-continuous, bounded,
missing, extra, duplicate, tampered, or mismatched bundles.

The experiment-neutral shared-analysis protocol supports AVAILABLE and N/A
states, declared scalar comparisons, evidence/provenance passthrough, and
atomic non-overwriting JSON/TSV/Markdown publication. Its baseline adapter
first invokes native full-M0 aggregation. The versioned comparison manifest
expands to 60 predeclared script, spacing, descriptive, and method comparisons;
the eight M0 ordinary-IAST versus M0-prime-continuous comparisons are explicitly
not pure spacing controls.

Cloud deployment now uses a generic contract-driven bridge plus thin baseline
audit/input adapters. The generic layer owns clean/exact Git checks, isolated
SSH arguments, mount and rsync path guards, resumable identity markers,
redacted receipts, remote audit, downloaded/remote hash comparison, collection
profiles, and host assignments. `reports/baselines/full_m0_vm_runbook.md` is
the non-executed Stage 0-4 procedure.

Local verification on 2026-09-07:

- the fetched baseline/S1M1/main remote SHAs still matched the audited values
  `5d1d595`, `3ed1841`, and `bf3396e` before this closure;
- frozen canonical validation passed at 240 documents, exact freeze ID, zero
  invalid characters, and zero invalid apostrophes;
- frozen representation validation passed;
- the full-M0 plan is 22/18/4 and the queue printed 22 jobs with
  `launches_jobs=false` and none of the four original IAST-continuous IDs;
- `pip check` passed in the available local environment;
- the complete repository suite passed: 401 tests, with four pre-existing
  Torch nested-tensor warnings;
- the formal M0-prime payload is not present locally, so formal
  `--check-inputs` correctly fails at the missing pinned manifest;
- no VM, formal full-corpus cell, or external TransLIST run was launched;
- frozen M0, its six representation trees/manifests/tag, the sandhi rule table,
  `notes/**`, and `src/sktlm/latent/**` were not modified.

# CURRENT_TASK.md

## Current status

Branch: 'exp/s1m1-final-reduction'.

Parent checkpoint:
'4bacb038eb00c479dd6913e63ec1543a1b21e0e6'
('exp/s1m1-core-methods').

The S1M1 post-hoc archival/descriptive reducer is complete on this dedicated
branch. This branch must remain separate from 'exp/s1m2-reusable-pieces'; do not
merge it into S1M2 merely to share analysis infrastructure.

The frozen preregistered gate remains historically and scientifically
separate:

    S1M1 frozen preregistered gate
    -> S1M1 post-hoc archival reduction

The archive does not modify or reinterpret gate pass/fail criteria.

## Implemented

'src/sktlm/analysis/s1m1_archival.py' provides a local-only, read-only,
fail-closed, bounded reducer over the exact six-cell gate manifest:

- audited source retention identities and row counts;
- pass dynamics and signed absolute/relative changes;
- lexical mass, diversity, exact discrete length, and reuse summaries;
- ambiguity and explicit bounded-top-k labels;
- exact boundary expectations/entropy/confidence/cue summaries;
- exact global rule distribution plus labelled top-k segment diagnostics;
- candidate scaling, bounded heavy-tail estimates, document and length strata;
- runtime/resource/counter/cache/SQLite and throughput evidence;
- bounded cross-cell head overlap, weighted distance, rank, and MinHash support;
- deterministic bounded evidence reservoirs with stable source IDs.

'scripts/analysis/reduce_s1m1_archival.py' refuses an existing output directory
before scanning, validates every collection through the existing six-cell
audit contract, and atomically writes the compact archive.

The frozen files
'reports/core_methods/latent_lexicon/post_gate_analysis_protocol.md' and
'scripts/analysis/aggregate_six_representation.py' are unchanged.

## Validation

Completed locally without real-artifact scanning:

    python -m py_compile \
      src/sktlm/analysis/s1m1_archival.py \
      scripts/analysis/reduce_s1m1_archival.py

    python -m pytest tests/analysis/test_s1m1_archival.py -q

Focused result: 4 passed.

The full repository suite also passed:

    python -m pytest -q

Full result: 546 passed, 4 warnings in 48.30 seconds. The warnings are the
existing PyTorch nested-tensor and SentencePiece/SWIG deprecation warnings.

## Human-only eventual archive command

Only after all six completed/audited collections and the exact gate manifest
are locally available:

    python scripts/analysis/reduce_s1m1_archival.py \
      --manifest <completed-six-cell-gate-manifest.json> \
      --output-dir <new-empty-archive-directory>

The output directory must not already exist. This command may scan and hash
large artifacts for longer than five minutes, so it was not launched by this
implementation task.

## Absolute boundary

Do not contact a VM, run bridge/SSH/SCP/rsync, poll a remote job, collect
artifacts, mutate the experiment registry, scan the real large collections
automatically, or overwrite any source/output directory.

## Next repository action

This branch should be committed and pushed as the S1M1 archival-reduction
line. S1M2-P1 continues independently from
'f95bc5f1bb92ce4beb899b13fa5a83070852d734' on
'exp/s1m2-reusable-pieces'. Do not transplant these Task A files onto that
branch.

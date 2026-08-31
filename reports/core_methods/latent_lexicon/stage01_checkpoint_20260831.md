# Stage 01 core-method checkpoint — 2026-08-31

This report captures the durable state of the Stage 01 latent-lexicon/core-method line before cloud deployment and the first successful full-M₀ production run. It deliberately promotes conclusions out of gitignored `artifacts/` into tracked documentation.

## Scope and frozen scientific contract

The current formal method is script-neutral latent lexical induction under a fixed external-sandhi grammar, with corpus-wide lexical reuse and exact marginalization over legal analyses.

The first production condition is frozen as:

- corpus: M₀;
- observation: IAST + `surface_word`;
- documents: 240;
- characters: 57,588,079;
- freeze ID: `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`;
- fixed external-sandhi inventory: 1218 rules;
- lexical alpha: 0.1;
- complexity lambda: 0.5;
- complexity tau: 1.0;
- ignored-whitespace penalty: 8.0;
- exact inference; no approximate pruning/beam substitution for the production claim.

The current latent target is lexical word-form identity rather than deeper morphology. Distinct phonological representations such as `om = V_O.C_M` and `oṃ = V_O.M_ANUSVARA` remain distinct; grammar-licensed ambiguity is preserved rather than collapsed by representation changes.

## Implementation checkpoint

The full-corpus-ready v1 implementation lives under `src/sktlm/latent/` on branch `exp/m0-core-methods`.

The implementation now includes:

- script-neutral phonological forms with IAST frontend;
- fixed structured external-sandhi grammar;
- exact-reconstruction candidate DAG construction;
- exact forward/backward latent inference;
- SQLite-backed lexical expected counts/probabilities;
- streaming multi-pass training and final inspection;
- bounded caches and candidate bounds;
- deterministic document-level multiprocessing;
- crash-reusable per-document shards;
- exactly-once document checkpoint semantics;
- deterministic canonical reduction preserving scientific output bytes across worker counts/optimizations when the host run completes normally.

The first attempted full M₀ run exposed an unsafe legacy resume failure class and was intentionally not resumed. Its diagnosis is preserved in `interrupted_m0_20260830_diagnostics.md`. P0 subsequently made the database checkpoint authoritative and couples document counts, metrics, and progress atomically.

## Performance optimization status

The accepted optimization sequence through P10 is documented in `performance_optimization_v1.md`.

Important accepted milestones include:

- P2: training-only exact inference;
- P3: cached immutable phonological keys;
- P4: score each distinct lexical form once per segment;
- P5: script-neutral internal-sandhi match cache;
- P6: compact SQLite count representation;
- P7: deterministic training multiprocessing with crash-reusable shards;
- P8: deterministic inspection multiprocessing;
- P9: bounded rolling worker submission with canonical reduction;
- P10: direct scalar boundary-posterior serialization.

Rejected experiments are kept out of the implementation when they failed to show stable benefit. In particular, the post-P10 internal-match-reuse experiment produced zero scientific mismatches but no reproducible speed gain and was fully reverted.

## Medium benchmark evidence

### P8, 4 workers, 3 passes + inspection

Tracked summary from the completed medium run:

- wall: 2,141.125 s (35m41s);
- normalized throughput: 7,904.94 chars/s;
- training wall: 884.096 s total;
- inspection wall: 1,185.712 s;
- artifact bytes: 2,571,478,847;
- SQLite bytes: 770,027,520;
- completed passes: 3;
- inspection complete: yes;
- overflow: 0;
- residual shards: none;
- SQLite `quick_check`: ok.

The conservative full-M₀ projection at this checkpoint was about 8.09 hours by character throughput.

### P10, 4 workers, 3 passes + inspection

The completed P10 medium run materially changed the deployment picture:

- wall: 1,216.915 s (20m17s);
- speedup over P8: 1.759x;
- training wall: 625.509 s, 29.2% lower than P8;
- inspection wall: 523.347 s, 55.9% lower than P8;
- throughput: 13,908.50 chars/s;
- completed passes: 3;
- inspection complete: yes;
- overflow: 0;
- residual shards: none;
- SQLite `quick_check`: ok.

All six scientific artifact pairs compared between P8 and P10 had identical sizes and SHA-256 hashes. This is stronger than tolerance-based numerical equivalence and supports treating P9/P10 as engineering-only changes to wall time rather than changes to the scientific result.

The conservative full-M₀ projection after P10 is about 4.60 hours by characters and 4.06 hours by document count. Reaching the original ~3-hour target would require about another 1.53x or 1.35x speedup respectively.

## Scientific medium checkpoint

The completed medium audit produced the following durable diagnostics:

- mean identity mass: 0.070468;
- mean latent mass: 0.929532;
- mean posterior entropy: 1.044665;
- mean top-1 posterior: 0.594393;
- active lexical rows: 1,888,526;
- low-count rows: 1,866,960 (98.858%).

The large low-count tail is currently treated as a substantive modeling question, not as evidence of a counting bug. `active` means positive expected-count storage, not hard support. No change to lambda/tau should be justified from this medium statistic alone; the first full run is required to determine whether posterior mass concentrates on a substantially smaller reusable lexical core.

The tiny sanity-run symmetry between lexical `om` and `oṃ` does not persist on medium. Medium pass-3 training counts were approximately 47.612692 for `om` and 29.976378 for `oṃ`; inspection expected counts were approximately 50.809742 and 27.907685 respectively. This supports retaining the two intentional phonological types and treating the tiny-run equality as local grammar-licensed unidentifiability.

## Validation status

The latent-focused suite passed after the multiprocessing work. The full repository suite also passed except for three known failures in the untouched SentencePiece wrapper caused by the installed SentencePiece 0.2.2 API removing `immutable_proto`; these are outside the latent method.

Accepted optimizations were checked at relative tolerance `1e-10` and absolute tolerance `1e-12` before the stronger medium byte-identity comparison became available.

## Current scaling state

The next local measurement is P10 medium at 8 workers. An earlier attempt was manually interrupted while the master process was waiting on worker futures; its run directory was preserved rather than treated as a benchmark result. The clean 8-worker rerun was still in progress at the time of this checkpoint and therefore **must not yet be used as a durable scaling conclusion**.

Only after that run completes should its wall/phase timing, integrity checks, aggregate process-tree memory observation, and scientific hash comparison be promoted into a tracked report/update.

## Cloud deployment gate

The project is ready to move from algorithmic optimization into deployment/scaling once the 8-worker local medium measurement is closed out.

The cloud deployment gate is:

1. complete and audit local P10 8-worker medium;
2. bootstrap the single 16-vCPU / 32-GB Ubuntu host with repository, frozen inputs, environment, and data-disk layout;
3. verify corpus/rule provenance and freeze ID on the cloud host;
4. run short medium worker-scaling measurements sufficient to select a cloud worker count;
5. measure aggregate process-tree memory externally, because benchmark `peak_rss_bytes` covers the main process only;
6. launch the first production full-M₀ IAST + `surface_word` run only after the worker count and storage headroom are credible.

A ~3-hour full run remains an engineering target rather than a scientific requirement. If the best exact, reproducible configuration is slower, the measured time should be reported rather than recovered through approximate inference.

## What the first successful full M₀ must answer

The first full run is not a single-number benchmark. Its scientific audit must determine whether:

- a reusable latent lexicon emerges at corpus scale;
- lexical identities gain support across multiple surface/sandhi environments;
- the model avoids identity collapse;
- the low-count tail reflects benign posterior support or uncontrolled lexical proliferation;
- ambiguity remains calibrated rather than being artificially resolved;
- the fixed grammar and learned lexicon provide an economical reusable explanation of the observed corpus.

The resulting full-run conclusions, hashes/provenance, selected diagnostics, and deployment measurements must be promoted into a dedicated tracked report. Multi-GB JSONL/SQLite outputs should remain outside Git rather than becoming the only record of the result.

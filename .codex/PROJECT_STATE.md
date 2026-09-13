# PROJECT_STATE.md

Last major handoff: 2026-08-30
Primary implementation branch: `exp/s1m2-reusable-pieces`

This file records durable project state. It is not a task prompt.

## 1. Frozen M₀ corpus

M₀ is frozen and must not be reopened during core-method implementation.

- Commit: `dbff6836eb35ecb1933653443ca793b1ab890c63`
- Annotated tag: `m0` — never move this tag.
- Canonical root: `data/canonical/gretil_iast`
- Manifest: `data/manifests/canonical_corpus.csv`
- Freeze ID: `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`
- Documents: 240
- Characters: 57,588,079
- Bytes: 69,864,279

Formal M₀ observation conditions are exactly:

- IAST / `surface_word`
- IAST / `legacy_joined`
- IAST / `continuous`
- Devanagari / `surface_word`
- Devanagari / `legacy_joined`
- Devanagari / `continuous`

Older names such as `lexical_boundary` or `observed` are not formal M₀ conditions.

The first formal core-method run is planned for:

`IAST + surface_word`

Later conditions must be trained independently rather than initialized from the first condition.

## 2. Branch division

- `exp/m0-core-methods`: latent/sandhi core method work.
- `exp/m0-baseline-validation`: collaborator baseline production/validation line.

The collaborator line currently covers the 22-condition baseline matrix:
- BPE: IAST + Devanagari × 3 spacing = 6
- Unigram: same = 6
- Unicode code point: same = 6
- Akṣara-safe BPE: Devanagari continuous = 1
- Surface-lattice: IAST × 3 spacing = 3

TransLIST is a separate supervised Sanskrit segmentation/desandhi reference, not a 23rd matrix condition.

The core branch should coordinate interfaces/contracts, not take over the collaborator's implementation.

## 3. External-sandhi rule inventory

Tracked machine-readable inventory:

`data/rules/external_sandhi.tsv`

Current size: 1218 external-sandhi rules.

Columns:
- `rule_id`
- `left`
- `right`
- `surface`
- `variant`
- `status`

The file was mechanically generated from an untracked human-readable matrix.

Generation choices already made:
- `V̆` expanded over `{a, i, u, ṛ, ḷ}`.
- `|` surface alternatives split into separate rows.
- variants preserved.
- status currently `active`.
- IDs use `EXT_0001...`.
- `#` in the TSV is currently a readable boundary notation, not the final internal boundary object.

The runtime method may adapt/parse this inventory into a structured script-neutral representation, but should not rewrite the source TSV in the current task.

## 4. Existing sandhi infrastructure

Package:

`src/sktlm/sandhi/`

Existing modules include:

- `rules.py`
- `apply.py`
- `boundary.py`
- `inverse.py`
- `index.py`
- `lattice.py`
- `dp.py`
- `ngram_dp.py`
- `ngram_posterior.py`

Important behavior:

### `rules.py`
Loads and validates the fixed rule inventory.

### `apply.py`
Exact underlying pair -> all matching external-sandhi rule applications. No ranking.

### `boundary.py`
Forward realization of full word pairs; preserves rule provenance and variants.

Example:
`devaḥ + api -> devo'pi`

### `inverse.py`
Surface -> all grammar-licensed one-boundary inverse candidates. No hard ranking.

### `index.py`
Trie/index optimization for forward and inverse matching. This reduced exhaustive sandhi tests from tens of seconds to sub-second scale.

### `lattice.py`
Early proof-of-concept character/span DAG:
- identity edges per observed code point;
- sandhi edges over matched surface spans;
- ambiguity preserved.

This lattice was useful for proving the mechanics, but it is not assumed to be the final lexical-analysis representation.

### `dp.py`
Generic edge-local DAG log-sum-exp and debug Viterbi.

### `ngram_dp.py`
Context-aware character n-gram marginalization over the toy lattice.

### `ngram_posterior.py`
Character n-gram forward/backward, edge posterior, rule posterior, expected sandhi usage.

Existing sandhi tests were reported passing locally by the user.

## 5. Existing toy language-model / EM prototype

Existing/added modules include:

- `src/sktlm/experiments/models/ngram.py`
- `src/sktlm/experiments/training/sandhi_ngram_smoke.py`
- `src/sktlm/experiments/training/ngram_em.py`
- `src/sktlm/experiments/training/surface_ngram_experiment.py`

These prove that the following computation chain works:

fixed external grammar
-> inverse candidates
-> lattice
-> marginalization
-> posterior
-> fractional expected counts
-> iterative update

They are engineering proof-of-concept code, not the final research objective.

The user explicitly does not want the formal method to continue growing by patching the character-level EM approach.

## 6. Toy results and what they mean

A tiny surface-only toy corpus used:

- `devo'pi`
- `rāmo'pi`
- `aśvo'pi`
- `naro'pi`

The surface-only character n-gram EM-style run produced approximately:

- mean expected sandhi edges: `0.000248`
- target `aḥ + a -> o'` posterior: about `1e-7`
- convergence after roughly 2–3 iterations.

This is not evidence that surface-only Sanskrit sandhi induction is impossible.

The toy corpus repeatedly supports the surface pattern `o'pi` but provides almost no cross-environment recurrence that would make latent forms such as `-aḥ` and `api` useful across many contexts.

The durable conclusion is only:

- the software machinery works;
- the toy dataset is not adequate for judging full latent lexical induction;
- full-corpus recurrence is the intended learning signal.

A `surface_ngram_prior_experiment.py` was proposed/generated later, but the user deliberately did not run/adopt that direction. Do not treat a generic sandhi bonus as the intended method.

## 7. Current methodological redesign

The formal v1 method should be:

**script-neutral latent lexical induction with fixed external-sandhi grammar and corpus-wide lexical reuse.**

The central comparison is not:

`devo'pi` character probability vs `devaḥ#api` character probability.

Instead ask whether analyses such as:

`devo'pi -> devaḥ | api`

allow the same latent lexical units (`devaḥ`, `api`, etc.) to explain many observations across different sandhi and non-sandhi environments.

Current latent target level is lexical word-form identity such as:

- `devaḥ`
- `api`

Do not yet push to deeper morphology such as:

`deva + s`

Internal sandhi induction and deeper morphophonological identity are later stages.

## 8. Boundary / script interpretation

A lexical boundary is an abstract structural relation/object.

It is not:
- literal `#`;
- whitespace;
- zero-width spacing;
- apostrophe;
- avagraha;
- a Devanagari vowel form.

`#` may remain only for debug/serialization.

The intended layering is:

latent lexical/phonological structure
-> external-sandhi realization
-> script rendering
-> spacing realization

The same latent structure may be rendered with or without visible whitespace.

For Devanagari, an abstract lexical boundary can affect orthographic rendering even when no visible space is emitted, e.g. word-initial vowel behavior.

## 9. Script neutrality

The current toy prototype is strongly IAST-biased because IAST Unicode strings were used directly as model sequences.

Formal core code must instead expose a script-neutral Sanskrit phonological representation.

The first implementation should build and exercise only the IAST frontend, but its output and the learner interface must not depend on IAST-specific code-point structure.

A later Devanagari frontend should map into the same internal representation and use the same grammar/learner.

## 10. Candidate generation direction

The old proof-of-concept lattice intentionally overgenerated any matching substring.

Formal v1 candidate generation should use deterministic linguistic/orthographic constraints before statistical scoring.

Allowed evidence:
- visible whitespace;
- avagraha;
- punctuation;
- fixed grammar;
- phonological legality;
- exact forward reconstruction.

Every inverse candidate should forward-reconstruct the observed surface exactly.

Do not use:
- Sanskrit dictionaries;
- gold segmentation;
- morphological analyzers;
- pretrained Sanskrit models

to prune candidates in the surface-only induction experiment.

Whitespace is strong evidence, not gold segmentation.

## 11. Formal learner direction

The main signal should be corpus-wide reuse of latent lexical units.

Start with an interpretable unigram latent-lexicon learner, not a Transformer.

Conceptually a candidate analysis:

`w1 | w2 | ... | wk`

receives support from:
- learned lexical probabilities / expected counts of `w_i`;
- deterministic fixed-grammar compatibility;
- an explicit complexity/sparsity pressure penalizing proliferation of rare one-off latent lexical types.

Do not add a generic reward for using sandhi.

Use soft posterior assignment, expected lexical counts, and iterative updates.

Initialization should be reasonably neutral over legal analyses rather than first training an identity-favoring surface character LM.

The exact complexity/MDL formula is not yet theoretically frozen; any v1 implementation choice must be simple, explicit, configurable, and reported as an assumption.

## 12. Scalability requirements

The formal first run targets the full M₀ corpus (~57.6M chars, 240 documents).

Implementation must be:
- streaming/sharded;
- bounded-memory;
- deterministic.

Do not materialize the whole corpus, all lattices, or all full candidate paths in RAM.

Use compact representations / dynamic programming rather than explicit global path enumeration.

Checkpoint/resume is desirable if practical.

## 13. Required first-run artifacts

The IAST + surface_word full run should make the learned structure inspectable.

At minimum output:

- latent lexical inventory with expected counts/probabilities;
- surface span/form -> candidate latent analyses + posterior;
- boundary posterior;
- expected external-sandhi rule usage;
- identity-vs-latent posterior mass;
- ambiguity/confidence statistics;
- active lexicon size;
- low-count / one-off lexical-type statistics;
- explicit complexity/description-length-style summary;
- config/provenance metadata.

Also create a concise human inspection report with:
- highest-frequency latent forms;
- high-confidence sandhi analyses;
- most ambiguous cases;
- suspicious low-frequency/one-off latent forms;
- most-used sandhi rules;
- notable identity-to-latent shifts.

## 14. What the first full run is supposed to tell us

The primary questions are:

1. Does a reusable latent lexicon emerge?
2. Do latent word forms gain support across multiple surface/sandhi environments?
3. Does the model avoid both identity collapse and uncontrolled overanalysis?
4. Is the learned latent inventory more economical/reusable than memorizing surface forms?

Do not reduce the first run to a single loss/accuracy number.

## 15. Environment

User local development environment was moved to a repository `.venv` based on Python 3.11.9.

`numpy` was added to `pyproject.toml` dependencies after PyTorch warned that NumPy was absent.

Relevant tests were reported passing after this change.

## 16. Formal v1 implementation status (2026-08-30)

The first full-corpus-ready `IAST + surface_word` latent lexical learner is now implemented on `exp/m0-core-methods`. The expensive full M₀ run has **not** been launched.

New formal-method code lives under `src/sktlm/latent/`:

- `phonology.py`: script-neutral semantic phoneme IDs and IAST parse/render adapters;
- `frontend.py`: separates phonological content from observed whitespace, avagraha, and punctuation cues;
- `grammar.py`: compiles the frozen 1218-rule TSV into structured runtime matches, with `#` represented as a structural boundary rather than a character;
- `candidates.py`: constructs exact-reconstruction lexical candidate DAGs;
- `inference.py`: nested exact forward/backward inference with full marginals and bounded top-K decoding only for inspection;
- `store.py`: SQLite-backed expected counts/probabilities and bounded caches;
- `training.py`: streaming document/line processing, iterative expected-count updates, checkpoints, resume, and artifact writers.

The CLI is `sktlm-train-latent-lexicon`, implemented by `src/sktlm/experiments/training/latent_lexicon.py`.

Implemented candidate constraints include:

- fixed-grammar exact reconstruction of the observed phonological surface and typed cues;
- visible whitespace is evidence, not a lexical-boundary gold label;
- ignoring visible whitespace is legal but receives a configurable observation penalty (default `8.0` per ignored space);
- joined-surface external-sandhi rules normally stay inside a surface token; a whitespace crossing is allowed only immediately adjacent to avagraha for the current frontend;
- avagraha-bearing nonidentity analyses must consume the avagraha cue;
- deterministic candidate deduplication, a configurable internal-match bound, and an identity fallback.

The implemented unigram lexical score is:

`p(w) = (c_w + alpha) / (N + alpha * V)`

with default `alpha = 0.1`. The explicit complexity summary is:

`R(c) = lambda * sum_w log(1 + c_w / tau)`

with defaults `lambda = 0.5`, `tau = 1.0`. Per-use inference subtracts the corresponding exact one-count increment:

`lambda * log(1 + 1 / (tau + c_w))`.

These formulas remain documented implementation assumptions, not theoretically frozen project decisions. There is no generic reward for using sandhi. Pass 1 is neutral over legal analyses; later passes use learned lexical scores.

## 17. Validation and bounded sanity run

Focused latent/sandhi tests passed (`84 passed`). The repository suite excluding the three known SentencePiece compatibility failures passed (`428 passed, 3 deselected`). The three failures are in the untouched SentencePiece wrapper because the installed SentencePiece version no longer exposes `encode_as_immutable_proto`; they are not failures of the latent learner.

The latest bounded sanity artifact is:

`artifacts/latent_lexicon/sanity_v1d/`

It processed one document, six segments / 208 characters, for three passes. Final inspection statistics include:

- 257 active lexical rows;
- expected lexical tokens: `32.9704`;
- mean identity mass: `0.2737`;
- mean latent mass: `0.7263`;
- mean posterior entropy: `1.8979`;
- no internal-match overflows.

The required lexicon, analyses, boundary posterior, rule usage, ambiguity, complexity, configuration, provenance, checkpoint, and inspection-report artifacts were emitted. This run is only an engineering/method sanity check and is not evidence for corpus-wide linguistic conclusions.

## 18. Diagnosed `om` / `oṃ` symmetry in the sanity run

The sanity lexicon contains two deliberately distinct phonological keys:

- `om` = `V_O.C_M`, expected count `0.9986335340`;
- `oṃ` = `V_O.M_ANUSVARA`, expected count `0.9986335340`.

This is a grammar-licensed, presently unidentifiable ambiguity rather than representation or expected-count duplication.

The two inspected surface occurrences are `oṃ namo ...` and `oṃ brahma ...`. The fixed inventory licenses underlying final `m` before those consonants via:

- `EXT_0795`: `m + n -> ṃ#n`;
- `EXT_0793`: `m + b -> ṃ#b`.

For every otherwise identical displayed analysis, replacing first lexical `oṃ` by `om` plus the applicable rule leaves the lexical score and all downstream factors equal. The paired paths therefore have exactly equal log scores and posteriors. Exact forward/backward inference assigns mass to one lexical edge or the other; it does not add the same edge mass to both. Their combined expected count is `1.9972670681`, approximately the two observed occurrences, with the small remainder assigned to other legal analyses.

`active_lexical_types` currently counts every row in the learned lexicon table; it is not a hard-support selection threshold. Types with expected count at or below the configurable default `1.0` are additionally reported as low-count. Thus both members being “active” does not mean the learner hard-selected both.

Do not collapse `C_M` and `M_ANUSVARA`: they are intentionally different phonological symbols, and doing so would change the representation. On this tiny sample the current surface-only unigram objective has no disambiguating evidence. A full-corpus audit should check whether other environments break the symmetry. If the symmetry persists corpus-wide, resolving it would require an explicit new modeling decision (for example a lexicalized alternation treatment or another justified prior), not a counting bug fix.

## 19. Latent performance optimization status (2026-08-30)

The medium 1-pass reference completed at `artifacts/latent_benchmarks/medium_reference_p1/` with 5,297.481 seconds wall time. It identified inspection inference, repeated lexical score calls/key construction, candidate generation, serialization, and count storage as the main costs. Do not rerun this reference.

Accepted semantics-preserving commits after the reference are:

- `75da12f`: training-only exact inference;
- `14d883c`: cached immutable phonological-form keys;
- `87113e0`: segment-local reuse of lexical scores;
- `26e3a99`: script-neutral internal-sandhi match cache;
- `3840576`: compact SQLite count/lexicon storage;
- `fa27389`: deterministic crash-safe document multiprocessing for training;
- `3da7ad1`: deterministic crash-reusable document multiprocessing for inspection.

All accepted changes were checked against reference scientific artifacts with zero mismatches. The focused latent suite now reports `22 passed`. The full repository suite reports `444 passed, 3 failed`; the three failures remain the known untouched SentencePiece 0.2.2 `immutable_proto` incompatibility.

On repeated 3-pass smoke runs, the optimized serial median was 19.268 seconds (training 10.091, inspection 8.088). The final 4-worker median was 13.305 seconds (training 6.998, inspection 5.292), a 1.45x end-to-end speedup. Two workers did not amortize process/shard overhead on the short smoke documents; worker count must be benchmarked on medium before the full run.

Parallel workers never write the learner database. They create checksummed per-document shards; the master validates/reuses crash artifacts and applies them in canonical document/segment order. Training document updates remain transactionally coupled to the authoritative SQLite checkpoint. Inspection completion is also durable before successful shard cleanup, and completed resume skips repeated inference. Atomic temp-file replacement retries bounded transient Windows sharing violations.

The benchmark's `peak_rss_bytes` measures only the main process when workers are enabled. Do not interpret it as aggregate multiprocessing memory. Before choosing a full-run worker count, record process-tree memory externally or extend the harness with correct aggregate accounting.

No post-optimization medium or full M₀ run had been launched at the end of this
optimization round. The subsequent completed medium result is recorded below.

## 20. Completed optimized medium and P9-P10 (2026-08-31)

The P8 4-worker, 3-pass medium benchmark completed successfully at
`artifacts/latent_benchmarks/medium_optimized_p8_w4_p3/`, from commit `049d439`.
It took 2,141.125 seconds (35m41s), versus 5,297.481 seconds for the old
single-worker 1-pass reference. Normalized character throughput improved 4.948x;
average training-pass document time improved 3.731x; inspection document time
improved 3.355x; and inspection inference improved 3.797x. The direct wall ratio
is 2.474x even though P8 performs three training passes rather than one.

The artifact has three completed passes and completed inspection, zero candidate
overflow, no retained shard files, the expected artifact line counts, and a
healthy SQLite `quick_check`. Pass 1 iteration metrics are exactly identical to
the old medium reference. The final lexicon has 1,888,526 active types, of which
1,866,960 (98.858%) are low-count; this is a modeling/inventory concern rather
than evidence of duplicate aggregation.

Medium evidence breaks the sanity-run `om` / `oṃ` symmetry. Pass-3 training
counts are 47.612692 for `V_O.C_M` (`om`) and 29.976378 for
`V_O.M_ANUSVARA` (`oṃ`); inspection expected counts are 50.809742 and
27.907685. Literal `om iti` / `om ity...` and literal `oṃ ...` contexts
distinguish the keys. Preserve both representations: the sanity equality was
expected local ambiguity, not representation/counting duplication.

At P8 throughput, a full M₀ 3-pass-plus-inspection run projects to approximately
8.09 hours by characters (about 7.14 hours by document count), still roughly
2.70x short of the 3-hour target. The benchmark's 78.5 MB peak RSS is
main-process-only and must not be cited as aggregate multiprocessing memory.

Two later optimizations are committed:

- `e731d6c` (P9): a bounded `2 * workers` rolling submission window that keeps
  workers supplied while preserving canonical reduction and crash-safe shards;
- `dc68089` (P10): direct scalar boundary-posterior serialization.

P9's repeated 4-worker smoke wall median is 10.322 seconds, down from P8's
13.305 seconds, with zero scientific mismatches. P10 reduces the targeted
inspection-serialization median from 1.841 to 1.683 seconds (8.6%), again with
zero mismatches. The focused latent suite reports `22 passed`.

P9/P10 have not been measured on medium. The next authorized long job is
`medium_optimized_p10_w4_p3`, specified exactly in `.codex/CURRENT_TASK.md`.
The user must launch and monitor it manually; do not start a full M₀ run yet.

## 21. Completed P10 medium validation (2026-08-31)

The P10 4-worker, 3-pass medium benchmark completed at
`artifacts/latent_benchmarks/medium_optimized_p10_w4_p3/` from commit
`9be29ea`. Wall time was 1,216.915 seconds (20m17s), a 1.759x improvement over
P8's 2,141.125 seconds. Training document wall improved 1.413x and inspection
document wall 2.266x. Inspection inference improved 1.176x, candidate generation
1.225x, and serialization 1.428x.

The artifact has three completed passes, completed inspection, zero overflow,
and no retained shard files. SQLite `quick_check` is healthy. Training and
inspection tables each contain 1,888,526 types with count sums
394,031.7571645344 and 395,770.48199961643. P8 and P10
`iteration_metrics.json`, `summary.json`, `analyses.jsonl`,
`boundary_posteriors.jsonl`, `latent_lexicon.tsv`, and `rule_usage.tsv` are
byte-for-byte identical by SHA-256.

The conservative full-M₀ projection is now 4.60 hours by character throughput
and 4.06 hours by document count. The approximately 3-hour goal therefore still
needs 1.53x or 1.35x further scaling. The next authorized long job is an
8-worker run of the same P10 medium configuration, specified in
`.codex/CURRENT_TASK.md`. Aggregate Python process-tree memory must be measured
externally because benchmark `peak_rss_bytes` covers only the main process.

A post-P10 per-token internal-match reuse experiment was scientifically
equivalent but showed no reproducible smoke benefit against a current-host
control. It was fully reverted and not committed.

## 22. Local P10 8-worker scaling closed (2026-08-31)

The clean 8-worker P10 medium rerun completed at
`artifacts/latent_benchmarks/medium_optimized_p10_w8_p3_rerun1/` from
provenance commit `25998f0`. It has three completed passes, completed
inspection, zero overflow, no residual shard/tmp/SQLite sidecar files, and
`PRAGMA quick_check = ok`. Training and inspection tables contain 1,888,526
rows with count totals 394,031.7571645344 and 395,770.48199961643.

The six canonical scientific artifacts are byte-for-byte identical to the
4-worker P10 run by streaming SHA-256. Their names, sizes, and hashes are
promoted in
`reports/core_methods/latent_lexicon/medium_scaling_p10.md`.

Eight workers are negative scaling on this host:

- wall 1,216.915 → 1,526.624 s (+25.45%);
- training document wall +13.33%;
- inspection document wall +27.05%;
- benchmark total CPU +23.81%;
- character throughput -20.29%.

Four workers are the local production sweet spot. Do not spend time on local
12/16-worker measurements. The local full-M₀ projection remains the 4-worker
4.60-hour character estimate / 4.06-hour document estimate. This worker
conclusion is host-specific and must not be applied to the cloud host without
measurement.

The first 8-worker attempt at
`medium_optimized_p10_w8_p3_interrupted/` was manually stopped. Its checkpoint
has zero completed passes and it has no benchmark metrics. Its 24 partial shard
files (including 8 zero-byte temporary files) are crash diagnostics only and
are excluded from performance conclusions.

## 23. Cloud deployment preparation (2026-08-31)

The two remote documentation commits `99df410` and `921bfe1` were audited and
retained. The promotion policy is correct and the Stage 01 checkpoint is useful;
its provisional 8-worker state was corrected in a follow-up rather than by
rewriting public history.

No pre-existing cloud/deployment/bootstrap scripts were present. A guarded
workflow now exists under `scripts/cloud/` and is documented in
`reports/core_methods/latent_lexicon/cloud_deployment_ubuntu22.md`. It provides:

- read-only hardware/disk discovery;
- exact-HEAD, fast-forward-only repository bootstrap;
- refusal to place artifacts on the system/root filesystem;
- Python 3.11 venv/dependency setup on the data disk;
- reuse of canonical freeze and representation validators;
- Linux process-tree RSS/CPU/process-I/O sampling;
- bounded-memory artifact completion, SQLite, residue, and SHA-256 audit.

The cloud sequence is 4-worker medium, then 8 workers only after the first
audit. Local scaling is not extrapolated. Cloud 12/16 are conditional on
measured benefit and memory headroom. Full M₀ remains gated and must not be
started automatically.

## 24. Cloud host preflight state (2026-08-31)

The target Ubuntu 22.04.4 host has 16 vCPU and approximately 32 GB RAM. The
user deliberately created `/dev/vdb1` as ext4 with label `sktlm-data`, mounted
it at `/mnt/sktlm-data`, and verified `/etc/fstab`; the filesystem has roughly
280 GB available. This disk setup is complete and must not be repeated.

The fresh host has iostat/sysstat but does not yet have Git or Python 3.11, and
no repository bootstrap has started. The bounded local deployment audit found
three non-scientific preflight issues: host sanity aborted when Git was absent,
the frozen-input validator ignored CLI arguments, and bootstrap could change
the linked layout before detecting missing Python and did not explicitly update
the remote-tracking ref consumed by its merge. The minimal fixes were locally
validated for missing-tool behavior, CLI parsing, shell syntax, and Linux
process-wrapper behavior. No latent semantics, frozen input, rule inventory, or
accepted P10 result changed.

## 25. Deterministic local/cloud research bridge (2026-08-31)

`scripts/cloud/sktlm_bridge.py` now provides six bounded operations: `status`,
`deploy-code`, `push-inputs`, `verify-remote`, `pull-results`, and `collect`.
The architecture keeps Git commit/history authoritative for tracked code/configuration. GitHub is the publication/collaboration endpoint; production code transport to mainland core-01 through core-06 is a verified local Git bundle over SCP/SSH with exact-SHA and fast-forward-only checks. Resumable rsync over SSH is reserved for non-Git scientific bytes. It invokes
the existing input validator and run auditor instead of implementing divergent
scientific validation.

The bridge has no arbitrary remote command, package installation, benchmark
launch, Git push, remote deletion, or report commit capability. Remote command
strings come only from fixed templates with quoted configured values; local
subprocesses use list-form argv with `shell=False`. Every rsync connection
rechecks that the configured data mount is its own non-root filesystem, never
uses `--delete`, and refuses native Windows transfer execution in favor of
WSL/Linux.

Tracked configuration is the credential-free
`configs/cloud/bridge.example.toml`; the real `.sktlm-bridge.toml` is
gitignored. Mutating/sync operations write redacted receipts below
`artifacts/cloud_transfers/`. Result profiles are `report` (default),
`scientific` (without `learner.sqlite`), and explicit `full`; existing local
collection directories are never overwritten silently. `collect` preserves an
invalid remote audit while still retrieving diagnostics and records which
large artifacts remain remote-only.

The bridge is locally covered by 32 focused fake-subprocess/temp-directory
tests, Linux shell parsing of every fixed remote command template, and WSL
CLI/process-metrics smoke checks. Localhost rsync itself is installed, but no
local SSH daemon is available, so an optional end-to-end localhost SSH/rsync
smoke was not possible. At that pre-deployment checkpoint the bridge had not
contacted the real VM or transferred data, and the VM had no Git, Python 3.11,
repository, or benchmark. Section 26 supersedes that operational state.

## 26. Multi-host cloud checkpoint and local-output consolidation (2026-08-31)

Cloud deployment advanced after the original single-host preflight. The
reference `core-01` medium P10 w4 run is complete and audited at
972.1771821109978 seconds / 17409.851117105878 chars/s; its report-profile
collection is local and ignored. Aggregate process-tree peak RSS was
978,272,256 bytes. `core-02` w8, `core-03` w12, and `core-04` w16 remain
RUNNING; `core-05` and `core-06` are standby. No pending result is inferred.

The bridge now supports optional TOML `[host_profiles.<id>]` overlays while
preserving the legacy `[bridge]` form. Every subcommand accepts
`--host-profile`. Status and receipts record logical profile/machine identity.
When multiple profiles exist, `collect`/`pull-results` require explicit
selection and match it against `configs/cloud/experiment_registry.toml` before
any SSH action, preventing collection from a clone assigned to another run.
Operational hosts/IPs and identity paths remain in ignored
`.sktlm-bridge.toml`.

The durable cloud result, cost gate, pending states, selection rule, and w4
scientific hashes are in
`reports/core_methods/latent_lexicon/cloud_scaling_checkpoint_20260831.md`.
A single bounded inventory of local reports/notes/artifact-root metadata is in
`research_output_inventory_20260831.md`. It promoted the cloud w4 conclusions
but left raw P10/cloud outputs, generated cleaning audits, old notes,
interrupted runs, receipts, and private operational config local and intact.
The single focused bridge suite passed all 37 tests after this change.

## 27. Cloud medium scaling closed; 8-worker production setting (2026-08-31)

The Ubuntu 22.04 cloud medium gate is complete under scientific checkpoint
`fbd0a499701d6a13dcbf8374d5b5ce3a357a7b04`. All four runs are DONE and
their remote audits report valid. Wall times rank w8 (740.9371817360001 s),
w16 (849.243166304 s), w12 (853.409434638 s), then w4
(972.1771821109978 s). The w8 result is approximately 12.8% faster than the
w16 runner-up, satisfying the preregistered >=10% direct-winner rule.

Eight workers are therefore frozen as the cloud production setting for the
next full-M0 stage. No tie-break or additional medium scaling run is needed.
Scaling improved substantially from 4 to 8 workers, became negative at 12/16,
and plateaued between 12 and 16; w8 also used fewer CPU seconds than w12 or
w16. This is a measured host-class result and does not assert a hardware cause.

All four runs produced byte- and SHA-256-identical `analyses.jsonl`,
`boundary_posteriors.jsonl`, `iteration_metrics.json`,
`latent_lexicon.tsv`, `rule_usage.tsv`, and `summary.json`. The small
differences in aggregate benchmark `artifact_bytes` reflect noncanonical
runtime/metadata files and are not scientific differences.

The next gate is prepared, not launched: four 8-worker full-M0 replicas map
`core-01` through `core-04` to `rep01` through `rep04`; `core-05`
and `core-06` remain unassigned READY/STANDBY. Their purposes are a
production scientific result, failure insurance, cross-host runtime variance,
and deterministic cross-host reproducibility. The authoritative closure and
hashes are in
`reports/core_methods/latent_lexicon/cloud_scaling_checkpoint_20260831.md`;
the completed run records and planned identities are in
`configs/cloud/experiment_registry.toml`.

## 28. Formal benchmark evidence layer (2026-08-31)

`reports/core_methods/latent_lexicon/evidence/` now preserves small,
non-sensitive machine-readable evidence for the accepted cloud medium P10
w4/w8/w12/w16 checkpoint and the accepted local P10 w4/w8 comparison. The
manifest maps run IDs, workers, provenance commits, source locations, copied
evidence, and the already-established canonical artifact sizes/SHA-256 values.
No hashes, audits, or benchmarks were rerun.

Raw metrics/audit/config/provenance evidence was locally available and copied
for cloud w4 and both local runs. Cloud w8/w12/w16 raw small files were not
present locally; their tracked files are explicitly labeled accepted-result
digests of facts already recorded in the registry and cloud checkpoint.
Multi-GB deterministic outputs, SQLite files, WAL/shards, and process samples
remain ignored/local.

## 29. Full-M0 four-replica launch preparation (2026-08-31)

Four durable run/metrics pairs are prepared for `core-01`/`rep01` through
`core-04`/`rep04`, all at the frozen cloud setting of 8 workers and three
passes. The run IDs are
`cloud_full_m0_iast_surface_word_p10_rep01_w8_p3` through
`cloud_full_m0_iast_surface_word_p10_rep04_w8_p3`; the corresponding metrics
IDs omit the leading `cloud_`. Registry state is PREPARED, not RUNNING.

The full workload uses `sktlm.experiments.training.latent_lexicon` without a
document list or max limits. The benchmark harness was inspected and supports
only smoke/medium, so no nonexistent `--benchmark full` mode is used. The
exact launch, one-line monitor, post-run audit-envelope, and final audit
commands are tracked in
`reports/core_methods/latent_lexicon/full_m0_launch_plan.md` and
`.codex/CURRENT_TASK.md`. No SSH, launch, test, audit, or scientific-code/data
change occurred during preparation.

## 30. Active unrestricted replicas and optional vocabulary budget (2026-08-31)

The user reports that `core-01` through `core-04` are now running the four
unrestricted full-M0 replicas. They are strictly hands-off: no SSH, polling,
process control, resume, cleanup, cloud Git operation, or run-directory change
is authorized. `core-05` and `core-06` remain READY/STANDBY and unlaunched.
This operational state was supplied by the user and was not independently
queried.

The local core implementation now has a separate optional
`--vocab-budget K` condition for future capacity-matched BPE/Unigram
comparisons. `None` omits the new field from the configuration payload, so
the existing unrestricted configuration signature and inference path remain
unchanged.

For a constrained run, all 50 script-neutral singleton `Phoneme` identities
are forced into the vocabulary. Neutral Pass 1 ranks remaining multi-phoneme
latent `form_key` identities by `expected_count DESC, form_key ASC` and keeps
at most `K-50`. The resulting vocabulary is stored durably in SQLite and used
unchanged by later passes, workers, resume, and final inspection. OOV
multi-phoneme forms have no lexical parameter: their score, expected counts,
and decoded sequence are projected to constituent base tokens. Surface
variants and sandhi rules consume no vocabulary slots.

Constrained runs emit `vocabulary_budget.json` and `vocabulary.tsv`, and bind
the selection semantics plus allowed-key SHA-256 into checkpoint, provenance,
and summary metadata. A single focused local command covering selection,
tie-breaking, count projection, score decomposition, unrestricted `None`,
artifact output, and completed-run resume passed: `8 passed in 0.91s`. No
smoke, medium, full, cloud, or active-run validation was performed.

## 31. Research nomenclature and current roadmap (updated 2026-09-01)

M₀ is the frozen common experimental substrate: corpus, exactly six formal
observation representations, and shared provenance/evaluation contracts.
Full-M₀ describes full frozen-corpus extent for one representation condition;
it is not a model name. Historical branch, run, and report names remain
unchanged as provenance.

Pre-S1M1 VM and capacity calibration is CLOSED. The unrestricted word-form
support is approximately 19.07M identities; 90%/95%/99%/99.9%/99.99% mass
requires approximately 1.027M/1.493M/2.084M/2.875M/3.893M identities. K16 and
K32 primarily create atomization/phoneme fallback under strong compression
pressure and remain appendix sensitivity evidence. No new K, sweet-spot
search, or 18-cell fixed-K matrix is planned.

The active gate is unrestricted learning across all six M₀ representations.
IAST surface_word is supplied by accepted replicas; five new cells are
RUNNING at the frozen representation-gate checkpoint. Baseline/tokenizer
comparison, common evaluation, S1M1 specification freeze, aggregation, and
paper-facing outputs remain deferred until these runs complete and audit.

S1M1 targets flat lexical word-form identity and diagnoses the limits of that
hypothesis class under the fixed external-sandhi grammar. S1M2 moves to
reusable untyped compositional pieces:

    x -> u -> p1 ... pk
    concat(p1 ... pk) = u

The frozen grammar licenses/reconstructs u from observed x. The learner may
segment u into reusable pieces but may not introduce a rewrite: concatenation
must be exact. It predeclares no stem, suffix, root, ending, lemma, POS,
paradigm, or grammatical-feature roles. Stage 1 adds no gold morphology,
analyzer, TransLIST/gold segmentation, Sanskrit-specific morphological prior,
or learned internal morphophonological rules.

S1M3 opens only for independent scientific semantics; otherwise proceed to
Stage 2. Systematic-gap allomorph induction is a future later-stage hypothesis,
not a frozen S1M2 requirement. It may eventually test latent families using
posterior-predictive missing forms, distributional/compositional replacement,
and explicit complexity costs without prescribing a gold underlying form.

## 32. CI and reproducible-environment capture (2026-08-31)

GitHub Actions now runs the repository-standard `pytest` command on
`ubuntu-latest` for Python 3.10, 3.11, and 3.12 after installing `.[test]`.
The workflow intentionally contains no corpus download, benchmark, GPU job,
experiment matrix, full-M₀ launch, or large-artifact upload.

`scripts/repro/capture_environment.py --output-dir PATH` writes a
machine-readable `environment.json` and deterministic
`requirements-freeze.txt`. It records Python, OS/machine, key package,
optional Torch/CUDA, Git, and installed-distribution provenance without
emitting editable local paths. Existing output files are never overwritten.
This keeps `pyproject.toml` install-oriented while allowing a formal
paper/release run to preserve the exact environment it actually used.

The capture tool is scaffolding only and was not integrated into, or used to
modify, any active pre-S1M1 job. S1M1 paper-facing orchestration remains
deferred until the unrestricted six-representation gate completes, any
frontend/shared scientific adjustments finish, and the S1M1 scientific
specification freezes. Only then should declarative execution, per-cell
provenance, audit, aggregation, and paper-facing tables/figures be implemented.

## 33. Calibration closed and unrestricted representation gate running (2026-09-01)

This section supersedes the operational/future-plan statements in Sections 30
and 31 without rewriting their historical record.

The four unrestricted IAST surface_word full-M0 replicas completed naturally
at 8 workers and three passes. Their six canonical scientific artifacts are
byte-identical. Wall times were 13,058.676, 12,615.774, 13,103.272, and
13,165.096 seconds for rep01 through rep04; peak process-tree RSS was
3,711,254,528, 3,729,432,576, 3,728,773,120, and 3,708,420,096 bytes.

Unrestricted capacity analysis found 19,068,580 active word-form identities
and approximately 1.03M/1.49M/2.08M identities for 90%/95%/99% expected-count
coverage. Fixed K=16,384 and K=32,768 runs shared the unrestricted neutral
Pass 1 exactly, then both entered a strong projection-pressure regime far from
unrestricted behavior and close to one another. Capacity calibration is
therefore CLOSED. K16/K32 remain appendix sensitivity evidence; no more K
values, K grid, sweet-spot search, or 18-cell matrix is planned.

The formal training selector now supports all six frozen M0 script/condition
cells. IAST defaults and unrestricted behavior remain unchanged. The
script-neutral phonological interface includes a minimal parser for the
repository-generated M0 Devanagari representation. Direct full-run audit and
collection safety were extended for the representation gate. The focused
frontend/training/audit/bridge suite passed 80 tests in 8.33 seconds.

The five remaining unrestricted cells were manually bundle-deployed and
launched at scientific checkpoint
375178ba50bd1a1644d65525907692b31413b33d and are RUNNING:

- core-01: IAST legacy_joined;
- core-02: IAST continuous;
- core-03: Devanagari surface_word;
- core-04: Devanagari legacy_joined;
- core-05: Devanagari continuous.

Core-06 remains standby and was not deployed or launched. Before launch, all
five selected hosts had the exact checkpoint, clean branch, no prior active
job, absent target paths, and identical valid frozen-input verification.
Bundle deployment and immediate live-PID/process-sample checks succeeded.
Exact assignments, PIDs, counts, and hashes are recorded in
reports/core_methods/latent_lexicon/six_representation_gate_launch_checkpoint_20260901.md.

RUNNING is not completion. No final wall time, RSS, return code, audit, or
scientific result is recorded. Codex must not contact, poll, collect from,
audit, stop, restart, resume, or otherwise modify these hosts or jobs. After
natural completion, the human operator must require process_tree_summary.json
return_code=0 and final audit valid=true before collection, comparison, or
marking a row DONE.

For core-01 through core-06, production deployment is a verified local Git
bundle over SCP/SSH with exact-SHA and fast-forward-only checks. Remote GitHub
fetch/pull and copied working trees are forbidden production paths. The
historical full_m0_launch_plan.md remains untouched.

The clean-checkout manifest test now validates six-cell cardinality and logical
document uniqueness without requiring gitignored representation payload.
Production load_documents file-existence checks remain unchanged. The focused
frontend/bridge suite passed 57 tests in 0.71s; the single full pytest run
passed 516 tests with two existing warnings in 44.45s.
Baseline/tokenizer comparison, common evaluation, S1M1 specification freeze,
aggregation, and paper-facing work remain deferred until the unrestricted
six-representation gate completes.

## 34. Post-gate analysis and independent-review preparation (2026-09-01)

While the unrestricted six-representation gate remained RUNNING and strictly
human-operated, a local-only post-completion evidence path was added without
changing latent scientific/runtime code or any active configuration.

`src/sktlm/analysis/six_representation_gate.py` and
`scripts/analysis/aggregate_six_representation.py` accept an explicit local
JSON manifest for exactly the six unrestricted formal cells. They fail closed
on missing/duplicate identities, fixed-K or scoped inputs, undeclared
multi-commit provenance, cross-cell config/M0 provenance mismatch, nonzero
process return, invalid final audit, missing canonical outputs, or local
bytes/SHA mismatch against audit. The lexicon scan is bounded-memory and checks
`expected_count DESC, form_key ASC`; outputs cover the frozen mass-support
thresholds, scalar comparisons, rule TV/JSD in nats, candidate/overflow
statistics, and separate process-tree engineering metrics. Successful outputs
are deterministic JSON, tidy TSV, and claim-free Markdown in a new
non-overwritten directory. The analysis order, deterministic qualitative
sample-selection rules, and interpretation limits are frozen in
`post_gate_analysis_protocol.md`.

The researcher-authored `notes/reviewer/reviewer_prompt.txt` and
`notes/reviewer/method.txt` were initially ignored/untracked and were promoted
byte-for-byte after a secret/private-infrastructure review. Their SHA-256 values
are respectively
`d5efc209de1f3a6dbf76726ecbd638d08acc91c98bf9c5ec2058fa00af27d0a1`
and
`f7bcf017be5c4c912a2e2e3b0a4b49398da27df1c6921fc9469a686f05f42015`.
The independent-review protocol requires five fresh sessions with one
content-identical frozen packet/prompt, immutable per-reviewer raw responses,
5/5 completion before synthesis, and separate author adjudication. The local
packet helper records repository/scientific Git identity and deterministic
file/prompt/method/packet hashes, and verifies eventual raw-review metadata. It
contains no LLM/API/browser/network behavior; no review has run.

`continuous_performance_source_analysis.md` maps frontend segmentation,
grammar matching/cache, candidate graph construction, exact DP/top-k,
lexical scoring, multiprocessing, SQLite, telemetry, serialization, and
inspection from source only. It separates future semantics-preserving
implementation candidates from candidate/scoring/representation changes that
would require a new scientific condition. No optimization was implemented and
no active/partial VM metric was used.

The focused synthetic suite for the new aggregation and review-packet contracts
passed once (`14 passed in 3.61s`). Final local contract review added portable
Windows/POSIX path-escape rejection for packet destinations and raw-review
paths, plus machine-readable refusal when an aggregation output directory
already exists; its single new regression test passed (`1 passed in 0.19s`)
without rerunning the completed suite. The five new representation jobs remain
RUNNING at scientific checkpoint
`375178ba50bd1a1644d65525907692b31413b33d`; no completion or scientific
comparison is recorded.

## 35. One-shot audited scientific collection (2026-09-01)

The bridge `collect` command now accepts the existing `report`, `scientific`,
and `full` result profiles while retaining `report` as the backward-compatible
default. `collect_action` passes the selected profile into the unchanged
transfer path after the remote audit. Scientific collection therefore produces
`benchmark/`, `metrics/`, `remote_audit.json`, and `.sktlm-collection.json` in
one operation and no longer requires a separate transfer-only `pull-results`
call.

The scientific profile remains the report/metrics set plus
`iteration_metrics.json`, `analyses.jsonl`, `boundary_posteriors.jsonl`,
`latent_lexicon.tsv`, and `rule_usage.tsv`; it excludes `learner.sqlite`.
Audit-first ordering, invalid-audit preservation, downloaded hash validation,
redacted receipts, registry assignment checks, resumable partial-transfer
identity, and refusal to overwrite remain intact. Eight focused local synthetic
bridge tests passed in 0.92 seconds, and Python syntax compilation passed. No
VM, SSH, SCP, rsync, remote audit, collection, benchmark, scientific runtime,
or registry operation was performed.

## 36. Non-continuous 2×2 checkpoint closed locally (2026-09-01)

The completed unrestricted IAST/Devanagari × `surface_word`/`legacy_joined`
four-cell evidence is now promoted to
`reports/core_methods/latent_lexicon/noncontinuous_representation_checkpoint_20260901.md`.
Within `surface_word`, script conversion is exactly scientifically equivalent
except for raw character count. Within `legacy_joined`, the script effect is
negligible but not exactly zero. In contrast, joining has a large and nearly
script-invariant effect: active/low-count lexical types rise about 36%, expected
lexical-token count falls about 21%, entropy falls about 19.5%, identity mass
rises about 25%, and rule usage falls about 28.8%.

A bounded deterministic Devanagari merge selector supplied four additional
real examples plus the pre-specified anchor without scanning the full analysis
artifacts. The qualitative evidence shows that `legacy_joined` amplifies an
over-long lexicalization tendency already present in `surface_word`. This is
recorded as a low-supervision learner/objective failure mode motivating later
abstraction/reuse objectives, not Sanskrit-specific hard constraints or a
claim of linguistic understanding.

Scientific collection now reuses the bytes/SHA inventory already computed
after transfer, so each canonical local payload is hashed once rather than
read a second time for remote-audit comparison. Scientific/full collection
still fails closed on missing audit identities, missing local files or
inventory rows, and bytes/SHA mismatch; report-only collection remains
backward compatible. Focused synthetic tests passed, with no remote operation,
scientific-runtime change, corpus/manifest change, or registry change.

The continuous cells remain outside this checkpoint. The six-cell gate and
final M1 conclusion remain open until human-supplied completed/audited
continuous collections are available.

## 37. Generic representation analysis and archival gate (2026-09-03)

`src/sktlm/analysis/representation_protocol.py` implements v2 partial-cell
aggregation while reusing strict validation and scientific metrics from the
historical six-cell gate. The manifest separates the declared universe from
supplied cells, records typed N/A reasons and optional runtime/termination
evidence, and declares pair directions. Only available endpoints produce
scientific scalar, rule-distribution, and top-k comparisons; unavailable
values are JSON null and TSV/Markdown `N/A`. The historical v1 behavior is
preserved.

`src/sktlm/analysis/artifact_inventory.py` implements explicit-path,
streaming-SHA, deterministic, read-only inventory plus an evidence-based
READY/NOT_READY gate and atomic non-overwriting JSON/TSV output. It contains no
delete function. Focused synthetic and legacy compatibility tests passed (`15
passed`). Formal S1M1 analysis was not run, formal large files were not hashed,
no artifact was deleted, M0-prime was not started, S1M2 P1c was not started,
and no VM/cloud operation occurred.

## 38. S1M1 final-analysis/archive preparation (2026-09-03)

The final status contract is now four complete non-continuous scientific cells,
IAST `continuous` scientifically excluded, and Devanagari `continuous`
execution-incomplete. Both continuous runs were manually terminated and their
partial scientific state is excluded; their retained runtime/termination
evidence remains diagnostic. The formal v2 manifest and transparent historical
IAST-anchor acceptance envelope are tracked.

Formal aggregation was not launched because its strict hash validation and
scientific reduction would scan twelve local large sources totaling
91,193,439,274 bytes. Existing audit/replica hashes were recorded, but local
revalidation was still pending at this preparation checkpoint. Completed-cell
SQLite databases were not included in local scientific collections, so exact
training-final scorer and reuse state require source-host compact export.

A standard-library, read-only streaming exporter and explicit resumable operator
SHA script are prepared and synthetically tested. The exporter writes exact
scorer/inspection/reuse/segment/boundary/pass/rule/runtime summaries with
atomic output, SHA-256, and read-back consistency. No real compact export ran.
At this preparation checkpoint, the machine-readable deletion gate was
`NOT_READY`: no source was safe to delete and both failure-evidence sets were
retained. M0 remained frozen, M0-prime was not generated, S1M2 P1c was not
started, and no cloud/VM or long process ran.
Focused tests passed (`18 passed`), and the full pure test suite passed once
(`551 passed`, four warnings, 27.86 seconds); syntax and diff checks passed.

## 39. S1M1 scientific analysis closed; archival pending (2026-09-03)

The preparation and pre-closure states in sections 36-38 are superseded for
current status by the completed small outputs supplied by the researcher:

```text
S1M1 scientific analysis: COMPLETE
formal aggregation: VALID
large-source inventory: VALID
archival compact state: PENDING
deletion gate: NOT_READY
freeze: NOT_STARTED / PENDING
M0-prime: NOT_STARTED
S1M2 P1c: BLOCKED
```

Formal analysis `s1m1-final-four-cell-20260903` validated six declared cells:
four `AVAILABLE`, IAST `continuous` as `NA_SCIENTIFICALLY_EXCLUDED`, and
Devanagari `continuous` as `NA_EXECUTION_INCOMPLETE`. The completed source
inventory `s1m1-final-source-inventory-20260903` validated size and SHA-256 for
all twelve large scientific sources totaling 91,193,439,274 bytes. These
existing outputs were used without rerunning aggregation or hashing/scanning
the large sources.

The formal conclusion is spacing effect substantially greater than script
effect. `surface_word` is scientifically equal across scripts except raw
character accounting; `legacy_joined` has negligible nonzero script residuals.
Removing visible spacing reproducibly expands active types about 36.23% and
low-count types about 36.70%, reduces expected lexical tokens about 21.33%,
reduces entropy about 19.54%, raises top-1 posterior about 5.04%, and reduces
external-rule expected usage about 28.79%. The joint pattern identifies
context-specific over-long lexicalization under the current flat lexical
objective: a sharper posterior coexists with worse lexicon economy.

The completed scientific collection profile excluded `learner.sqlite` by
contract. Metadata-only checks found the four canonical completed-cell
training-final databases absent from this checkout and found no
`learner.sqlite` in the known local cloud-collection directories. Other local
smoke/medium databases exist but are not substitutes. The archival policy
recorded at that closure point required four compact exports; section
40 supersedes that archival policy. No artifact was approved for deletion and
freeze remained pending.

## 40. Selective S1M1 SQLite retention interface (2026-09-03)

SQLite microstate preservation is now selective rather than a four-cell
requirement. The machine-readable policy is
`configs/analysis/s1m1_sqlite_retention.json`:

- Devanagari `surface_word` is the successful boundary-visible microscopic
  reference. Retain its raw `learner.sqlite`, its non-empty WAL if present,
  and compact scorer/surface/context association state.
- Devanagari `legacy_joined` is a completed diagnostic failure/stress
  condition. Retain its compact scorer/surface/context state, but not its raw
  SQLite/WAL permanently.
- Neither completed IAST cell requires SQLite microstate archival because the
  matched-spacing script effect is negligible. Existing scientific
  outputs/provenance remain governed by their existing retention policy.
- Both continuous partial databases are excluded from the completed
  training-final contract; existing failure/termination evidence is retained.

`export_s1m1_sqlite_state.py` reuses the existing read-only SQLite query and
table-export machinery without reading scientific JSONL/TSV inputs. It writes
three compressed tables, database/WAL source identities, compact hashes,
read-back row/mass checks, a manifest, and `SHA256SUMS` through atomic
non-overwriting publication. It uses SQLite `mode=ro` plus `query_only` and
performs no checkpoint, journal-mode change, or SQL write. Schema v2 also
records the exact exporter Git commit, implementation identity, schema identity,
and implementation-file hashes, and fails closed if Git provenance cannot be
resolved.

The pre-execution workflow requires the learner to be stopped and DB/WAL state
to be quiescent. It leaves the scientific source checkout unchanged, runs the
audited commit from a separate detached Git worktree, writes compact output
outside the source checkout, and verifies returned Devanagari `surface_word`
raw identities against `manifest.json`. Artifact classifications use only
`PENDING`, `RETAIN`, `SAFE_TO_DELETE_REGENERABLE`, and `NOT_SAFE`; `NOT_READY`
is gate-level only.

No real database was opened, hashed, or exported in this implementation task.
The next external step is limited to the two Devanagari products above. S1M1
scientific analysis remains complete; freeze remains pending solely because
the researcher chose to finish selective archival, deletion-readiness, and
final artifact audit first. Codex/repository tooling never performs deletion.
Focused validation passed: `5 passed in 0.94s`; changed Python files compiled,
both changed JSON files parsed, and `git diff --check` passed.

## 41. S1M1 association-microanalysis implementation (2026-09-04)

The returned Devanagari `surface_word` and `legacy_joined` compact states
are present locally. A metadata-only preflight accepted both schema-v2
manifests, their exact exporter commit/implementation identities, small
manifest checksums, declared file sizes, and their previously verified
`SHA256SUMS` identities. It did not scan or rehash the large compressed
payloads. Declared rows are:

- `surface_word`: 19,068,580 scorer, 8,356,854 surface, and 11,226,279
  context rows;
- `legacy_joined`: 25,977,252 scorer, 6,495,224 surface, and 8,741,612
  context rows.

`src/sktlm/analysis/association_specialization.py` now provides the generic
bounded-memory mechanism. It validates strict scorer/association ordering and
duplicate-pair absence while streaming, computes per-form context and surface
concentration/entropy/effective-support metrics, emits type-, scorer-mass-, and
association-mass-weighted summaries, fixed length/count/joint bins, online
length/count relationships, exact shared/left-only/right-only matched-form
comparisons, count-increase strata, and bounded deterministic diagnostics.
`scripts/analysis/analyze_association_specialization.py` is the thin CLI;
`configs/analysis/s1m1_association_microanalysis.json` contains the S1M1
cells, direction, bins, namespace declaration, and diagnostic thresholds.

Lexical length is the number of validated canonical script-neutral
`Phoneme` IDs in `form_key`, not Unicode or morphology. Entropy uses natural
logs; normalized entropy is zero at support one and `H / ln(n)` above one;
effective supports are `exp(H)` and `1 / sum(p_i^2)`. The audit confirmed
that scorer counts are final-training-pass state, surface associations are
thresholded inspection expected counts, and contexts come from retained
top-K inspection analyses above threshold. Cross-table equality is therefore
not a valid invariant; each table is instead reconciled independently to its
compact manifest row/mass totals.

Focused association plus compact-export regressions passed (`10 passed`);
the complete analysis suite passed (`64 passed`), and the repository suite
passed (`594 passed, 4 warnings`).
The full association scan has not run. No formal aggregation, source
inventory, learner, raw SQLite hash, VM operation, deletion-readiness update,
scientific-conclusion change, M0-prime work, or S1M2 work occurred. The only
recommended full command is recorded in
`docs/workflows/association_specialization_analysis.md`.

## 42. S1M1 scientific closure and freeze (2026-09-05)

Section 41's pending state is superseded. The full association microanalysis
`s1m1-devanagari-association-microanalysis-20260904` completed successfully:
45,045,832 per-form rows and 27,897,467 comparison rows were emitted, its
manifest is valid, and every entry in its `SHA256SUMS` file was verified. Both
retained compact-state checksum sets were also verified. The retained
Devanagari `surface_word` raw `learner.sqlite` is 10,488,496,128 bytes; its
locally recomputed SHA-256 is
`e62ec033052c4dcdfedf7c3164faa88c7e954a4c2fbc5b73379faa49395d5c8c`,
exactly matching the exporter-recorded source identity. No WAL was present at
export or in the retained raw directory.

Direct association-level evidence is `YES`, with an explicit weighting
qualification. Expected-count-weighted context top-1 share rises from 0.3204
under `surface_word` to 0.4188 under `legacy_joined`, while context entropy
falls from 4.7255 to 3.7926 nats; association-mass and surface metrics show the
same mechanism. The joint length-at-least-17/count-at-most-0.1 region contains
6,713,168 legacy forms versus 3,829,489 surface forms. Type-weighted context
top-1 does not uniformly increase (0.8607 surface versus 0.8509 legacy), so the
claim is population/mass-level proliferation of long, low-count, narrowly
associated identities, not that every legacy type is more specialized.

S1M1 is now `SCIENTIFIC_ANALYSIS_COMPLETE`, `ARCHIVAL_COMPLETE`,
`DELETION_GATE_READY`, and `FROZEN`. The final deletion-readiness contract
classifies the twelve large completed-cell scientific sources (91,193,439,274
bytes total) as `SAFE_TO_DELETE_REGENERABLE`; required raw SQLite, compact
state, association evidence, aggregation/inventory, and continuous-cell
failure evidence are `RETAIN`. No file, database, VM artifact, compact export,
association payload, or scientific source was deleted. Physical deletion
requires a separate researcher decision.

The frozen conclusion is that the flat lexical objective is effectively
script-invariant across the completed cells but strongly dependent on visible
boundary evidence. Reducing that evidence yields a sharper posterior together
with a much larger long/low-count lexicon and less external-rule use. Visible
spacing is evidence/regularization for this objective, not gold wordhood and
not a claim that Sanskrit requires spaces. A corrected continuous substrate
and S1M2 reusable untyped pieces are the next work; S1M2 P1c has not started.

## 43. M0-prime implementation and formal-run boundary (2026-09-05)

The generic M0-prime generator/validator is implemented on `main` in
`src/sktlm/representations/m0_prime.py`, with formal configuration at
`configs/representations/m0_prime_iast_continuous.json` and workflow contract
at `docs/workflows/m0_prime.md`. It derives only from frozen M0 Devanagari
`continuous` (240 documents; freeze ID and both source-manifest hashes are
fail-closed) and never edits M0.

The derived text uses `ē`/`ō` for lexical `/ai/` and `/au/`, leaving `ai`/`au`
for separate vowel sequences. A real-corpus preflight exposed the analogous
ordinary-IAST collision between lexical aspirates and plain consonant+`h`
sequences, so M0-prime also uses modifier `ʰ` for lexical aspirates and leaves
ordinary `kh` ... `bh` for two phonemes. The `iast_m0_prime` frontend maps the
encoding into the same script-neutral `Phoneme` inventory as the M0 frontends.

Generation is streaming by document, atomic, non-overwriting, and requires a
clean Git worktree. Validation independently checks exact source hashes,
document/path/split/canonical identity, output membership and hashes,
deterministic regeneration, line/whitespace preservation, absence of retained
Devanagari, all declared contrasts, and equality of source/output
script-neutral phoneme sequences. It emits a permanent manifest, generation
and validation records, config snapshot, and `SHA256SUMS`.

Focused representation/frontend/training tests passed (`93 passed`), the full
repository suite passed (`600 passed`, four warnings), and a bounded 29-file
real-corpus check preserved phoneme identity while observing every declared
contrast. The formal full-data output has not yet been generated or validated.
Its exact generation and validation commands are documented in the workflow;
they must run sequentially once in the authorized detached Windows job.

## 44. M0-prime formal generation and validation (2026-09-05)

The one-shot detached task `sktlm-m0-prime-iast-continuous-v1` ran the exact
documented generation command followed by validation at clean implementation
commit `e7f5b7d8e57b81868c97000b3058347160030df2`. It started at 02:00 local time
and finished at 02:22; both command exit codes and the Task Scheduler result
were zero. The job was not duplicated.

The formal result is `VALID` for all 240 documents. The output contains
64,932,981 bytes, 51,409,280 characters, 2,107,648 lines, and 46,255,133
script-neutral phonemes. It observes 276,978 lexical `/ai/`, 116,388 lexical
`/au/`, 25,078 separate `a+i`, 23,397 separate `a+u`, 1,558,270 lexical
aspirates, and 423 plain consonant+`h` sequences. Source/output phoneme
identity, membership, document/split identity, every source/output hash,
deterministic regeneration, line/whitespace preservation, and all declared
contrasts passed.

The formal manifest SHA-256 is
`3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`;
config SHA-256 is
`648a0f68f3ad4dfcb057ca06b93d960a1cb1105844667c54144d28c7c9860478`;
implementation-file SHA-256 is
`9e3eb0705aac2c0f5164d79f7129188f289ba7e9e115094581ab6bcf62b33406`.
All four entries in the compact `SHA256SUMS` passed an independent post-run
check. Generated text and execution artifacts remain ignored; the tracked
formal checkpoint records the permanent interface/provenance. M0-prime is
complete and validated. S1M2 synchronization/readiness is next; P1c has not
started.

## 45. S1M2 synchronized and P1c-ready (2026-09-05)

S1M2 was rebuilt from updated `main` at
`bf3396e630f7b28ff3172bd765979e2f64c351bf`. The original P0 commit
`f95bc5f1bb92ce4beb899b13fa5a83070852d734` was replayed as `c976bdf`; the
original P1a/P1b commit `3d4c5127c74201fa22af5fbf1673faa4096aa456`
was replayed as `3ba3d80`. Their implementation/report content was preserved,
while their obsolete durable-state snapshots were resolved against current
S1M1/M0-prime state.

The old S1M2 base tracked `notes/reviewer/*`, but neither replayed commit
touches notes. The synchronized tree and `main...HEAD` delta contain no tracked
`notes/**`; no note was modified, copied, staged, restored, or checked out.

P0 provides the unchanged exact reference piece lattice, prior normalization,
forward/backward expected counts, and outer-to-inner count composition. P1a
provides normalized countable-base-measure scoring for active and unseen pieces
with fixed within-pass state. P1b provides lazy M1-equivalent lexical spans
without persistent lexical-edge tuples. All pieces remain untyped and
script-neutral; all paths concatenate exactly to the grammar-licensed lexical
form. No morphology/gold resource, internal rewrite, sandhi-use reward, or
change to the fixed external grammar was introduced.

The synchronized branch inherits S1M1 freeze and the validated six-cell
M0/M0-prime substrate. Focused pieces/profiler/M0-prime integration tests passed
(`48 passed`), and the complete repository suite passed (`616 passed`, four
existing warnings). P1c is not implemented. The exact next boundary is exact
shared/composed inference over lazy spans with P0/materialized oracle gates:

```text
S1M2 P1c READY TO START
```

## 46. Authorized S1M1 cleanup reconciliation (2026-09-05)

After the frozen deletion-readiness checkpoint, the researcher separately
authorized and manually performed cleanup of exactly the 12 files classified
`SAFE_TO_DELETE_REGENERABLE` in
`reports/core_methods/latent_lexicon/s1m1_deletion_readiness_20260903.json`.
A cheap read-only `Test-Path -LiteralPath` check over that existing manifest now
finds 0 present and 12 absent. No large artifact was rehashed, no source was
recreated, and no additional deletion was performed by repository tooling or
Codex. Historical checkpoint statements that no deletion had occurred describe
the state at checkpoint creation; this section records the later authorized
physical state and supersedes them for current-state purposes.

## 47. S1M2 P1c exact composed inference complete (2026-09-05)

The P1c production kernel is implemented in
`src/sktlm/pieces/composed.py`. It evaluates the complete P0 legal piece
support with direct position forward/backward DP, without constructing P0
`PieceLattice` objects. It composes those exact per-form partitions and
conditional piece counts with P1b lazy lexical spans, token DP, and outer
factor DP. It returns lexical and piece expected counts, identity/latent mass,
expected lexical tokens, boundary posteriors, rule usage, joint entropy, and
total posterior mass.

Piece scores and per-form results are shared within one immutable scoring pass
through LRU caches with independent finite entry and conservative
estimated-byte limits. Oversize entries are evaluated without retention. The
engine exposes lazy-span, factor/node, composed-state/transition, piece-score,
form-cache, store-lookup, eviction, oversize, entry, and byte-estimate counters.
Changing cache bounds cannot change support, scoring, ordering, or posterior
semantics; a new engine is required after every between-pass parameter update.

Tiny tests cover identity-only, alternative segmentations, whole-form versus
singleton competition, cross-form reuse, sandhi/avagraha ambiguity, visible
space, joined and no-space spans, M0-prime diphthong/hiatus and aspirate/C+h
contrasts, and matched Devanagari phonology. Direct form results match P0 and
complete lazy results match the materialized outer/P0 comparator at the
declared `rtol=1e-10`, `atol=1e-12` convention. The focused pieces/latent suite
passed (`70 passed`); the repository suite passed (`627 passed, 2 warnings`).

```text
S1M2_P1C=COMPLETE
P1C_P0_TINY_EQUIVALENCE=PASS
LAZY_MATERIALIZED_OUTER_EQUIVALENCE=PASS
EXPECTED_PIECE_COUNT_EQUIVALENCE=PASS
BOUNDARY_RULE_MASS_EQUIVALENCE=PASS
S1M2_TRAINER_INTEGRATION=READY_TO_START
FULL_M0_PROCESS_RUNNING=NO
```

## 71. Token-local lexical-form interning rejected (2026-09-06)

Candidate SHA `5560f620fadeea3947d90e83a00fbf9be7a567de` remained exactly
equivalent to optimization 10 across seven artifacts and 10,252 values per
frontend. It reduced `PhonologicalForm` initializations from 10,249 to 8,825
(`13.9%`), but the added tuple-key dictionary work made the profiled span path
`9.5%`/`27.1%` slower and the shared evaluator `4.4%`/`3.7%` slower. IAST and
Devanagari total-wall changes disagreed (`-7.7%` and `+5.5%`).

Because the intended mechanism regressed in both profiles, optimization 11
was rejected and normally reverted by SHA
`035802a5c8acf24291d5bb045d42d6b1d09072e1`; no repeat was run. Compact
evidence is `s1m2_continuous_optimization_11_v1.json`. Optimization 10 remains
the active implementation baseline.

```text
S1M2_OPTIMIZATION_10=ACCEPTED_ACTIVE_BASELINE
S1M2_OPTIMIZATION_11=REJECTED_REVERTED
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

## 72. Exact bounded Cartesian top-K merge implemented (2026-09-06)

Optimization 12 changes only bounded inspection presentation. For one lexical
span, the prior code materialized all `K x K` combinations of retained lexical
prefixes and retained piece segmentations before trimming to K. The candidate
treats each fixed-prefix segmentation row as already ordered under the exact
same score and full scientific tie key, then performs a heap k-way merge.

It retains at most K row heads and constructs at most K winning/next
extensions per span instead of K squared candidates. Prefix and segmentation
indices reproduce the former stable prefix-major order for identical full
keys. Exact partitions, expected counts, boundaries, rules, and complete
inference support are not involved. Shared/legacy top-path comparison now
covers both sandhi ambiguity and a longer continuous-like form. The complete
pieces/latent suite passes (`90 passed`). A fixed paired clean-SHA probe is
required before acceptance.

```text
S1M2_OPTIMIZATION_12=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 73. Exact bounded Cartesian top-K merge accepted (2026-09-06)

At candidate SHA `b0ed64869d1976e51aa841603dec6e5d63cc9a43`, the fixed paired
probe preserves all seven canonical artifacts exactly against optimization 10:
10,252 numeric values per frontend have zero difference. Lazy-token top-K
improves `57.4%` for M0-prime IAST and `47.5%` for M0 Devanagari; inspection
inference improves `5.3%`/`16.0%`, and total profiled calls fall `4.0%`.

Subsecond total-wall changes disagree (`+0.05%` improvement and `11.8%`
regression), so they are treated as noise. Acceptance rests on exactness,
strict finite bounds, and the reproduced targeted-phase reduction. Compact
evidence is `s1m2_continuous_optimization_12_v1.json`.

The cumulative factorization since the frozen optimization-7 representative
is now material: both training and inspection use the shared prefix route,
with `81.5%` fewer states and `78.3%` fewer transitions/score calls on the
fixed probe. Exactly one new detached paired representative attempt is now
justified. Stress, cloud scaling, and formal full-M0 remain forbidden.

```text
S1M2_OPTIMIZATION_12=ACCEPTED
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=READY_TO_LAUNCH_DETACHED
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 74. Factorized representative complete; bounded audit implemented (2026-09-06)

Detached attempt `s1m2_continuous_representative_factorized_v2_attempt01`
completed successfully at Git SHA
`8f694d64d350b1e7e2c882de3556d69bcda2b8db`. Durable state records exit zero,
both stderr logs are empty, provenance/config/checkpoints bind the expected
Git SHA, input hashes, one pass, and four workers, and both benchmark metrics
are present.

M0-prime IAST and M0 Devanagari wall times are 5,358.39 and 4,707.76 seconds
(1.488/1.308 hours), improving 48.4%/54.5% over the frozen optimization-7
representative. Both frontends traverse 6,886,648 legal span hypotheses per
phase, 5,448,470 shared states, and 39,051,167 transitions, with no shared
fallback. States fall 83.7% and transitions 80.4% relative to the old run.

Reconstructed three-pass-plus-inspection sample times are 2.299/2.043 hours.
The unchanged static multipliers give central phoneme projections of
232.8/206.8 hours and conservative squared-span projections of 303.2/269.4
hours. Runtime remains not ready by a wide margin. Output schemas are unchanged:
phoneme-scaled transient output remains 354.1/366.8 GiB and SQLite remains
147.8/156.5 GiB, so storage is not ready.

The artifact comparator now streams large JSONL and TSV inputs in deterministic
line/row order rather than materializing multi-gigabyte runs. Its focused test
passes, as do both historical cheap comparisons. A detached old-vs-new
same-frontend audit is required before promoting this representative result to
fully validated. No training or benchmark rerun is required.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_AWAITING_STREAMING_AUDIT
S1M2_BOUNDED_ARTIFACT_COMPARATOR=IMPLEMENTED_FOCUSED_PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
S1M2_CONTINUOUS_STRESS=DEFERRED_PENDING_STRUCTURAL_OPTIMIZATION
FULL_M0_PROCESS_RUNNING=NO
```

## 62. Continuous optimization 7 accepted; representative gate next (2026-09-05)

Candidate SHA `29c08a242bc4c4f65b39ddeebeb210c4bc45ccf3` keys the existing
bounded form-evaluation LRU by canonical `form.key`. The pieces/latent suite
passes (`83 passed`), all seven canonical artifacts remain byte-identical to
optimization 6 in both frontends, and profiled probe wall time improves
`3.9%`/`1.1%`. This small optimization closes the obvious cheap allocation
loop; exact span/form DP is now the dominant measured work.

The next gate is one detached paired local representative run at four workers
using the frozen document list. It is diagnostic and cannot satisfy the later
production-cloud representative/stress gate by itself.

```text
S1M2_OPTIMIZATION_7=ACCEPTED_SMALL
S1M2_CONTINUOUS_REPRESENTATIVE_LOCAL=READY_TO_LAUNCH_DETACHED
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 63. Local representative measurement exposes structural/runtime and storage failure (2026-09-06)

Detached attempt `s1m2_continuous_representative_local_v1_attempt01`
completed successfully at
`765742a1037ff2e1ef5dc267d300742ad84ef0c8`. It ran the frozen three-document
representative workload sequentially for M0-prime IAST and M0 Devanagari
continuous at local Windows w4, one pass plus final exact inspection. Both
stderr logs are empty and output config, manifest, checkpoint, provenance, and
benchmark identities validate. Do not rerun this attempt.

The two frontends have identical script-neutral work per phase: 6,886,648
outer span hypotheses, approximately 33.51 million composed states, and
approximately 199.68 million composed transitions. Piece inventory, lexical
diagnostics, and rule usage are byte-identical; summaries and iteration
metrics differ only in written character count. Representative cross-frontend
scientific identity therefore passes.

Elapsed time was 2.882/2.876 hours for only one pass plus inspection. A
three-pass-plus-inspection reconstruction on this same sample is 4.754/4.738
hours. Full-corpus projections are approximately 481/480 hours by phonemes and
627/625 hours by the conservative squared-span proxy. Final representative
artifacts are 2.43/2.52 GB and transient output is 3.75/3.89 GB; phoneme
scaling projects 354/367 GiB transient output per continuous cell. Parent-only
RSS is not process-tree evidence and does not close the memory gate.

The measured mechanism is repeated exact interval/form composition under
heavy bounded-LRU churn: roughly 1.95 million form-evaluation evictions and
3.96 million piece-score evictions per phase. The frozen stress and cloud
w4/w8 gates are deferred until exact structural inference and compact storage
work materially change this regime. This is not yet a scientific blocker
because semantics-preserving factorization has not been exhausted. Compact
evidence is tracked at
`reports/core_methods/reusable_pieces/evidence/s1m2_continuous_representative_local_v1.json`.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_LOCAL=COMPLETE_VALIDATED
CONTINUOUS_SCRIPT_NEUTRAL_REPRESENTATIVE=PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
S1M2_CONTINUOUS_STRESS=DEFERRED_PENDING_STRUCTURAL_OPTIMIZATION
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 64. Shared token-local form-prefix marginal DP implemented (2026-09-06)

Optimization 8 replaces independent inner-form training marginal DPs with one
exact token-local prefix DAG. Shared prefixes compute bounded-piece forward
values once; unchanged outer lexical masses seed a reverse adjoint pass that
aggregates exact piece counts and scalar marginals over every form endpoint.
Whole-form transitions remain endpoint-local. The graph is transient, capped
at 262,144 prefix nodes per token through an explicit engineering config, and
falls back to the prior exact implementation before shared scoring if the cap
would be exceeded.

The shared route is enabled only when inspection top-K is absent and
`piece_support_epsilon=0`; inspection and nonzero-threshold conditions retain
the existing exact path. At epsilon zero, finite legal transition weights make
positive occurrence support exactly structural. Shared/legacy tests cover all
scientific marginals and support, plus the bound fallback. The pieces/latent
suite passes (`87 passed`), including resume and serial/parallel equivalence.
The candidate is not performance-accepted until its clean-SHA fixed paired
probe completes.

```text
S1M2_OPTIMIZATION_8=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 65. Shared training marginal DP accepted (2026-09-06)

The optimization-8 fixed paired probe at
`2dad1b342042eb1ec9b282c3fd0d1798b363557e` passes semantic comparison against
optimization 7 over all seven canonical artifacts. Each frontend comparison
checked 10,252 numeric values under `rtol=1e-10`, `atol=1e-12`; the maximum
absolute/relative differences are `7.11e-14`/`2.84e-14`, and piece identities
plus occurrence support are unchanged.

Training composed states fall 81.5%, transitions and piece-score calls 78.3%,
and lazy traversals 66.7%. Training inference improves 70.3%/73.2% and complete
probe wall improves 19.0%/18.3%, with inspection deliberately unchanged. No
shared-prefix cap fallback occurred. Optimization 8 is accepted for training
marginals; inspection shared marginals/top-K transition reuse is the next exact
candidate. Evidence is
`reports/core_methods/reusable_pieces/evidence/s1m2_continuous_optimization_8_v1.json`.

```text
S1M2_OPTIMIZATION_8=ACCEPTED_TRAINING_ONLY
S1M2_OPTIMIZATION_9=SHARED_INSPECTION_MARGINALS_AND_TOP_K_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 66. Shared inspection marginals and top-K implemented (2026-09-06)

Optimization 9 routes exact inspection marginals through the accepted shared
prefix DAG. Bounded per-form piece top-K paths are reconstructed from the
already-scored shared transitions under the unchanged score and tie ordering;
long whole-form transitions remain endpoint-only. A config-recorded cap of
4,194,304 piece references per token is checked before shared scoring and
falls back to the existing exact implementation when exceeded.

Shared/legacy inspection tests match lexical and piece paths, probabilities,
scores, rules, boundaries, all exact marginals, and occurrence support. Both
finite-bound fallbacks pass, as do the complete pieces/latent tests (`89
passed`). The candidate requires the fixed paired probe at a clean Git SHA
before performance acceptance.

```text
S1M2_OPTIMIZATION_9=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 67. Shared inspection marginal/top-K reuse accepted (2026-09-06)

The optimization-9 paired probe at
`fc2b66babd0c77f1984679bedd01c965b1c79c32` passes the canonical semantic
comparator against optimization 8. Top lexical/piece path order and support
match; 10,252 numeric values per frontend remain within the frozen tolerance,
with maximum absolute/relative differences `1.67e-13`/`1.51e-14`.

Inspection states fall 81.5%, transitions and score calls 78.3%, and inspection
inference improves 54.1% in both frontends. Complete probe wall improves a
further 40.7%/35.5%; no cap fallback occurs. Optimization 9 is accepted. The
remaining per-endpoint bounded piece top-K should next be shared across prefix
states with a corrected total piece-reference cap. Evidence is
`reports/core_methods/reusable_pieces/evidence/s1m2_continuous_optimization_9_v1.json`.

```text
S1M2_OPTIMIZATION_9=ACCEPTED
S1M2_OPTIMIZATION_10=SHARED_PREFIX_TOP_K_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 68. Shared bounded piece-prefix top-K implemented (2026-09-06)

Optimization 10 computes the bounded normal-piece top paths once per shared
phonological prefix state, using the same destination-wise union and score/key
ordering as P0. A long whole-form piece is not stored on prefix state and is
added only at its exact endpoint. The inspection safety check now bounds
`top_k * sum(prefix_depth)` across all shared states, a conservative upper
bound on retained piece references; failure selects the legacy exact path
before shared score calls.

Shared/legacy nested path order, scores, probabilities, and all exact
marginals continue to pass, as do both finite fallbacks and the pieces/latent
suite (`89 passed`). The candidate requires its clean-SHA fixed paired probe.

```text
S1M2_OPTIMIZATION_10=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 69. Shared bounded piece-prefix top-K accepted (2026-09-06)

At candidate SHA `b19df311e3ca15cba40d9a2c29b993434ebb1d19`, both fixed
continuous probes preserve all seven canonical scientific artifacts exactly
against optimization 9: `10,252` numeric values per frontend have zero
absolute and relative difference. The shared recurrence retains 855 bounded
prefix states and 5,906 bounded top paths, with no cap fallback.

The targeted inner piece top-K phase improves `57.3%`/`58.0%`, and the
enclosing lazy-token top-K phase improves `42.0%`/`52.1%`. Devanagari total
wall improves `17.3%`; IAST total wall is flat within probe noise (`0.25%`)
while its inspection inference improves `7.9%`. Acceptance is based on exact
equivalence, finite fallback, and the reproduced targeted-phase reduction,
not on the noisy IAST total-wall value. Compact evidence is tracked in
`s1m2_continuous_optimization_10_v1.json`.

The representative result remains the valid performance gate for the old
regime and must not be rerun yet. The next measured exact work addresses
shared-batch/transient span construction or bounded outer path selection.

```text
S1M2_OPTIMIZATION_10=ACCEPTED
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

## 61. Continuous optimization 6 accepted (2026-09-05)

Candidate SHA `25fbeedc2afb84b868d35624ba5303310dcc574f` reuses immutable
piece-key tuples in the bounded inner inspection top-K. P0 ordered paths and
the focused pieces/latent suite pass (`83 passed`), and all seven canonical
artifacts remain byte-identical to optimization 5 for both frontends. Inner
top-K improved about `61%`; profiled wall time improved `7.2%`/`11.9%`.

The next measured exact candidate keys the existing bounded form-evaluation
LRU by `form.key` rather than repeatedly hashing its phoneme tuple. This is
local to P1c and avoids unsafe changes to global or cross-process form hashing.

```text
S1M2_OPTIMIZATION_6=ACCEPTED
S1M2_OPTIMIZATION_7=FORM_CACHE_CANONICAL_KEY_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 60. Continuous optimization 5 accepted (2026-09-05)

Candidate SHA `1c27eb02b0dd5db8d6fbc23d2707ee14fa0b8b82` delays piece-form
construction until an actual miss in the unchanged bounded score LRU. All
seven canonical probe artifacts are byte-identical to optimization 4 in both
frontends, the focused pieces/latent suite passes (`83 passed`), and cache
counters/gauges remain identical. Profiled wall time improved `20.5%`/`21.5%`,
with piece-transition construction `57--64%` faster.

The next exact candidate reuses the immutable inner piece-path key now rebuilt
135,550 times by inspection sorts. It remains bounded by the existing inner
top-K state and cannot affect exact marginal inference.

```text
S1M2_OPTIMIZATION_5=ACCEPTED
S1M2_OPTIMIZATION_6=INNER_PATH_KEY_REUSE_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 59. Continuous optimization 4 accepted (2026-09-05)

Candidate SHA `942007c231a14c73caa6441176c66cc7cec3ff32` stores the existing
deterministic composed-path tie key on each bounded transient inspection path.
All seven canonical probe artifacts are byte-identical to optimization 3 for
both frontends, and the focused pieces/latent suite passes (`83 passed`).
Profiled wall time improved `25.5%`/`20.9%`; lazy-token top-K improved
`78.3%`/`71.3%`.

The next measured target is constructing 25,135 piece forms before bounded
cache lookup when only 1,039 keys miss. Optimization 5 will key that same LRU
by the immutable symbol tuple and construct a form only on misses, without
changing cache bounds, ordering, scoring, legal support, or emitted identities.

```text
S1M2_OPTIMIZATION_4=ACCEPTED
S1M2_OPTIMIZATION_5=LAZY_PIECE_FORM_CONSTRUCTION_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 54. Continuous optimization 1 implemented and equivalence-validated (2026-09-05)

The first measured candidate retains the `PhonologicalForm` that
`LazyTokenLattice.span()` already constructs for legality validation inside the
transient `LazyLexicalSpan`. Repeated accesses during that one exact traversal
no longer reconstruct the same form. Spans remain iterator-local and are not
stored in the graph or across traversals, so legal support and P1b's
non-materialization contract are unchanged.

P0/P1c and trainer scientific equivalence tests remain green; the complete
pieces/latent suite passes (`82 passed`). The candidate requires the same fixed
paired probe from its own clean Git identity before acceptance.

```text
S1M2_OPTIMIZATION_1=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
FULL_M0_PROCESS_RUNNING=NO
```

## 55. Continuous optimization 1 accepted (2026-09-05)

At candidate SHA `d4e48735cefb9d25a057c40c1b12e811cc1afa32`, the fixed
paired cProfile probe retains all seven canonical scientific artifacts
byte-identically within each frontend. Wall time improved by 47.3% for
M0-prime IAST and 50.3% for M0 Devanagari; training inference improved about
57% and inspection inference about 38--41%.

The targeted mechanism improved directly: total calls fell 45.1%, form
initialization count fell 49.4%, initialization time fell 75.9%, and the former
lazy-span word-property hotspot disappeared. Optimization 1 is accepted. The
next measured target is transient reuse of exact piece transitions within one
per-form cache-miss evaluation; it must not persist P0 lattices.

```text
S1M2_OPTIMIZATION_1=ACCEPTED
S1M2_OPTIMIZATION_2=READY_TO_IMPLEMENT
FULL_M0_PROCESS_RUNNING=NO
```

## 56. Continuous optimization 2 implemented and equivalence-validated (2026-09-05)

Each per-form cache-miss evaluation now builds its exact legal piece
transitions once in original start/end order and reuses them across inner
forward, backward, posterior, singleton, and optional top-k passes. The
iterator-local table is discarded before return; it is neither a P0 lattice nor
a persistent candidate cache, and its size remains linear in form length times
the fixed piece bound plus the whole-form transition.

The complete pieces/latent suite passes (`82 passed`). Piece-score calls now
correctly satisfy `calls = hits + misses` without requiring within-form cache
hits. Scientific outputs and candidate support remain under the existing oracle
and trainer gates. A clean-SHA fixed paired probe is required for acceptance.

```text
S1M2_OPTIMIZATION_2=IMPLEMENTED_EQUIVALENT_AWAITING_FIXED_PROBE
FULL_M0_PROCESS_RUNNING=NO
```

## 57. Continuous optimization 2 accepted (2026-09-05)

Candidate SHA `407904ac8ed8196c7b676b7deab8b707a6f85e8d` preserves all
seven canonical scientific artifacts byte-for-byte against optimization 1 in
both continuous frontends. Profiled wall time improved another 59.4%/58.7%,
form initialization count fell 67.8%, and piece-score calls now occur once per
unchanged legal composed transition.

Optimization 2 is accepted. The remaining probe inspection profile is dominated
by top-k sorting/key allocation. Optimization 3 will batch the unchanged inner
piece-path sort/truncate once per destination position, with fixed piece-length
and top-k bounds and identical ordering.

```text
S1M2_OPTIMIZATION_2=ACCEPTED
S1M2_OPTIMIZATION_3=READY_TO_IMPLEMENT
FULL_M0_PROCESS_RUNNING=NO
```

## 49. Continuous benchmark selection rule frozen (2026-09-05)

Before observing any S1M2 continuous timing, the static selection algorithm
was frozen in `configs/benchmarks/s1m2_continuous_selection.json` and
`src/sktlm/latent/continuous_structure.py`. It reads exactly validated
M0-prime IAST `continuous` and frozen M0 Devanagari `continuous`, and requires
matched document membership plus per-document phoneme and ordered span-length
identity.

Selection is model- and runtime-free. Two stress documents are ranked by
maximum punctuation-free continuous span, then squared-span proxy and
phonemes. After removing them, representative documents are the nearest
distinct 25th/50th/75th percentile rows under squared-span proxy, maximum
span, phonemes, and relative-path tie break. The scanner also emits full
static totals needed for character-, document-, and span-weighted projections.

The selector's 26 focused static/frontend/M0-prime tests pass. The full
240-document/two-frontend scan has not yet run and is treated as a detached
workload. It is not model training and gives no full-M0 authority.

```text
CONTINUOUS_BENCHMARK_SELECTION_RULE=FROZEN
CONTINUOUS_STATIC_SCAN=READY_TO_LAUNCH
```

## 50. Continuous static scan complete and workloads frozen (2026-09-05)

Detached attempt `s1m2_continuous_structure_v1_attempt01` completed the paired
M0-prime IAST/M0 Devanagari structural scan at
`16c67d33a44d8cf651a795aa89a193490116af23`. The full output SHA-256 is
`03ebdf71afc80f82492d9d36cc593ab50c380fd3b0b57689862ea8e98c7b39f8`.
All 240 documents match exactly in frontend phoneme count and ordered nonempty
continuous-span lengths. The shared substrate has 46,255,133 phonemes,
1,261,507 spans, squared-span proxy 2,285,952,803, and document-maximum span
p50/p90/p95/p99/max 101/501/822/1,500/2,634.

The tracked representative list contains the fixed non-stress 25th/50th/75th
percentile structural ranks (456,891 phonemes; max span 85). The stress list
contains the fixed top two longest-span documents (62,748 phonemes; max span
2,634). Compact evidence is in
`reports/core_methods/reusable_pieces/evidence/s1m2_continuous_structure_v1.json`.

The child output is complete and valid. Task Scheduler reported a later
control-break and left the wrapper state stale at `RUNNING` after the child had
atomically written `complete.json`; empty stderr, complete stdout, hashes, and
identities establish completion. The wrapper anomaly is preserved and the
static scan must not be rerun. No S1M2 model benchmark or full-M0 run started.

```text
CONTINUOUS_STATIC_SCAN=COMPLETE_VALIDATED
CONTINUOUS_BENCHMARK_WORKLOADS=FROZEN
S1M2_CONTINUOUS_PROFILING=READY_TO_IMPLEMENT
```

## 51. S1M2 continuous detailed telemetry implemented (2026-09-05)

Before observing any S1M2 continuous model timing, the production path gained
bounded engineering-only histograms and subphase clocks. Fixed power-of-two
histograms summarize written/phoneme/token/span sizes and candidate work;
candidate profiling separates grammar matching, factor-window filtering, node
and lattice construction; composed inference separates inner piece, lazy-token,
factor-composition, and outer exact-DP phases. Nested timings may overlap their
enclosing totals and cannot feed scientific decisions.

Parallel training and inspection now expose the fixed `2 * workers` pending
limit, queue occupancy, completed-but-canonically-blocked shards, reducer stall,
and pending-shard bytes. SQLite database/WAL/shared-memory and near-final
artifact sizes have explicit high-water gauges. Production cloud profiling
will continue to obtain simultaneous process-tree RSS/CPU/I/O from the existing
Linux metrics wrapper.

Telemetry-on lazy graphs equal telemetry-off graphs, and the existing exact
inference and serial/parallel scientific equivalence tests remain green. The
focused pieces/latent suite passes (`80 passed`) and `git diff --check` passes.
No S1M2 model benchmark or full-M0 run has started.

```text
S1M2_CONTINUOUS_TELEMETRY=IMPLEMENTED_VALIDATED
S1M2_CONTINUOUS_CHEAP_PROFILE=READY_TO_RUN
FULL_M0_PROCESS_RUNNING=NO
```

## 53. Paired continuous probe baseline complete (2026-09-05)

At Git SHA `95f6029cc2e0e05852305cf7d4f511c064d60789`, the fixed
three-document/two-line, one-pass plus inspection probes completed under
`cProfile` for M0-prime IAST continuous and M0 Devanagari continuous. Wall
times were 19.088 and 18.629 seconds. These values are diagnostic only and
cannot project full-M0.

Both frontends produced identical phoneme/segment, lazy-span, composed-state,
and composed-transition work. Piece inventory, lexical diagnostics, and rule
usage are byte-identical; summaries differ only by written-character count.
The profile identifies repeated transient `PhonologicalForm` reconstruction as
the dominant first target: `LazyLexicalSpan.word` was called 193,077 times for
5.643 cumulative seconds, and form initialization used 7.001 cumulative
seconds. Candidate generation was negligible. The baseline compact envelope is
tracked under reusable-piece evidence; raw runs remain ignored.

```text
S1M2_CONTINUOUS_CHEAP_PROFILE=COMPLETE
CONTINUOUS_SCRIPT_NEUTRAL_PROBE=PASS
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 52. S1M2 continuous runtime benchmark contract frozen (2026-09-05)

The tracked runtime contract binds six benchmark IDs (probe, representative,
and stress for each valid continuous frontend) to the S1M2 model, exact
manifest path/hash, frozen document-list path/hash, frontend, condition, and
line bound. Probe IDs read the first two lines of every representative-list
document; representative and stress IDs read the complete frozen workloads.

The runner fails closed on hashes and excludes ordinary `iast`, so the invalid
original M0 IAST-continuous cell cannot be benchmarked accidentally. It records
the resolved contract in `benchmark_metrics.json`. Two contract tests pass,
including a deliberately invalid manifest hash; the current targeted telemetry,
trainer, and contract run passes (`9 passed`). No timing result has yet been
observed from the fixed probe.

```text
S1M2_CONTINUOUS_BENCHMARK_CONTRACT=FROZEN
S1M2_CONTINUOUS_CHEAP_PROFILE=READY_TO_RUN
FULL_M0_PROCESS_RUNNING=NO
```

## 48. S1M2 streaming trainer integration complete (2026-09-05)

The existing full-corpus-capable trainer now supports
`model=reusable_pieces_v1` without replacing the frozen S1M1 path. S1M2 uses
P1b lazy candidates and P1c exact inference directly. The neutral first pass
and each later SQLite-scored pass keep one immutable piece state; pass
finalization transactionally installs positive-count singletons plus pieces
meeting the configured distinct-occurrence reuse threshold. Inactive pieces
remain legal and receive the P1a countable-base-measure score. Lexical-form
expected counts are retained only as diagnostics.

Serial processing remains document-streaming and document-atomic. Parallel
workers emit checksummed lexical/piece shards, which are reduced in canonical
document order under bounded rolling submission. SQLite counts and the
durable checkpoint commit together. A fresh bounded P1c engine is constructed
after each between-pass update. Training performs no top-K decoding; bounded
piece paths are generated only for inspection.

The S1M2 artifacts include piece inventory/state/reuse/length/complexity,
lexical diagnostics, exact analysis and boundary/rule summaries, piece
ambiguity and memorization/atomization/composition masses, configuration,
provenance, checkpoint/history, SQLite state, engineering telemetry, and a
human report. Scientific output is byte-identical between serial/two-worker
runs and after a simulated interruption immediately following a durable
document commit. S1M1 config identity remains backward compatible because its
payload omits all newly added S1M2-only fields.

Focused pieces/latent tests passed (`76 passed`), and the repository suite
passed (`633 passed, 2 warnings`). The warnings are unchanged PyTorch warnings.
No production-shaped benchmark or full-M0 job has been launched.

```text
S1M2_TRAINER_INTEGRATION=COMPLETE
RESUME_EQUIVALENCE=PASS
S1M2_CONTINUOUS_PROFILING=READY_TO_START
FULL_M0_PROCESS_RUNNING=NO
```

## 58. Continuous optimization 3 accepted (2026-09-05)

Candidate SHA `e4ed01671a7c0ec027db46372680f5c6b90b176f` batches inner
piece-path sort/truncate once per destination after all incoming transitions
arrive. The unchanged deterministic ordering matches P0 ordered top paths,
weights, and probabilities. Exact partition and marginals are untouched, and
temporary work is bounded by fixed maximum piece length and inspection top-K.

The focused pieces/latent suite passes (`83 passed`), and all seven canonical
probe artifacts are byte-identical to optimization 2 for both continuous
frontends. Profiled wall time improved `10.5%`/`9.4%`, inner piece top-K time
improved `32.3%`/`34.3%`, and list-sort calls fell `78.2%`. The next measured
inspection hotspot is repeated `_ComposedPath` nested tie-key construction;
immutable transient key reuse is ready as optimization 4.

```text
S1M2_OPTIMIZATION_3=ACCEPTED
S1M2_OPTIMIZATION_4=COMPOSED_PATH_TIE_KEY_REUSE_READY
S1M2_CONTINUOUS_EXACT_OPTIMIZATION=IN_PROGRESS
FULL_M0_PROCESS_RUNNING=NO
```

## 70. Factorized representative audit comparator corrected (2026-09-06)

Detached read-only audit attempt
`s1m2_continuous_representative_factorized_audit_v1_attempt01` failed after
1.9 seconds at SHA `a0887bb33b1e5f2969123b105bff96a988d95706`, before a complete
large-artifact scan. It ran no training or inference. The streaming comparator
had accidentally made TSV row order significant, unlike the established
first-column keyed comparison contract; equal-count piece rows exposed the
regression immediately.

The comparator now uses a bounded temporary SQLite keyed join for TSV files,
while retaining line-streamed, order-sensitive JSONL comparison. Duplicate,
unexpected, and missing TSV identities fail closed. Its regression fixture
reverses TSV rows and passes. The failed attempt remains preserved; a new
attempt identity is required for the same frozen representative artifacts.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_AWAITING_STREAMING_AUDIT_RETRY
S1M2_BOUNDED_ARTIFACT_COMPARATOR=KEYED_DISK_BACKED_FOCUSED_PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

## 71. Factorized representative audit TSV typing corrected (2026-09-06)

Detached audit attempt
`s1m2_continuous_representative_factorized_audit_v1_attempt02` failed after
9m17s at SHA `5c47ecde4e1d369630856fe0a35e6a4278512588`, while comparing the keyed
piece inventory. It ran no training or inference and did not finish a complete
large-artifact scan. The literal piece spelling `nan` had been coerced to IEEE
NaN by the generic TSV parser; the underlying old/new rows have identical text
and only tolerance-scale differences in declared numeric columns.

The comparator now applies numeric parsing/tolerance only to explicit numeric
TSV headers. Text remains exact, including nonfinite-looking spellings. Equal
numeric nonfinite values are supported and unequal ones fail closed. This
schema typing composes with the bounded SQLite first-column join; three focused
regression tests pass. Attempt 02 remains preserved and attempt 03 must use a
new task/run identity against the unchanged frozen representative artifacts.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_AWAITING_STREAMING_AUDIT_ATTEMPT_03
S1M2_BOUNDED_ARTIFACT_COMPARATOR=SCHEMA_TYPED_KEYED_DISK_BACKED_FOCUSED_PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

## 75. S1M2 local optimization 13 accepted (2026-09-06)

Opt13 moves parallel inspection count, piece, surface, and context shard rows
from four text streams into one ordered append-only SQLite database per
document. Canonical document reduction and JSONL ordering are unchanged. The
parent attaches each shard and executes one transaction in SQLite, avoiding
central Python parsing and `PhonologicalForm` reconstruction; legacy text
shards remain readable for crash-resume compatibility.

The focused pieces/latent suite passes (`93 passed`). The one-shot bounded
400,000-row reducer measurement is exactly table-equivalent and improves from
11.885 to 5.429 seconds (`54.3%`), while shard bytes fall `11.4%`. The single
fixed Devanagari probe passes all seven canonical artifacts with zero numeric
difference across 10,252 values and improves total wall `2.2%`. No
representative or longer workload was run. Compact evidence is
`evidence/s1m2_local_optimization_13_v1.json`.

```text
S1M2_OPTIMIZATION_13=ACCEPTED
S1M2_OPTIMIZATION_14=READY
S1M2_LOCAL_OPTIMIZATION_ROUNDS_REMAINING=1
FULL_M0_PROCESS_RUNNING=NO
```

## 76. S1M2 local optimization 14 accepted; bounded task closed (2026-09-06)

After canonical S1M2 artifacts are written, Opt14 now removes six
reconstructible final-pass diagnostic/inspection tables and compacts
`learner.sqlite`. The completed persistent database retains only metadata with
the transactional checkpoint and the authoritative active `piece_lexicon`.
Every run records the separation in `storage_manifest.json`; scientific
support, weights, posteriors, outputs, and ordering are unchanged.

The focused pieces/latent suite passes (`93 passed`). The single fixed
Devanagari probe is exact across all seven canonical artifacts and 10,252
numeric values, reduces final artifact bytes `38.8%`, and shows no wall
regression. On a disposable copy of the completed factorized Devanagari
representative database, 1,470,657 active rows retain the identical ordered
digest while completed SQLite bytes fall from 1,221,271,552 to 69,447,680
(`94.3%`); compaction takes 74.5 seconds, `1.6%` of the prior representative
wall.

The measured compact ratio projects completed SQLite to `6.55 GiB` and total
completed output to `129.17 GiB` by the frozen phoneme multiplier. These are
bounded projections, not VM/full-corpus measurements. The pre-compaction
transient projection remains `366.69 GiB`, so the production storage gate is
still `NOT_READY`. No representative, VM, cloud, or full-M0 workload ran.
Compact evidence is `evidence/s1m2_local_optimization_14_v1.json`.

Opt13 and Opt14 are the last authorized local structural rounds and are both
resolved. Opt15 is not implemented. Reusing immutable lexical/piece-support
and shared-prefix topology across EM passes appears conditionally worthwhile,
provided a future design proves compact bounded storage and exact reweighting.

```text
S1M2_OPTIMIZATION_13=ACCEPTED
S1M2_OPTIMIZATION_14=ACCEPTED
S1M2_LOCAL_OPTIMIZATION_TASK=COMPLETE
S1M2_OPTIMIZATION_15=CONDITIONALLY_JUSTIFIED_NOT_IMPLEMENTED
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

## 72. Factorized representative audit manually reconciled (2026-09-06)

The factorized representative audit is scientifically closed from the
preserved attempt-03 evidence plus bounded manual continuation and diagnostic
scans. Attempt 03 remains historically `FAILED` because the strict
order-sensitive wrapper stopped during IAST `analyses.jsonl`; its state payload
also retains the copied internal `attempt: 2` field despite the distinct
attempt-03 task/run identity. Neither historical record is rewritten.

IAST reconciliation covers all seven canonical artifacts. A complete diagnostic
over all 12,306 analysis records compared 903,234 numeric values. Exactly 70
values exceeded the frozen `rtol=1e-10`, `atol=1e-12` gate, all in the derived
`piece_posterior.segmentation_entropy` field. No other scientific numeric
quantity exceeded the gate and no substantive structural divergence was found.
Five bounded top-K membership differences occur at records 1092, 1203, 1301,
1937, and 11353; each is a K=8 cutoff exact/near tie.

Devanagari SHA-256 triage showed that piece inventory, lexical diagnostics,
and rule usage are respectively byte-identical to the already audited IAST
reference/candidate sides. The four frontend-specific artifacts were scanned
once. Across 2,132,828 numeric values there are zero substantive structural
failures and zero scientific non-entropy numeric failures. The only two
non-entropy apparent differences are `lazy_span_traversals`, an engineering-only
key. The scan reproduces exactly 70 entropy exceedances and the same five top-K
membership records as IAST, plus 24 order-only top-K records.

The global comparator tolerance remains unchanged; JSONL order sensitivity is
not relaxed and no special entropy or top-K bypass is added. Scientific closure
is recorded by reconciliation evidence rather than by changing production
inference merely to force the historical wrapper to return zero.

The entropy-stabilization experiment (`9edfd7f`) and its cheap-probe acceptance
checkpoint (`20687a3`) were reviewed and reverted. Canonical evidence is
`evidence/s1m2_factorized_representative_reconciliation_v1.json`.

```text
S1M2_CONTINUOUS_REPRESENTATIVE_FACTORIZED=COMPLETE_RECONCILED
S1M2_FACTORIZED_REPRESENTATIVE_SCIENTIFIC_EQUIVALENCE=PASS_WITH_BOUNDED_PRESENTATION_CAVEATS
S1M2_REPRESENTATIVE_RERUN=FORBIDDEN_WITHOUT_NEW_CONTRADICTORY_EVIDENCE
S1M2_REPRESENTATIVE_AUDIT_RERUN=NOT_REQUIRED
S1M2_BOUNDED_ARTIFACT_COMPARATOR=SCHEMA_TYPED_KEYED_DISK_BACKED_FOCUSED_PASS
CONTINUOUS_RUNTIME_TARGET=NOT_READY
PRODUCTION_STORAGE_GATE=NOT_READY
FULL_M0_PROCESS_RUNNING=NO
```

## 77. S1M2 local optimization 15 accepted (2026-09-07)

Opt15 makes reconstructible S1M2 state follow bounded lifetimes. Each training
pass drops `piece_inventory` and `lexical_diagnostics` in the same transaction
that installs the active `piece_lexicon` and completed-pass checkpoint. Each
parallel inspection shard is deleted after successful canonical reduction;
after interruption, missing shards are deterministically regenerated from the
frozen input and durable active piece state. S1M1 remains unchanged.

The focused pieces/latent suite passes (`95 passed`), including interruption
after durable pass-state retirement and after inspection-shard retirement. A
24-document, two-worker Devanagari lifecycle benchmark preserves all seven
scientific artifacts byte-for-byte and reduces measured peak bytes from
3,738,727 to 2,247,509 (`39.9%`); candidate wall is lower in the single bounded
pair. The one fixed Devanagari probe is exact across 10,252 numeric values. Its
+0.195 second one-shot subsecond wall shift is recorded as noise and was not
rerun.

A read-only audit on a disposable copy of the existing factorized Devanagari
representative database measures 533,065,728 bytes of training diagnostic
tables, 617,578,496 bytes of inspection indexes, 70,627,328 bytes of active
state, and 930,493,404 bytes of accumulated inspection shards. Conservatively
retaining the historical WAL projection and allowing an eight-worker bounded
pending window gives `229.86 GiB`, down `37.31%` from `366.69 GiB`. This is
`PROJECTION_NOT_VM_OR_FULL_CORPUS_MEASUREMENT`; it is below the 300 GiB host
limit but still requires later VM measurement. Evidence is
`evidence/s1m2_local_optimization_15_v1.json`.

```text
S1M2_OPTIMIZATION_15=ACCEPTED
S1M2_OPTIMIZATION_16=READY
PRODUCTION_STORAGE_GATE=PROJECTED_BELOW_300_GIB_NOT_VM_MEASURED
FULL_M0_PROCESS_RUNNING=NO
```

## 78. S1M2 local optimization 16 accepted; local optimization stopped (2026-09-07)

Opt16 separates immutable S1M2 inference topology from mutable model state.
Training pass 1 compiles score-free candidate/form support and shared
piece-prefix transitions into compact document-local archives. Later EM passes
and final inspection stream one bounded segment record at a time and exactly
reweight it from the current authoritative piece parameters. Piece scores,
segmentation-prior weights, forward/backward vectors, posteriors, expected
counts, and top-K score state are never persisted in the topology cache.

The focused pieces/latent suite passes (`96 passed in 17.69s`). It includes an
explicit changed-parameter reweight-versus-rebuild test, archive lifecycle,
interrupted resume, durable pass/shard retirement resume, and serial/parallel
scientific identity. The final bounded 3-document/64-line measurement compares
154,136 values exactly. Against four legacy rebuilds, avoidable topology
lifecycle overhead falls from 1.368 to 0.520 seconds (`61.99%`), the all-in
compile/archive/decode/reweight lifecycle improves `21.26%`, and piece-score
calls fall `83.80%`.

The bounded archive is 995,862 bytes (3.149 bytes per transition). Frozen
phoneme scaling projects compiled full-corpus topology at `11.60 GiB`; adding
it to the accepted Opt15 bound raises the transient projection from `229.86`
to `241.46 GiB`. This remains below the 300 GiB host limit and is explicitly
`PROJECTION_NOT_VM_OR_FULL_CORPUS_MEASUREMENT`.

The one allowed fixed Devanagari probe passes all seven canonical artifacts
exactly across 10,252 numeric values. Its wall changes from 0.985 to 1.007
seconds; the +0.022 second one-shot subsecond shift was not repeated. No
representative, stress, VM, cloud, six-cell, or full-M0 workload ran. Evidence
is `evidence/s1m2_local_optimization_16_v1.json`.

Opt15 and Opt16 are both accepted. Current evidence exposes no further obvious
structural local optimization target, so the stopping decision is
`STOP_LOCAL_OPTIMIZATION`; Opt17 must not be opened. VM worker scaling,
scheduling, and production readiness remain separate future work requiring
explicit authorization.

```text
S1M2_OPTIMIZATION_15=ACCEPTED
S1M2_OPTIMIZATION_16=ACCEPTED
S1M2_LOCAL_OPTIMIZATION_TASK=COMPLETE
S1M2_LOCAL_OPTIMIZATION_RECOMMENDATION=STOP_LOCAL_OPTIMIZATION
PRODUCTION_STORAGE_GATE=PROJECTED_BELOW_300_GIB_NOT_VM_MEASURED
FULL_M0_PROCESS_RUNNING=NO
```

## 79. Generic Windows Codex automation framework complete (2026-09-07)

The bounded-task Windows automation logic is now task-independent and tracked
under `.codex/automation/`. `install_task.ps1` performs fail-closed repository,
remote, CLI, task-inventory, and runtime-root preflight; freezes initial/resume
prompts; writes schema-versioned config/state under ignored
`artifacts/codex_automation/<automation_id>/`; and registers the fixed anchored
schedule without an immediate start unless `-StartNow` is explicit.

`run_task.ps1` uses both a named mutex and Task Scheduler
`MultipleInstances IgnoreNew`. Every wake requires the expected clean branch,
a HEAD descended from the installed base, exact local/remote equality, and
unchanged prompt hashes. A new thread is created only when `thread_id` is null;
all later wakes construct exact-ID resume and reject any observed mismatch.
`resume --last` is never constructed. Unique per-wake JSONL, stderr, and final
message logs feed a strict final-marker parser. `CONTINUE` stays active;
`WAITING_EXTERNAL`, `COMPLETE`, and every invalid/failure phase disable the
task. State replacement uses same-directory atomic file replacement.

`control_task.ps1` exposes read-only `Status`, an extra manual `Wake` that
never changes trigger definition, and `ResumeExternal`, which requires
`WAITING_EXTERNAL`, preserves the stored exact thread ID, atomically returns
to `ACTIVE`, enables the unchanged task, and optionally performs one extra
wake. The ASCII-only framework parses under Windows PowerShell 5.1. The final
focused dry-run/state suite passes seven contract groups in 1.644 seconds,
including fixed 301-minute scheduling, exact resume construction, all three
valid status transitions, invalid-marker fail-closed behavior, atomic state
replacement, and disposable installer output. It registered no Scheduled Task
and started no Codex automation.

The three historical `notes/planned_ps1/**` implementations were inspected
read-only and were not modified. No scientific source, benchmark, VM, cloud,
representative, stress, or full-M0 workload was touched. This closes only the
generic infrastructure prerequisite; S1M2 Pre-VM Closure itself remains
`NOT_STARTED`. The next action is researcher installation through the generic
installer, not autonomous continuation.

```text
GENERIC_CODEX_WINDOWS_AUTOMATION=COMPLETE
S1M2_PREVM_CLOSURE=NOT_STARTED
S1M2_PREVM_NEXT_ACTION=RESEARCHER_INSTALLS_GENERIC_TASK
ACTUAL_SCHEDULED_TASK_CREATED=NO
CODEX_AUTOMATION_STARTED=NO
```

## 80. Generic Windows Codex automation infrastructure repaired (2026-09-07)

The installed Codex CLI is `codex-cli 0.153.2`. Its `--approve-for-me` option
already selects the workspace-write sandbox and cannot be combined with
`--sandbox`; the generic launcher now uses `--approve-for-me` alone for both
new and exact-ID resume invocations. It still forbids `resume --last` and the
dangerous approvals/sandbox bypass.

Installer coexistence is now based on the Scheduled Task runner action, config
path, and repository identity instead of the broad `SKTLM-*` prefix. Exact
TaskName and runtime-root collisions still fail closed. Historical one-shot
tasks and installed READY/ACTIVE generic peers are not treated as running merely
because they exist. The runner retains the per-task mutex and adds a deterministic
canonical-repository mutex; same-repository contention skips one wake without
changing healthy state, while different repositories remain independent.

`control_task.ps1` adds restricted `RecoverPreThread`. It accepts only a
disabled `LAUNCHER_ERROR` with an empty thread ID, prior launch logs proving no
thread or last message, unchanged frozen prompt hashes, a clean compatible HEAD
equal to the configured remote ref, and exact Scheduled Task action/config/repo
and fixed-trigger identity. Recovery atomically returns state to READY, enables
the existing task, preserves TaskName/automation ID/config/thread/anchor/interval/
trigger, and performs an immediate extra wake only when `-StartNow` is explicit.
`WAITING_EXTERNAL` and `COMPLETE` semantics are unchanged.

All four framework scripts and the focused suite parse under Windows PowerShell
5.1. The single focused suite passes 12 contract groups in 4.096 seconds; it
created no actual Scheduled Task and invoked no Codex automation. The existing
`SKTLM-S1M2-PreVM-Closure` runtime was inspected read-only: its task is Disabled,
state is `LAUNCHER_ERROR`, `thread_id` is null, JSONL is empty, no last-message
file exists, both prompt hashes match, and action/config/repo/trigger identity
matches. It is eligible for `RecoverPreThread` once the repaired commit is clean
and pushed, but this repair did not recover, enable, start, or wake it. No
scientific, VM, representative, stress, or full-M0 work ran.

```text
GENERIC_CODEX_WINDOWS_AUTOMATION=COMPLETE_REPAIRED
S1M2_PREVM_CLOSURE=NOT_STARTED_INSTALLED_PRETHREAD_FAILURE
S1M2_PREVM_RECOVER_PRETHREAD=RESEARCHER_ACTION_REQUIRED
ACTUAL_SCHEDULED_TASK_CREATED_BY_REPAIR=NO
CODEX_AUTOMATION_STARTED_BY_REPAIR=NO
```

## 81. Generic automation continuation contract repaired (2026-09-08)

The generic Windows runner now persists a unique `thread.started` ID atomically
while the native Codex process is still running and performs another JSONL
salvage before handling abnormal exit. Codex runs through a small PowerShell
5.1 native wrapper so stderr text cannot become a terminating launcher
exception and the real native exit code is retained. Once a thread exists,
quota, CLI/transport, or nonzero-exit interruption becomes
`INTERRUPTED_RECOVERABLE`; the task stays enabled and the next fixed wake uses
the same exact thread ID. `resume --last` remains impossible.

NEW threads still require a clean local/remote-equal checkout. Established
threads instead checkpoint a deterministic fingerprint covering tracked
unstaged diff, staged diff, and paths/lengths/content hashes of all non-ignored
untracked files, plus local and remote HEAD. Unchanged dirty state and an
unchanged recorded local-ahead `(local, remote)` pair may exact-resume. Any
between-wake workspace, local-HEAD, or fetched remote-HEAD change fails closed;
ignored automation/runtime artifacts do not enter the fingerprint.

`WAITING_DETACHED` now records an immutable artifacts-local manifest with job,
command, process, PID/start-time, completion/result, and exit-status identity.
Scheduled polling verifies the workspace and job identity without invoking
Codex while the job runs. Success, explicit failure, or a lost/reused process
identity is recorded and exact-resumes the original thread once. Existing
`WAITING_EXTERNAL` and `COMPLETE` disabling semantics are unchanged.

The legacy PreVM JSONL contains one salvageable thread ID,
`01a07c3d-47bd-7983-8171-90383489ae1f`, although its old state remains
`LAUNCHER_ERROR` with null `thread_id`. `RecoverInterrupted -AdoptWorkspace`
can explicitly adopt the current dirty PreVM work as this exact thread's
checkpoint, preserve the fixed trigger, and optionally add a `-StartNow` wake.
The runtime/task/prompt/branch/base identities pass a read-only assessment, but
the repair did not execute recovery, enable the task, start Codex, or modify the
PreVM work.

Windows PowerShell 5.1 static parsing passes for all framework scripts and the
focused test file. The single focused suite passes 17 contract groups in 6.504
seconds, including native stderr/exit handling, thread salvage, dirty/staged/
untracked fingerprints, unchanged local-ahead continuation, detached running/
success/failure outcomes, and legacy recovery planning. It created no real
Scheduled Task and invoked no Codex.

```text
GENERIC_CODEX_CONTINUATION_CONTRACT=COMPLETE_REPAIRED
S1M2_PREVM_THREAD_ID=01a07c3d-47bd-7983-8171-90383489ae1f
S1M2_PREVM_RUNTIME=LEGACY_INTERRUPTED_RECOVERABLE
S1M2_PREVM_RECOVERY=RESEARCHER_ACTION_REQUIRED
ACTUAL_PREVM_WAKE_STARTED_BY_REPAIR=NO
SCIENTIFIC_WORK_MODIFIED_BY_REPAIR=NO
```

## 82. S1M2 pre-VM production interface closed (2026-09-08)

The bounded pre-VM implementation is complete on branch
`exp/s1m2-reusable-pieces`. Its tested implementation identity is
`baa14f7ce1fed04397a68dd41c9c299c07a50100`; the final published pre-VM
identity is the later documentation/evidence commit containing this section.
The authoritative machine-readable contract is
`configs/production/s1m2_six_cell.json`, with canonical JSON SHA-256
`59d276c96adb08da9715dd872edb284bd776be7b412aee3822204613f68a9631`.

The production universe is frozen at six cells. Five consume frozen M0; IAST
`continuous` consumes only the validated M0-prime representation through the
`iast_m0_prime` frontend. Original M0 IAST `continuous` remains excluded and
cannot be selected through the contract. All cells retain the accepted exact
S1M2 scoring, candidate, grammar, posterior, and inspection semantics. Worker
count is engineering-only.

Opt16's cache contract is now operationally closed. Missing archives and
narrowly classified magic/header/identity/truncation/decompression/record/
structural failures trigger one deterministic rebuild from frozen input and
fixed structural configuration, atomically replace only the reconstructible
archive, reopen, and continue at the same document-local record. Unexpected
exceptions fail loudly. Focused missing-before-later-pass and
truncated-before-inspection tests preserve every canonical scientific artifact
byte-for-byte and confirm that no mutable score or posterior is restored.

The unified `sktlm-s1m2-production` control plane supplies contract validation,
Round 1/bounded/Round 2/final plan generation, explicit run/resume, audit,
Round 1 aggregation/winner selection, and Round 2 gate evaluation. Generated
plans bind a clean Git SHA, branch, contract and input hashes, exact trainer and
audit/resume commands, scientific/engineering configuration, run/metrics IDs,
logical host, and output paths. The runner reuses the existing exact trainer
and Linux `/proc` metrics wrapper. Process-tree/main/worker RSS, sampled CPU
and I/O, filesystem headroom, and run/SQLite/WAL/SHM/topology/pending-shard
high-water marks remain engineering-only telemetry.

Round 1 is exactly one M0 Devanagari-continuous engineering calibration
workload: 72 deterministic static-pressure strata, both frozen stress documents
excluded, three passes, and at most 256 lines per document. It runs at workers
4, 8, 12, 16, 20, and 24 concurrently on physical roles `core-01` through
`core-06` in that order. It does not redefine the frozen representative or
stress workload. Its aggregator uses compact per-host formal-audit attestations
while full run artifacts remain remote, and retains the frozen
direct >=10% wall winner rule and the resource tie rule in Decision 109. Round
2 consumes that result artifact and maps its six frozen readiness jobs in
contract order to the same six roles, all using `WINNER_WORKERS`. Only all PASS
gates can generate the six-cell full launch plan; plan generation never starts
production. The tracked cloud registry holds all 18 planned identities without
real host/IP/credential material.

The final focused gate passes `94 passed in 11.66s`; the full repository gate
passes `687 passed, 2 warnings in 50.52s`. A clean-SHA Round 1 dry run emits
exactly six jobs with worker vector `4,8,12,16,20,24`, one scientific
configuration, and complete launch/resume/audit commands. The clean-SHA bounded
production-path run executes one frozen document line, one pass, and one worker
for all six cells in 2.91 seconds. All six artifact audits pass. Its explicit
script-neutral gate passes all three matched conditions by byte identity of
piece inventory, lexical diagnostics, and rule usage. This is interface
evidence only, not representative timing or scientific evidence. Compact
machine-readable evidence is `evidence/s1m2_prevm_closure_v1.json`.

No representative, stress, VM, cloud, or full-M0 workload was launched. Opt17
remains unauthorized; no frozen M0/S1M1 byte, rule inventory, candidate support,
scoring equation, or `notes/**` path changed. The only next action is the
documented manual six-host preflight/deployment sequence from the final clean
pushed pre-VM SHA, followed by parallel Round 1 launch.

```text
S1M1=FROZEN
M0_PRIME=COMPLETE_VALID
S1M2_METHOD=COMPLETE
S1M2_LOCAL_OPTIMIZATION=COMPLETE
S1M2_OPTIMIZATION_16=ACCEPTED
OPT16_TOPOLOGY_RECONSTRUCTIBILITY=PASS
OPT17=NOT_AUTHORIZED
S1M2_SIX_CELL_CONTRACT=FROZEN
ROUND1_INTERFACE=READY
ROUND1_AGGREGATOR=READY
ROUND2_INTERFACE=READY
ROUND2_GATES=READY
PROVENANCE=READY
FINAL_SIX_CELL_GENERATOR=READY
S1M2_SIX_CELL_BOUNDED_VALIDATION=PASS
PRE_VM_INTERFACE_STATE=READY
ROUND1_STATUS=NOT_STARTED
ROUND2_STATUS=NOT_STARTED
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=MANUAL_VM_ROUND1
```
## 83. Generic cloud experiment contract merged into S1M2 (2026-09-08)

The shared cloud control plane is now experiment-neutral without discarding
the stronger existing SSH argv isolation, filesystem/mount/path guards,
resumable rsync and collection identity, receipt redaction, remote audit, or
downloaded hash comparison. `src/sktlm/cloud/contracts.py` owns a strict
tracked contract for branch, deployment transport, frozen input sets, remote
roots, audit/completion identity, collection profiles, and host assignments.

The bridge has no default experiment branch. A tracked `--contract` binds the
branch and refuses conflicting local configuration. `git_remote` keeps the
legacy clean/published/exact-HEAD fast-forward path; `git_bundle` verifies the
local bundle and contained HEAD, transfers it below the guarded data mount,
verifies SHA-256 and `git bundle verify` remotely, and performs only an exact
fast-forward update. Contract-driven input sync and audited collection reuse
the established no-delete, deterministic, fail-closed primitives. Baseline
matrix, baseline audit adapters, baseline configs, and baseline scientific
logic were not copied into `main`.

Focused contract tests pass (`9 passed`); the complete cloud suite passes
(`61 passed`). No SSH, SCP, rsync, VM, benchmark, representative, stress, or
full-M0 operation ran.

## 84. Opt17 compact occurrence support implemented (2026-09-09)

After external Round 1 stopped on single-worker OOM, Opt17 was explicitly
authorized as a representation-only change. The shared zero-epsilon route now
stores each positive form occurrence once as packed integer surface
coordinates plus the form's legal-piece relation, then computes exact
per-piece cardinalities after segment-level form/coordinate deduplication. The
legacy nonzero-epsilon weighted occurrence maps are unchanged, merged-word
support stays on that path, and mixed shared/legacy fallback unions preserve
the former string identity exactly.

The only local validation command selected four focused tests and passed
(`4 passed, 19 deselected in 0.40s`). No benchmark, representative, stress,
VM/cloud, Round 1/2, production-like RAM probe, or full-M0 workload ran.
Scientific artifact comparison and the less-than-10-GiB single-worker target
remain pending collaborator validation.

```text
ROUND1_STATUS=FAILED_OOM
POST_OPT16_ENGINEERING_OPTIMIZATION=AUTHORIZED
SINGLE_WORKER_PEAK_RSS_TARGET=<10GiB
OPT17=IMPLEMENTED_AWAITING_MANUAL_VALIDATION
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=COLLABORATOR_RUN_EXACTNESS_AND_SINGLE_WORKER_MEMORY_PROBES
```

## 85. Opt18 training/inspection split and inspection working-set bound (2026-09-09)

The collaborator's Opt17 exact artifact comparison passed, so no scientific
blocker was found. Its single-worker Devanagari-continuous stress run completed
one requested training pass and entered final inspection, where RSS exceeded
6.5 GiB and continued rising until manual interruption. A read-only audit found
identical database and JSON checkpoints, `completed_passes=1`, no active pass or
next-pass table, and exact agreement between `piece_lexicon` count/total and the
final checkpoint history. Partial `.tmp` inspection streams and reconstructible
inspection tables exist, while no canonical completion is claimed. The learned
Opt17 state is reusable without another training pass.

Opt18A adds phase-separated execution to both trainer and benchmark CLIs:
`--stop-after-training`, `--inspection-only`, and `--inspection-workers N`.
Inspection worker count is deliberately absent from `TrainingConfig.payload()`
and its signature; the original `--workers` remains the training identity. The
inspection-only route requires an existing exact config signature and training
provenance, identical SQLite/JSON checkpoints, completed requested passes, no
active progress, matching iteration history, no next-pass tables, and a final
learned table whose count/total matches the checkpoint. It never calls the
training pass. Existing `provenance.json` is retained byte-for-byte, while
atomic `inspection_provenance.json` records the training commit, inspection
implementation commit, both worker counts, mode, attempt, status, and final
artifact hashes. Interrupted inspection tables/streams are reset or regenerated
through the existing reconstructible shard/topology path; checkpoint completion
is written only after canonical artifacts and S1M2 compaction succeed.

Opt18B removes the observed inspection retention multipliers without changing
scoring or support. Shared inner top-K states now retain one piece plus a shared
predecessor backpointer instead of duplicating complete piece/key tuples at
every prefix; the existing bound now counts the actual live one-piece path
records. Token-local endpoint segmentation caching is explicitly entry/byte
bounded. Structural occurrence summaries retain form plus packed coordinates,
not a materialized legal-piece tuple per form; exact legal support is cheaply
reconstructed one form at a time during cardinality reduction. During
inspection, the outer DP first retains only factor/scalar scores, then exactly
recomputes, consumes, and releases each factor posterior immediately, retaining
only bounded local presentation paths for final top-K. Training has no
presentation top-K and retains its original single evaluation pass, preventing
a corpus-scale CPU regression.

A raw read-only audit of the topology record immediately after the 19 emitted
inspection rows identifies the concrete stress trigger. Document 0 line 39 has
one factor, 88,398 prefix nodes, 34,602 lexical forms, and prefix-depth sum
16,069,373. The old eager top-K representation projected 128,554,984 piece
references, exceeded its 4,194,304 bound, and forced exact legacy inference;
that route rematerialized the large occurrence/top-K payload Opt17 had avoided
on the shared route. Compact backpointers need only 707,184 actual one-piece
path records for this topology, remain below the same bound, and preserve the
shared path. The retained all-factor summary tuple was also corrected as a
general risk, but was not the stress-specific multiplier because the failing
continuous segment contains only one factor.

Exactly one allowed focused pytest command ran. It reported `6 passed, 2 failed,
25 deselected in 2.23s`; both failures were the same new fail-closed scalar-score
assertion. The score-only helper had evaluated `alpha + prior + piece_score`
with a different floating-point association than the original
`alpha + (prior + piece_score)`. That operation was corrected to reuse the
original `raw_score = prior + piece_score` order. Per instruction, pytest was
not invoked a second time. Post-correction Python compilation and Git diff
checks pass. No artifact comparator was rerun, and no stress, representative,
72-document, three-pass, VM/cloud, Round 1/2, production-like, or full-M0 run
was launched.

```text
OPT17=EXACTNESS_PASS_RAM_FAIL_DURING_INSPECTION
OPT17_TRAINING_STATE=REUSABLE
OPT18A=IMPLEMENTED
OPT18B=IMPLEMENTED
TRAINING_INSPECTION_PROVENANCE=SEPARATE
SINGLE_WORKER_PEAK_RSS_TARGET=<10GiB
SINGLE_WORKER_PEAK_RSS_VALIDATION=PENDING_COLLABORATOR
ROUND1_STATUS=FAILED_OOM
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=COLLABORATOR_RESUME_EXISTING_OPT17_STATE_INSPECTION_ONLY_W1
```

## 86. Consolidated Opt17 / Opt18 / Opt19 engineering closure (2026-09-09)

Opt17 solved training RAM: the Devanagari-continuous stress run stayed around
0.2--0.3 GiB RSS with a transient peak around 0.79 GiB. Inspection nevertheless
continued rising past 6.5 GiB and was manually interrupted. Its completed,
internally consistent training state remains directly reusable.

Opt18 decoupled training and inspection and repaired the inspection working set
with bounded memory. Pathological stress line 39 completed. At line 47,
elapsed time was 00:22:33, RSS was 0.708 GiB, and peak process-tree RSS was
0.747 GiB; memory later returned to about 0.44 GiB. The attempt was stopped
after more than two hours before its first stress document completed. Opt18
therefore closes the RAM gate but fails the runtime gate.

Opt19 retains exact one-pass `_FactorSummary` payloads adaptively. Admission is
deterministic canonical factor order under a 320 MiB segment-local cumulative
logical budget. The fixed `sktlm-opt19-factor-summary/v1` formula charges prefix
nodes, transitions, prefix-depth sum, forms, pieces, an upper bound on occurrence
slots, lattice nodes, and bounded top-path records. Missing or structurally
inconsistent topology, non-shared/nonzero-epsilon conditions, arithmetic
overflow, the existing shared top-K bound, and insufficient remaining budget
all fail closed to Opt18 score-only prepass plus exact posterior recomputation
and immediate release.

Only the returned factor scalar/posterior summary, compact form/coordinate
support, boundary/rule maps, and bounded final top paths may survive through the
outer DP. Shared-batch alpha and transition arrays, prefix backpointers, and
span tables remain factor-local. Scoring, posterior, support, expected counts,
boundary mass, top-K ordering, and floating-point association are unchanged.
The budget is excluded from the scientific training payload/signature and is
recorded only in inspection execution provenance and benchmark metrics, so the
preserved Opt17 learned state remains directly reusable.

Telemetry now reports inspection fast-path factors, two-pass factors,
recomputed factors, and retained-budget peak bytes. The one focused pytest
invocation passed (`3 passed in 2.49s`), including exact equality between the
all-fast and all-two-pass routes, cumulative-budget behavior, fail-closed
missing-topology behavior, unchanged training identity, and inspection-only
provenance/restart. Python compilation and `git diff --check` passed afterward.
No stress, representative, full-M0, VM/cloud, or training workload ran.

Subsequent manual synthetic mixed-path exactness validation passed with
factors=4, fast_path=1, two_pass=3, recomputed=3, budget=32678, and
retained_budget_peak=32678. All scientific outputs were exactly equal to the
forced two-pass route.

The targeted stress run reached line 47 at elapsed=00:10:39, RSS=0.362 GiB,
and peak RSS=0.659 GiB. Relative to Opt18 at line 47, observed wall time fell
by about 52.8%. Opt18 ran with profiling while Opt19 did not, so this is an
engineering runtime gate rather than a rigorously isolated speedup measurement.
Opt19 closes local exactness, RAM, and runtime gates. The pre-VM engineering
state is ready, and the sole next action is VM Round 1.

```text
OPT17=TRAINING_RAM_PASS_INSPECTION_RAM_FAIL_STATE_REUSABLE
OPT18=RAM_PASS_RUNTIME_FAIL
OPT19=LOCAL_EXACTNESS_PASS_RAM_GATE_PASS_RUNTIME_GATE_PASS
OPT19_DEFAULT_SEGMENT_RETAINED_BUDGET_BYTES=335544320
OPT19_TRAINING_IDENTITY_UNCHANGED=PASS
PRE_VM_ENGINEERING_STATE=READY
ROUND1_STATUS=FAILED_OOM
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=VM_ROUND1
```

## 87. S1M2 segment-bundle execution scheduler (2026-09-09)

The pre-full unit-granularity audit confirmed that the existing trainer
ObservedSegment can remain the indivisible scientific unit. The tracked
planner now calls the trainer's canonical document-segment iterator directly
and records a stable planner implementation identity. The selected full
M0/Devanagari/continuous plan remains candidate_008192, with 8,479 bundles,
scan signature
73ea0638684ba1fa249fa9c802837c26f334b4efa0657efb18ad3f2bcc5e252e,
and plan SHA-256
7acf4b292adffe35dcdbdf3755c18d699b5659bb806ad2c7342a03db5d4279c9.

S1M2 parallel training may explicitly consume a validated execution-only plan;
omission preserves the legacy document scheduler. Bundle workers process only
complete contiguous ObservedSegment ranges. They emit per-segment exact float
records and temporary pass-1 topology fragments. Completed futures are removed
from true inflight state immediately and trigger refill, while completed
results wait independently in ready state. The parent coalescer restores the
original canonical segment left fold into the existing document shard, forms
the unchanged document topology archive in line_number/segment_index order,
and then uses the existing document transaction, apply, and checkpoint path.
Pass 2+ validates or reconstructs the immutable document archive before
concurrent range reads and reuses its pass-1 topology without recompilation.

Current-attempt bundle markers bind the config signature, materialized plan
identity, pass, document, bundle range, and checksums. Resume reuses valid
completed bundles for the current document, never reapplies a committed
document, and rejects changed plans or stale bundle shards. The plan path and
retention mechanics are excluded from scientific training identity but are
recorded in execution provenance and the durable active checkpoint.

Tiny tests establish planner/trainer segment identity, exact-once contiguous
coverage, legacy-vs-bundle exact learned state and pass metrics, identical
decoded topology contents/order, refill past an early incomplete future, reuse
of completed bundle shards after interruption, single document application,
and fail-closed plan mismatch. The first targeted invocation exposed only a
missing required fixture argument; the second exposed only an over-strong test
comparison of run-specific topology headers. After those test-only corrections,
all four targeted gates passed. No representative, stress, Round1, Round2, VM,
full-M0, profiling, RAM, or runtime workload ran.

    ROUND1_STATUS=MANUALLY_TERMINATED_AFTER_DIAGNOSTIC_CONVERGENCE
    ROUND1_FORMAL_WINNER=UNRESOLVED
    S1M2_EXECUTION_BUNDLE_AUDIT=PASS
    S1M2_EXECUTION_BUNDLE_SCHEDULER=IMPLEMENTED_TINY_VALIDATION_PASS
    S1M2_EXECUTION_BUNDLE_PLAN=CANDIDATE_008192
    S1M2_EXECUTION_BUNDLE_PLAN_SHA256=7acf4b292adffe35dcdbdf3755c18d699b5659bb806ad2c7342a03db5d4279c9
    ROUND2_STATUS=NOT_STARTED
    FULL_M0_PROCESS_RUNNING=NO
    NEXT_ACTION=RESEARCHER_MANUAL_EXECUTION_BUNDLE_VALIDATION

## 88. Pre-Round2 bundle worker recalibration prepared (2026-09-10)

The former six-workload Round2 readiness stage is retired. Round1 remains
`MANUALLY_TERMINATED_AFTER_DIAGNOSTIC_CONVERGENCE`; its diagnostic evidence is
valid, its formal winner is unresolved, and its retained worker search is
12/16/24. No Round1 PASS or winner was fabricated.

Active Round2 now holds the frozen M0 Devanagari-continuous representative and
stress document lists fixed and runs each at workers 12, 16, and 24 on
`core-01` through `core-06`. All six jobs use three passes, exact inference,
and the bundle scheduler. Workload-specific plans fix target pressure 279047,
at most 256 complete ObservedSegments per bundle, and 128 max segment tokens.
The planner now accepts an ordered `--document-list` and fixed
`--target-pressure`, binding the list path/hash into its scan signature. The
loader accepts the co-located subset-plan layout while continuing to validate
manifest, list, representation, segment sequence, and materialization identity
fail closed.

Round2 plan generation no longer consumes a Round1 result. It requires the
recorded diagnostic closure and both real subset-plan materializations; each
job and trainer command binds its workload plan, plan SHA, materialization SHA,
worker, and host. The cloud operator can transfer/verify those plans, launch all
six jobs, report compact status, safely send TERM while preserving SQLite,
checkpoints, bundle shards, and run state, and collect remote attestations.

Aggregation admits a worker only when representative and stress both pass the
existing artifact/provenance/completion/zero-overflow/memory/storage gates. It
uses the existing 10% practical wall threshold per workload, then lower peak
process-tree RSS, lower canonical reducer stall, and lower worker count. If the
two workload selections disagree, it emits
`NEEDS_W20_INTERPOLATION` and prepared w20 follow-up job specifications. A PASS
winner directly supplies the worker count to the unchanged full six-cell plan;
there is no replacement readiness stage.

No subset plan was materialized, and no corpus scan, test, training, Round2,
VM, benchmark, or full-M0 execution ran. Only Python syntax compilation and
`git diff --check` are authorized static checks for this handoff.

```text
OLD_ROUND2_READINESS=RETIRED
ROUND2_MODE=BUNDLE_WORKER_RECALIBRATION
ROUND2_PRIMARY_WORKERS=12_16_24
ROUND2_WORKER_20_STATUS=RESERVED_IF_DECISION_CRITICAL
ROUND2_REPRESENTATIVE_PLAN=MATERIALIZATION_REQUIRED
ROUND2_STRESS_PLAN=MATERIALIZATION_REQUIRED
ROUND2_STATUS=NOT_STARTED
FULL_M0_PROCESS_RUNNING=NO
NEXT_ACTION=RESEARCHER_PRE_ROUND2_MATERIALIZATION
```

## 89. S1M2 Round 2 documentation closure (2026-09-10)

Round 2 executed all six planned M0 Devanagari-continuous jobs at workers 12,
16, and 24 for the frozen representative and stress workloads. All jobs
completed three passes and inspection. The three representative attestations
are valid with zero candidate overflow. All three stress attestations fail the
unchanged zero-overflow gate: each run records 34 overflowed tokens in every
training pass and 34 in final inspection. Since no worker passes both
workloads, the machine result is `ROUND2_STATUS=FAIL`,
`WINNER_WORKERS=null`, and `WINNER_REASON=no_worker_passed_both_workloads`.

Source inspection confirms the overflow semantics: when raw internal matches
exceed `max_internal_matches=512`, the retained match list is cleared. The
stress result therefore uses a genuinely truncated candidate space. Round 2
is not a formal scientific PASS, has no frozen-contract worker winner, and
does not authorize Full production.

Engineering scaling remains valid as a separately typed result. Scientific
artifact SHA-256 values are identical across 12/16/24 workers within each
workload. The later inspection-only bundle calibration gives no worker a
greater-than-10% wall-time advantage. Under the existing tie-break, 12 workers
is the engineering preference because it has the lowest sampled process-tree
RSS; higher worker counts reduce some reducer stall but consume materially more
memory. The researcher separately reports manual `ALL_IDENTICAL` results for
all six old-scheduler/new-scheduler inspection artifact comparisons. This
closure accepts that confirmation without rerunning it; the older generated
collection JSON is preserved unchanged.

The docs branch `docs/report-lifecycle-paper-map-20260906` is merged with its
ancestry intact. The authoritative Round 2 narrative is
`reports/core_methods/reusable_pieces/s1m2_round2_closure_20260910.md`.
The next boundary is a separately authorized, bounded candidate-overflow
forensic, followed only after resolution by reconsideration of Full-production
wiring. Neither task ran during documentation closure.

```text
ROUND2_EXECUTION=COMPLETE
ROUND2_FORMAL_SCIENTIFIC_STATUS=FAIL_CANDIDATE_OVERFLOW
ROUND2_FORMAL_WINNER=NONE
ROUND2_ENGINEERING_SCALING=CLOSED
ROUND2_ENGINEERING_PREFERENCE_WORKERS=12
ROUND2_WORKER_COUNT_SCIENTIFIC_EQUIVALENCE=PASS
ROUND2_OLD_NEW_INSPECTION_EQUIVALENCE=PASS_RESEARCHER_MANUAL
FULL_M0_AUTHORIZED=NO
NEXT_ACTION=BOUNDED_CANDIDATE_OVERFLOW_FORENSIC
```

## S1M2 compact exact inference implementation checkpoint — 2026-09-11

- Branch: `exp/s1m2-reusable-pieces`.
- Starting remote/reference HEAD: `fd99c9492ed063b7f2172f0c6e124a39303c58dd`.
- Selected architecture: `DIRECT_STRUCTURAL_FORM_TRIE_WITH_LEFT_ANCHORED_INCREMENTAL_CONSTRUCTION`.
- Compact S1M2 exact inference no longer retains one `LazyLexicalSpan` per legal lexical hypothesis.
- Compact support no longer globally retains complete lexical forms/form keys for all hypotheses.
- Hot-path per-span complete-form materialization is removed; bounded consumption-oriented reconstruction is used where canonical form identity is scientifically required.
- Compact S1M2 retains all grammar-licensed internal matches; the historical 512 threshold is telemetry/pressure only and no longer deletes compact-route support.
- Whole-form reusable-piece legality and exact preceding-pass count scoring are preserved, including whole forms longer than `max_piece_length`.
- `piece_occurrence_support` semantics remain exact and distinct from posterior expected count.
- Shared exact reusable-piece DP remains the inference kernel; legacy P1c remains the reference oracle.
- Compact production inference remains unbound from the legacy complete-form topology archive.
- Compact Top-K memory pressure no longer causes fallback to legacy inference: exact marginals continue, shared K×trie-node presentation state is disabled when over budget, and bounded exact per-form reconstruction supplies presentation Top-K.
- `lexical_span_hypotheses` again counts exact legal spans using a structural counter without reconstructing complete forms.
- Manual exact-span comparator passed against `LazyTokenLattice.iter_spans()` on tiny fixtures.
- Focused compact validation passed: compact/reference exactness, no per-span form materialization, support beyond the legacy pressure limit, exact active-piece scoring, and training without the legacy topology archive.
- Compact Top-K over-budget comparator passed.
- No representative corpus, stress corpus, VM run, or Full M0 was executed for this implementation checkpoint.
- `FULL_M0_AUTHORIZED=NO`.
- Next action after publication: bounded post-push offender/pressure probe of the compact kernel before any broader validation.

## S1M2 compact occurrence-support CPU-tail fix — 2026-09-11

The post-marginal compact path no longer reconstructs every endpoint's legal
piece set through repeated `_legal_pieces(form)` scans. During direct-trie
compilation it records packed `(subtree root, piece id)` membership roots.
Ancestor dominance removes repeated occurrences of the same piece along one
form path. At outer-posterior consumption, exact distinct lexical-occurrence
ownership is assigned across factors, endpoint counts are propagated once up
the retained parent array, and piece support is summed over disjoint roots.
Whole forms longer than `max_piece_length` remain separate exact endpoint
pieces. Score-only inspection prepasses skip occurrence-root compilation.

Focused compact-vs-legacy inference tests cover `devo'pi`, `tattvamasi`, a
repeated piece within one lexical occurrence, the same form at two distinct
lexical occurrences, and a whole form longer than `max_piece_length`. A
monkeypatch gate proves the compact production route does not call
`_legal_pieces(form)`. The focused inference file passes 31 tests, and the
tiny serial/parallel S1M2 scientific-output test passes. No raw1002+, stress,
representative, VM, worker calibration, or Full M0 run was executed.

```text
COMPACT_OCCURRENCE_SUPPORT_CPU_FIX_IMPLEMENTED=YES
PER_ENDPOINT_FULL_FORM_LEGAL_PIECE_RESCAN_REMOVED=YES
COMPACT_VS_LEGACY_FOCUSED_EXACTNESS=PASS

## S1M2 Round3 to Full control-plane closure — 2026-09-11

Compact exact completed-run audit now treats the legacy topology archive as an
optional reconstructible cache. Zero `topology/document_*.bin` files pass in
compact mode, while storage metadata that claims mutable scores or posteriors
still fails closed. The frozen production contract remains unchanged.

A formal `sktlm-s1m2-round3-closure/v1` builder and validator now bind the
immutable Round2 FAIL artifact, its canonical production contract, compact
implementation commits, and the existing raw520 exactness, local worker
equivalence, and raw1002/1410/1841/2484 pressure-tail evidence files by SHA-256.
Validation rejects a forged Round2 PASS, a formal winner, missing or altered
evidence, truncation/fallback, reopened worker selection, a non-w12 retained
preference, and compact commits outside current history.

Full-plan construction now requires both the historical Round2 result and the
validated Round3 closure. It does not rewrite Round2: formal status remains
FAIL due to candidate overflow and formal winner remains null. All six Full
jobs use the retained engineering preference of 12 workers, with the existing
Devanagari-continuous execution bundle path and SHA unchanged. W20 and the
legacy 3-hour gate remain retired. Eligibility is PASS, but Full M0 remains
unauthorized pending an explicit researcher decision.

```text
COMPACT_PRODUCTION_AUDIT=PASS
LEGACY_TOPOLOGY_REQUIRED=NO
ROUND3_STATUS=PASS
ROUND2_FORMAL_RESULT=PRESERVED_FAIL_CANDIDATE_OVERFLOW
ROUND2_FORMAL_WINNER=PRESERVED_NONE
ROUND2_ENGINEERING_PREFERENCE_RETAINED=12
WORKER_SELECTION_REOPENED=NO
CANDIDATE_OVERFLOW_BLOCKER=RESOLVED_BY_COMPACT_EXACT_INFERENCE
ROUND3_TO_FULL_CONTROL_PLANE=PASS
FULL_WORKERS=12
FULL_ELIGIBILITY=PASS
FULL_M0_AUTHORIZED=NO
```

## S1M2 production process-memory closure — 2026-09-13

Pass-2+ `PieceStoreScorer` workers no longer materialize the complete active
piece lexicon as a Python dictionary. Exact counts now use indexed SQLite
point lookup with a worker-local entry-bounded LRU, including exact OOV zero
counts and lookup/cache/SQLite telemetry. The scoring equation and active
piece parameters are unchanged.

The trainer now provides execution-only `--next-pass-only`. It completes only
the active partial pass or the next unfinished pass, transactionally leaves
`completed_passes=N`, `active_pass=null`, and `next_document_index=0`, then
returns without inspection. Default train-through-inspection behavior remains
unchanged.

Production `run_job()` now derives each phase from the authoritative SQLite
checkpoint and launches pass 1, resumed later passes, and inspection as
separate `run_with_metrics.py` process trees. Each phase has its own metrics
directory and manifest record (phase/pass, command, timestamps, return code).
Successful phase metrics are aggregated across resume attempts for existing
audit/resource consumers. A nonzero phase exits immediately; audit runs only
after all configured passes and inspection complete.

Tiny focused validation passed for bounded scorer exactness/LRU accounting,
three isolated passes with partial-pass restart, inspection equivalence to the
default lifecycle, and mocked production phase orchestration. No production,
representative, stress, Full M0, VM/cloud, RAM, or runtime workload was run.

```text
PIECE_SCORER_BOUNDED_SQLITE_LRU=PASS_LOCAL
TRAINING_PASS_PROCESS_ISOLATION=PASS_LOCAL
SCIENTIFIC_CONFIGURATION_CHANGED=NO
SCIENTIFIC_EQUATIONS_CHANGED=NO
FULL_M0_AUTHORIZED=NO
NEXT_ACTION=RESEARCHER_RUN_RAM_AND_CANONICAL_EQUIVALENCE_PROBES
```

## S1M2 Round 4 RAM-neutral runtime optimization — 2026-09-13

Round 4 is locally implemented as six sequential, independently pushed
commits based on `535f4e618563d88b9d85109d03bfaf1b049664dc`:

- `f7db7266995e35b487acf98ddb5f347fe8cd6363` records deterministic UTF-8
  line byte offsets in execution-plan schema v2 and seeks workers directly to
  bundle ranges. Existing v1 plans fail closed and require rematerialization.
- `9d58ebfe73cc34ed7b8afa9eac0d5d7a51e84656` hashes exact emitted training
  bundle-shard bytes while writing, avoiding the post-write full-file reread.
- `82dc24f38589c92b43bd28e16593be97239abb17` obtains the exact legal-span
  count from compact support compilation and removes the duplicate O(n²)
  production telemetry traversal.
- `007fb51dac30c614d91bbdf60b0539c4d6409c39` keeps canonical reducer
  accumulators string-keyed and materializes each unique phonological form only
  at an authoritative store flush.
- `5ee2ca52bee4722f7f9a7ff1d4346fc60bcbd0e7` constructs compact support
  directly into packed parent/depth/symbol arrays plus build-only child maps,
  eliminating transient `_SharedPrefixNode` objects on that path.
- `3b937abd4a64d5f6b48034d716112bdedca918e8` precomputes the fixed
  initial/noninitial piece-length prior table once per engine.

Focused validation passed: direct-seek UTF-8 range and stale-offset validation
(2 tests); streaming-vs-reread shard digest and scientific state (1 test);
reference-vs-compiled exact legal-span counts (1 test); bundled-vs-legacy
authoritative training state (1 test); compact-vs-legacy inference plus no
transient compact node objects (3 cases); and bit-exact fixed priors plus
compact/shared inference (3 cases). No representative, stress, worker
calibration, Full M0, VM/cloud, RAM, runtime, or other long validation ran.

Scientific equations, candidates, scoring, posterior, support, canonical
reduction order, floating-point accumulation order, frozen inputs and training
identity are unchanged. No worker, inflight, lookahead, cache, retained-factor,
or other RAM bound increased. Execution-plan v2 identity changes only the
reconstructible execution plan.

```text
ROUND4_STATUS=PASS_LOCAL
ROUND4_CODE_HEAD=3b937abd4a64d5f6b48034d716112bdedca918e8
SCIENTIFIC_SEMANTICS_CHANGED=NO
RAM_BOUND_INCREASED=NO
LONG_VALIDATION_RUN=NO
FULL_M0_AUTHORIZED=NO
NEXT_ACTION=RESEARCHER_RUN_ROUND4_MANUAL_GATES
```

## Generic cloud-host bootstrap — 2026-09-13

The non-contract `push-inputs` CLI dispatch bug is fixed: the generic path now
executes `push_inputs_action` rather than returning a nested lambda, while the
contract path continues to execute `push_contract_inputs_action`. The focused
generic dispatch regression passes.

`scripts/cloud/bootstrap_cloud_host.py` is now the generic WSL entrypoint for
bringing one arbitrary configured host profile to `READY`. It derives the clean
current branch and exact published HEAD locally, creates a temporary verified
Git bundle, and reuses the existing bundle deployment and generic frozen-input
transfer/validation paths. It does not hardcode an S1M2 branch, six-host set,
machine ID, or scientific workload.

The remote stages are ordered and fail closed: root SSH sanity; idempotent
prerequisites; exact-mount reuse or guarded operator-supplied blank-disk setup;
CPython 3.11.9 under `/opt/python-3.11.9`; exact-HEAD repo deployment/reuse;
guarded data-backed symlinks; venv and CPU-only PyTorch/project dependencies;
incremental canonical/representation transfer; authoritative validation; and
final READY validation. Conflicting mounts, root/system disks, unexpected
partitions/signatures/mounts, dirty/conflicting repos, wrong Python, invalid
venvs, and conflicting symlinks fail closed. Recognizable tool-owned partial
disk setup can resume. Receipts contain stage state and nested deployment/input
receipt references without secrets. `--dry-run` performs no VM/SSH operation.

Focused local validation passed 7 bootstrap tests plus the generic bridge
dispatch regression. No SSH, VM mutation, package/Python installation, rsync,
scientific workload, benchmark, or long validation ran.

```text
GENERIC_PUSH_INPUTS_DISPATCH=PASS_LOCAL
GENERIC_CLOUD_HOST_BOOTSTRAP=PASS_LOCAL
REMOTE_OPERATIONS_RUN=NO
SCIENTIFIC_SEMANTICS_CHANGED=NO
FULL_M0_AUTHORIZED=NO
NEXT_ACTION=RESEARCHER_DRY_RUN_NEW_HOST_BOOTSTRAP
```

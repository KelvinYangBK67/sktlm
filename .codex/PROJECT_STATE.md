# PROJECT_STATE.md

Last major handoff: 2026-08-30
Primary implementation branch: `exp/m0-core-methods`

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

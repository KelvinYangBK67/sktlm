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
The architecture keeps Git/GitHub authoritative for tracked code/configuration
and uses resumable rsync over SSH only for non-Git scientific bytes. It invokes
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

## 31. Research nomenclature and roadmap (2026-08-31)

The authoritative human-readable roadmap is
`docs/research_roadmap.md`. It separates three naming layers that earlier
historical documents sometimes placed close together:

- `M₀` is the frozen common experimental substrate: the corpus, exactly six
  formal observation representations, and shared provenance/evaluation
  contracts. It is not a scientific milestone or model name.
- `full-M₀` describes full frozen-corpus extent for one representation
  condition. It does not mean that the latent model is “M0”.
- a Stage is a major research phase; `M1`, `M2`, and optional `M3` are ordered
  scientific milestones within that Stage, restarting at `M1` for each new
  Stage. `v1` remains only an implementation/version label.

The project is currently in **pre-S1M1 infrastructure and capacity
calibration**. `IAST + surface_word` was chosen as the algorithm, exact
inference, streaming, resume, multiprocessing, performance, deployment, and
vocabulary-budget anchor. That history does not make it the sole final S1M1
representation. The current calibration program uses unrestricted replicas
to test VM equivalence and treats `K=16,384` / `K=32,768` as candidate
`K1` / `K2` capacity conditions. Their results may justify one adjustment
before S1M1 freezes; K must not change while the final matrix is running.

If VM identity proves scientifically negligible, the next research gate is
one unrestricted run for each of the six M₀ representations. Paired IAST and
Devanagari results for each spacing condition test script neutrality using
common latent, identity/latent-mass, ambiguity, grammar-use, and
segmentation/reconstruction diagnostics. Script-specific failures should be
fixed in the frontend before shared scientific parameters are changed.

After that six-representation gate and any necessary adjustment, one S1M1
specification freezes. The final S1M1 evidence matrix is:

`6 M₀ representations × {unrestricted, K1, K2} = 18 cells`

All 18 cells use the same frozen specification. Earlier full-M₀ runs remain
calibration/provenance evidence and are not retroactively promoted into the
final matrix.

Stage 1 retains the known/fixed external-sandhi grammar: S1M1 targets lexical
word-form identity and S1M2 advances to reusable surface-realizable
stem/morpheme identity. Any S1M3 requires a genuinely new scientific claim,
not engineering optimization. Stage 2 learns a realization grammar and then
uses it for latent learning. Stage 3 removes the language-specific rule prior
and advances toward joint latent-identity/realization discovery, with an
optional cross-lingual stress test only if it provides independent scientific
value.

Historical names—including `exp/m0-core-methods`, `full_m0_*` run IDs,
historical report filenames, and `stage01_checkpoint_20260831.md`—remain
unchanged as provenance. “Stage 01” in those reports names the historical
core-method work line; it does not retroactively declare final S1M1 evidence.

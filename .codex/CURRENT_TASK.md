# CURRENT_TASK.md

## Current status

Branch: exp/m0-core-methods.

Pre-S1M1 VM and fixed-vocabulary calibration is CLOSED. The frozen M0 corpus,
six representations, freeze metadata, m0 tag, 1,218-rule inventory, and the
scientific configuration of every running job remain unchanged.

The scientific checkpoint for the active representation gate is:

    375178ba50bd1a1644d65525907692b31413b33d

The four accepted IAST surface_word replicas supply one unrestricted cell.
Five other cells were manually bundle-deployed, input-verified, launched, and
immediately checked by the human operator:

- core-01: IAST legacy_joined
- core-02: IAST continuous
- core-03: Devanagari surface_word
- core-04: Devanagari legacy_joined
- core-05: Devanagari continuous

All five are RUNNING. Core-06 remains standby and was not deployed or
launched. Exact run/metrics IDs, launch PIDs, frozen-input counts/hashes, and
immediate verification are in:

- reports/core_methods/latent_lexicon/six_representation_gate_launch_checkpoint_20260901.md
- configs/cloud/experiment_registry.toml

RUNNING is not completion. No final wall time, RSS, return code, audit, or
scientific result has been recorded.

## Highest-priority operational boundary

Do not contact any VM. Do not run SSH, bridge remote operations, status
polling, collection, remote audit, process control, restart, resume, cleanup,
or deployment. Do not interpret early process samples. The five jobs must run
naturally to completion.

The next VM action is human-only and occurs after natural completion:

1. require process_tree_summary.json return_code=0;
2. run one final audit and require valid=true;
3. only then collect, compare the six cells, and mark completed rows DONE.

## Fixed deployment invariant

Git commit/history is authoritative code identity; GitHub is the publication
and collaboration endpoint. Production deployment to mainland core-01 through
core-06 is:

    clean published local checkout
    -> git bundle
    -> SCP/SSH
    -> remote bundle verification
    -> fetch from bundle
    -> exact fetched-SHA check
    -> fast-forward-only merge
    -> exact remote HEAD check

Remote GitHub fetch/pull and copied working trees are forbidden production
paths. The bridge deploy-code command is legacy GitHub-backed behavior for
non-core environments with reliable connectivity, not the core production
path.

## Research roadmap

The active gate is unrestricted learning across all six M0 representations.
K16/K32 remain capacity-stress appendix evidence. Do not add K, search for a
vocabulary sweet spot, or run the obsolete fixed-K 18-cell matrix.

S1M2 is reusable untyped compositional sharing:

    x -> u -> p1 ... pk
    concat(p1 ... pk) = u

The frozen external-sandhi grammar licenses/reconstructs u. Learned pieces
must concatenate exactly to u; S1M2 adds no rewrite and predeclares no stem,
suffix, root, ending, lemma, POS, paradigm, or grammatical-feature roles.
Systematic-gap allomorph induction is a future hypothesis, not a frozen S1M2
requirement and not implemented now.

Baseline/tokenizer comparison, common evaluation, S1M1 specification freeze,
aggregation, and paper-facing outputs remain deferred until the unrestricted
gate completes and final audits are available.

## CI closure

The clean-checkout CI failure was a test/environment contract mismatch. The
tracked manifest test now checks exactly six script/condition cells, exactly
240 rows per cell, and 240 unique logical document paths per cell without
requiring gitignored representation payload files. Production load_documents
file-existence checks are unchanged.

Validation completed once:

- focused frontend + bridge suite: 57 passed in 0.71s;
- full pytest: 516 passed, 2 existing Transformer warnings, in 44.45s;
- final git diff --check: passed.

Resume only from human-reported completed representation artifacts. Do not
rerun or infer remote state.

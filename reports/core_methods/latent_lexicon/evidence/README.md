# Formal benchmark evidence

This directory is the tracked minimum-sufficient evidence layer for research
and engineering decisions made from accepted formal benchmark runs. It keeps
small, non-sensitive, machine-readable metrics, audit, completion, config, and
provenance records when those files are locally available.

Bulk deterministic outputs remain ignored and local. In particular, this
directory does not contain `analyses.jsonl`, `boundary_posteriors.jsonl`,
`latent_lexicon.tsv`, `learner.sqlite`, SQLite WAL files, worker shards, or
`process_tree_samples.csv`. The established filenames, byte counts, and
SHA-256 values for large canonical scientific artifacts are recorded in
`manifest.json`; those hashes were copied from accepted tracked reports and
were not recomputed for this preservation task.

Reproduction and historical traceability are separate concerns. These records
preserve enough evidence to reconstruct why a benchmark conclusion was
accepted, but they are not a complete reproduction bundle. Reproduction still
depends on the frozen inputs, tracked code/configuration, documented command,
and an appropriate runtime environment. Selected complete artifacts may later
be archived externally for publication or long-term replication.

## Coverage

`manifest.json` maps every preserved run to its worker count, provenance
commit, original source location, and tracked evidence files. It covers the
four completed cloud medium P10 runs (w4, w8, w12, w16) and the accepted local
P10 w4/w8 comparison.

The cloud w4 report-profile evidence and both local runs had small raw files
available locally and those files are copied here. Raw small evidence for cloud
w8/w12/w16 was not present locally at preservation time. Their
`accepted_result.json` records are therefore explicit digests of facts already
accepted in `configs/cloud/experiment_registry.toml` and
`cloud_scaling_checkpoint_20260831.md`; they are not reconstructed audit
outputs and do not claim that a raw local collection exists.

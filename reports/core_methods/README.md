# Core-method reports

The core-method record is split by scientific milestone. Use this page to find
the current authority; use the subsystem indexes for deeper historical and
engineering detail. Stage definitions live in the
[research roadmap](../../docs/research_roadmap.md).

## S1M1 — Flat lexical identities — FROZEN

- **Authoritative result:** [S1M1 final scientific analysis and freeze](latent_lexicon/s1m1_final_checkpoint_20260903.md).
- **Mechanism evidence:** the final checkpoint's
  [association/specialization section](latent_lexicon/s1m1_final_checkpoint_20260903.md#direct-association-level-evidence-yes)
  provides the direct population-level evidence and weighting qualification.
- **Supporting controlled analysis:** the
  [non-continuous representation checkpoint](latent_lexicon/noncontinuous_representation_checkpoint_20260901.md)
  records the 2×2 comparison and bounded qualitative examples.
- **Derived downstream substrate:** the
  [M₀′ formal checkpoint](latent_lexicon/m0_prime_formal_checkpoint_20260905.md)
  is complete and valid; it is not an S1M1 result.
- **Detailed archive:** the frozen
  [latent-lexicon report collection](latent_lexicon/README.md) retains
  calibration, engineering, deployment, analysis-plan, and superseded status
  records. Historical words such as “current” apply only to their checkpoint.

No existing file under `latent_lexicon/` is rewritten to update its historical
status.

## S1M2 — Reusable untyped pieces — IN PROGRESS

- **Ordered report index:** [S1M2 reusable-piece reports](reusable_pieces/README.md).
- **Completed inference checkpoint:** [P1c exact composed-inference closure](reusable_pieces/s1m2_p1c_closure_20260905.md).
- **Completed integration checkpoint:** [streaming-trainer integration](reusable_pieces/s1m2_trainer_integration_20260905.md).
- **Current engineering/scientific-development record:**
  [continuous benchmark, profiling, and exact optimization](reusable_pieces/s1m2_continuous_benchmark_definition_20260905.md).

P0, P1a/P1b, P1c, and trainer checkpoints establish method and implementation
contracts. They do not constitute a final S1M2 scientific result. Continuous
profiling/optimization remains in progress, and full-corpus S1M2 production
has not started at this documentation checkpoint.

## Evidence storage

Tracked `evidence/` directories preserve compact machine-readable envelopes
for decisions. Bulk run outputs, databases, profiles, and regenerated products
remain under ignored `artifacts/`; when they change a durable conclusion, that
conclusion must be promoted into a tracked report.

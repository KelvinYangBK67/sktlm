# CURRENT_TASK.md

Current branch: `exp/m0-baseline-validation`

Local deterministic pre-cloud closure is complete. Do not launch an expensive
full-corpus matrix without explicit user authorization, do not run any IAST
`continuous` experiment, and do not modify frozen M0 or `src/sktlm/latent/`.

## Immediate next work

1. On the prepared CUDA host, check out the clean pre-cloud production commit
   and create a fresh environment from `pyproject.toml`/`requirements.txt`.
2. Run both frozen validators, the matrix input check, deterministic environment
   capture, and the one-job non-launching queue command in
   `reports/baselines/m0_first_production_cell_audit.md`.
3. With explicit authorization, run only
   `unicode_codepoint__devanagari__surface_word --production`.
4. Run `sktlm.experiments.baselines.audit` on that bundle. Do not schedule the
   other 17 cells unless classification is `pass`.
5. After all 18 independently trained bundles complete at one commit and
   environment, run the fail-closed aggregator. Never supply or synthesize the
   four retired cells.

The exact commands, failure classification, quarantine rule, and artifact path
are in `reports/baselines/m0_first_production_cell_audit.md`. TransLIST external
deployment is a non-blocking separate follow-up using
`reports/baselines/m0_translist_adapter.md`.

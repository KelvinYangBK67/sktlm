# CURRENT_TASK.md

Current branch: `exp/m0-baseline-validation`

Full-M0 pre-production code closure is complete. Do not modify frozen M0,
original representation trees/manifests, `data/rules/external_sandhi.tsv`,
`notes/**`, or `src/sktlm/latent/**`. Do not launch a VM or unbounded production
cell without new explicit authorization.

## Immediate next work

1. On the selected CUDA host, check out the exact clean pushed branch head and
   create a fresh Python 3.11 environment.
2. Provision the already validated, ignored M0-prime payload and its complete
   compact evidence set at the paths pinned by
   `configs/experiments/baselines/full_m0_matrix.yaml`; do not regenerate it on
   this branch.
3. Execute Stage 0 of `reports/baselines/full_m0_vm_runbook.md`: `pip check`,
   both frozen validators, M0-prime compact-evidence/input validation, exact
   22-cell non-launching plan/queue checks, four bounded M0-prime tokenizer
   smokes under the separate diagnostic artifact root, environment capture,
   and bridge contract validation.
4. With explicit authorization, run only
   `unicode_codepoint__devanagari__surface_word --production` and audit it.
   Continue only when classification is exactly `pass`.
5. With separate explicit authorization after the first-cell gate, execute the
   remaining 21 printed queue commands. Then run the fail-closed 22-cell
   aggregate, baseline shared-analysis adapter, and full-profile audited bridge
   collection.

The formal local `--check-inputs` currently fails closed because the pinned
M0-prime manifest/payload is not present in this checkout. No expensive
experiment or external VM action has been run.

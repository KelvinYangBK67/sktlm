# Reports

- `cleaning/` contains tracked corpus reports and occurrence-level provenance
  gates used by later cleaning stages.
- `cleaning/generated/` contains reproducible, potentially large local audit
  outputs and is ignored by Git.
- `representations/` contains script/spacing generation reports.
- `baselines/` contains tokenizer and model baseline reports.
- `core_methods/` contains the authoritative latent/core-method experiment
  narrative, including local optimization, cloud scaling, and full-run gates.
- `evaluation/` contains downstream evaluation reports.

## Authority and lifecycle

- Tracked concise reports are authoritative for conclusions and decisions.
- `reports/cleaning/generated/` and `artifacts/` are generated/local evidence;
  they remain ignored and are not the durable narrative.
- Historical reports are retained for provenance and linked from the relevant
  subsystem README rather than deleted when superseded.
- The current cloud scaling status is
  `core_methods/latent_lexicon/cloud_scaling_checkpoint_20260831.md`; the
  bounded local-only inventory is
  `core_methods/latent_lexicon/research_output_inventory_20260831.md`.

Reports never contain canonical corpus data. A later cleaning stage may consume
an explicitly tracked audit/provenance report as a reproducibility gate; these
remain physically separate from corpus bytes under `data/`.

## Data licensing

Some audit and provenance reports in this directory contain short textual
excerpts or skipped lines derived from GRETIL source texts. Those textual
portions are subject to the GRETIL data-licensing terms described in
[`../DATA_LICENSE.md`](../DATA_LICENSE.md); they are not relicensed under the
project's Apache License 2.0.

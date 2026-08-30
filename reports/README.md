# Reports

- `cleaning/` contains tracked corpus reports and occurrence-level provenance
  gates used by later cleaning stages.
- `cleaning/generated/` contains reproducible, potentially large local audit
  outputs and is ignored by Git.
- `representations/` contains script/spacing generation reports.
- `baselines/` contains tokenizer and model baseline reports.
- `evaluation/` contains downstream evaluation reports.

Reports never contain canonical corpus data. A later cleaning stage may consume
an explicitly tracked audit/provenance report as a reproducibility gate; these
remain physically separate from corpus bytes under `data/`.

## Data licensing

Some audit and provenance reports in this directory contain short textual
excerpts or skipped lines derived from GRETIL source texts. Those textual
portions are subject to the GRETIL data-licensing terms described in
[`../DATA_LICENSE.md`](../DATA_LICENSE.md); they are not relicensed under the
project's Apache License 2.0.

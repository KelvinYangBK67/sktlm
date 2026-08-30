# Reports

- `cleaning/` contains compact tracked corpus reports.
- `cleaning/generated/` contains reproducible, potentially large local audit
  outputs and is ignored by Git.
- `representations/` contains script/spacing generation reports.
- `baselines/` contains tokenizer and model baseline reports.
- `evaluation/` contains downstream evaluation reports.

Generated reports are never corpus inputs. Corpus data and reports therefore
remain physically separate.

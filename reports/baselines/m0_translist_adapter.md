# TransLIST adapter contract

TransLIST is an independent supervised reference under
`artifacts/references/translist/<run_id>`. It is not a baseline condition, does
not count toward 18-cell completeness, and cannot write inside
`artifacts/baselines/m0`.

Both reference and prediction JSONL use schema
`sktlm-translist-adapter-v1`. Each row contains `document_id`, `segment_id`,
`split`, `script`, `spacing`, `input_text`, `surface_segments`, and
`desandhi_segments`. Surface segments must concatenate exactly to the input;
desandhi segments are the supervised lexical output. IDs are unique, membership
and all identity fields must match exactly, and IAST `continuous` is rejected.

The adapter reports micro boundary precision/recall/F1, surface segmentation
exact match, desandhi sequence exact match, and desandhi token error rate. It
records the ordered split-identity fingerprint, source and prediction
fingerprints, Git commit, deterministic environment, and independent artifact
location. It does not deploy or train TransLIST itself, so external model
deployment remains a non-blocking follow-up.

Run an available prediction set with:

```bash
python -m sktlm.experiments.baselines.translist \
  --references path/to/translist_references.jsonl \
  --predictions path/to/translist_predictions.jsonl
```

# Canonical representations

Representation generation is downstream of canonical freeze and never writes
back into `data/canonical/`. Every output row records the same canonical
`freeze_id` and canonical file hash.

The six generated datasets are:

```text
iast/{continuous,surface_word,lexical_boundary}
devanagari/{continuous,surface_word,lexical_boundary}
```

`surface_word` preserves source-provided spacing. `continuous` removes ordinary
lexical whitespace while preserving physical line and document boundaries.
`lexical_boundary` uses the same text as `continuous` and adds a JSONL sidecar
whose offsets are derived only from source-provided whitespace after script
conversion.

The boundary offsets are a proxy. They are not gold segmentation, do not infer
missing lexical boundaries, and do not perform morphology, desandhi, or sandhi
analysis. This limitation is recorded in the representation manifest and
generation report.

Run and validate with:

```bash
sktlm-generate-representations
sktlm-validate-representations
```

# Formal GRETIL canonical corpus

The formal corpus builder selects only the exact `.htm` paths listed in
`notes/whitelist.txt`. It reads from `data/raw/gretil` and mirrors each selected
relative path under `data/canonical/gretil_iast`, changing only the suffix to
`.txt`.

## Invariants

- The output script is source IAST; the builder performs no transliteration.
- Source-provided lexical spaces and joined forms are preserved. The builder
  performs no desandhi, inferred segmentation, word joining, continuous-spacing
  conversion, or legacy joining.
- Unicode normalization is NFC. Encoding-equivalent punctuation and anusvara
  spellings may be normalized, but acute/grave and other source accents are
  retained.
- Clearly structural GRETIL HTML, headers, URLs, line labels, page numbers, and
  standalone structural numbers are removed with spaces or at line boundaries.
- Characters outside the expected Latin IAST and editorial repertoire are not
  deleted. They remain in the canonical text and are recorded for review.
- All whitelist entries must exist before any corpus artifact is written.

The older `sktlm-prepare-gretil` command remains a legacy pilot compatibility
path. It is not part of formal canonical construction.

## Commands

```bash
sktlm-build-gretil-canonical
sktlm-validate-gretil-canonical
```

The builder creates:

- `data/manifests/canonical_corpus.csv`
- `data/_reports/gretil_corpus_summary.txt`
- `data/_reports/gretil_unknown_characters.csv`
- `data/_reports/gretil_cleaning_audit.csv`

The manifest records source and canonical paths, stable document identity and
split, layer, script, size, accent/unknown-character flags, and SHA-256 hashes.
Validation checks exact whitelist membership, output namespace completeness,
UTF-8/NFC IAST, hashes, counts, whitespace invariants, and source provenance.

Canonical `.txt` files are generated data and are ignored by Git. The manifest
and QC reports are reproducible audit artifacts.

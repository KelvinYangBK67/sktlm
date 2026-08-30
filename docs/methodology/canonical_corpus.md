# Formal GRETIL canonical corpus

The extraction builder selects only exact HTML paths from
configs/corpus/gretil_whitelist.txt, reads data/raw/gretil, and mirrors each
selected document under data/intermediate/gretil. Only the explicit freeze
stage may write data/canonical/gretil_iast.

## Final invariants

- Exact whitelist membership, document identity, provenance and fixed split
  assignments are preserved.
- Every file is UTF-8 and NFC with LF line endings.
- The only permitted characters are lowercase IAST, validated ASCII avagraha,
  ASCII |, ASCII space and LF.
- A surviving apostrophe must pass the positive e/o avagraha environment;
  quotation and editorial apostrophes are forbidden.
- Titles, standalone section sigla, running headers and repeated edition
  abbreviations are removed before uppercase Sanskrit body text is lowercased.
- Editorial material is removed as a containing unit. Letters, digits and
  apparatus content are never blindly mapped to danda.
- Surviving textual punctuation is normalized to | only when deletion would
  erase a meaningful textual boundary.
- Source-provided lexical spaces remain a property of the canonical freeze.
  Script and spacing representations are derived later and never alter it.

The freeze implementation runs strict validation before it creates the output
directory. Final freeze is impossible unless invalid characters and invalid
apostrophes are both zero. Validation repeats the strict gate as well as exact
membership, corpus and file hashes, sizes, character counts and NFC checks.

## Commands

Extraction:

    sktlm-build-gretil-extraction
    sktlm-validate-gretil-extraction

Final cleanup and freeze:

    sktlm-clean-gretil-document-structure
    sktlm-project-gretil-strict-final
    sktlm-validate-gretil-strict
    sktlm-freeze-gretil-canonical
    sktlm-validate-gretil-freeze

The active manifest is data/manifests/canonical_corpus.csv. It retains source
hashes and stable identifiers, updates canonical hashes/counts, and binds every
row to one freeze_id. The compact final report is
reports/cleaning/gretil_canonical_freeze_summary.txt.

The previous freeze is retained under data/intermediate/gretil and its tracked
manifest/report under data/manifests/checkpoints and
reports/cleaning/checkpoints. Generated corpus files remain ignored by Git.

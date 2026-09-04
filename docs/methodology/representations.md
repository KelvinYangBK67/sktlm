# Canonical representations

Representation generation is downstream of canonical freeze and never writes
back into `data/canonical/`. Every output row records the same canonical
`freeze_id` and canonical file hash.

The six generated datasets are:

```text
iast/{surface_word,legacy_joined,continuous}
devanagari/{surface_word,legacy_joined,continuous}
```

`surface_word` preserves canonical spacing exactly in IAST and preserves all
lexical spacing after script conversion in Devanagari. `legacy_joined` applies
only the historical C-space-C,
C-space-V, and V-space-avagraha joins; anusvāra and visarga are not consonants
for these rules. `continuous` removes lexical spaces while preserving LF. It
keeps one space around IAST `|`/`||` when adjacent line text exists. In all
three Devanagari conditions, `।`/`॥` has no preceding space and one following
space when line text follows; line-final daṇḍas have no trailing whitespace.

Formal generation creates no boundary sidecars and performs no segmentation,
desandhi, morphology, or other inferred normalization. Script conversion is
completed once before the three spacing conditions are derived.

Run and validate with:

```bash
sktlm-generate-representations
sktlm-validate-representations
```

## Derived M0-prime

The six paths above remain frozen M0. The scientifically excluded ordinary
IAST `continuous` cell is not edited or relabeled. A separate M0-prime
derivation uses frozen M0 Devanagari `continuous` as source and renders lexical
`/ai/` and `/au/` as `ē` and `ō`, leaving `ai` and `au` for separate `a+i` and
`a+u`. It likewise renders aspirated consonants with modifier `ʰ`, leaving
plain `kh` ... `bh` for two-phoneme stop-plus-`h` sequences. This makes the
downstream IAST continuous encoding injective at the distinctions exposed by
the frozen Devanagari source. See
`docs/workflows/m0_prime.md` for generation, validation, provenance, and the
downstream six-cell contract.

# Derived M0-prime IAST-continuous substrate

M0-prime repairs the non-injective diphthong and aspirate spellings of the
original M0 IAST `continuous` cell without modifying M0. It is a deterministic
derived representation, not a new corpus freeze and not a learned model.

## Source and transformation

The only source is frozen M0 Devanagari `continuous`:

```text
freeze_id: 9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40
representation manifest SHA-256:
  c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520
canonical manifest SHA-256:
  ccec95eedc9ab37634d24d7d8fa2c47fc3189c3960b07cceb87fd48417ab3cb5
documents: 240
```

The transform preserves Devanagari's lexical-diphthong versus vowel-hiatus
distinction when rendering continuous IAST:

```text
lexical /ai/  -> ē
lexical /au/  -> ō
separate a+i  -> ai
separate a+u  -> au
aspirated consonants -> kʰ, gʰ, cʰ, jʰ, ṭʰ, ḍʰ, tʰ, dʰ, pʰ, bʰ
separate stop+h     -> kh, gh, ch, jh, ṭh, ḍh, th, dh, ph, bh
```

The aspirate convention is required for the same injectivity reason: frozen
Devanagari distinguishes (for example) `ध` from `द्` + `ह`, whereas ordinary
continuous IAST writes both as `dh`.

The `iast_m0_prime` frontend reverses this convention into the same
script-neutral `Phoneme` inventory used by the M0 frontends. It never treats
raw IAST characters as the final linguistic representation. Whitespace and
line order are preserved from the Devanagari source; no boundary sidecar,
segmentation, desandhi, morphology, or learned rewrite is introduced.

## Formal command

Run generation and validation from one clean, committed worktree:

```bash
python -m sktlm.representations.m0_prime generate \
  --config configs/representations/m0_prime_iast_continuous.json
python -m sktlm.representations.m0_prime validate \
  --config configs/representations/m0_prime_iast_continuous.json
```

The installed equivalents are:

```bash
sktlm-generate-m0-prime --config configs/representations/m0_prime_iast_continuous.json
sktlm-validate-m0-prime --config configs/representations/m0_prime_iast_continuous.json
```

Generation is atomic and refuses an existing output or artifact directory.
Validation is separately non-overwriting and may run once after generation.
Expected paths are:

```text
data/derived/m0_prime/iast/continuous/
artifacts/m0_prime/m0_prime_iast_continuous_v1/
  config.snapshot.json
  generation.json
  manifest.csv
  validation.json
  SHA256SUMS
```

The manifest is the permanent downstream interface. It records M0 freeze and
canonical identity, document and split identity, ordered relative paths,
source/output hashes and sizes, script/condition identity, phoneme counts, and
lexical-diphthong/hiatus counts. The validator rechecks exact source identity,
output membership and hashes, deterministic regeneration, line preservation,
allowed alphabet, lexical-diphthong/hiatus and aspirate/cluster distinctions,
and equality of source/output script-neutral phoneme sequences.

## Downstream six-cell substrate

Downstream experiments use five unchanged M0 cells plus the corrected derived
cell:

```text
M0 IAST:        surface_word, legacy_joined
M0 Devanagari:  surface_word, legacy_joined, continuous
M0-prime IAST:  continuous (script id iast_m0_prime)
```

The original M0 IAST `continuous` cell remains
`NA_SCIENTIFICALLY_EXCLUDED` and is never silently replaced in historical M0
analysis. Consumers opt into the M0-prime manifest explicitly.

## Formal result

The formal 240-document derivation and validation completed successfully on
2026-09-05 at Git commit
`e7f5b7d8e57b81868c97000b3058347160030df2`. Validation status is `VALID` and
the output manifest SHA-256 is
`3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`.
See `reports/core_methods/latent_lexicon/m0_prime_formal_checkpoint_20260905.md`
for exact totals, provenance, and compact checksum identities.

# PROJECT_STATE.md

This file records durable shared project state. It is not a task prompt.

## Frozen M₀

- Commit: `dbff6836eb35ecb1933653443ca793b1ab890c63`
- Annotated tag: `m0`
- Freeze ID: `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`
- Canonical root: `data/canonical/gretil_iast`
- Canonical manifest: `data/manifests/canonical_corpus.csv`
- Representation manifest: `data/manifests/representations.csv`
- Documents: 240
- Characters: 57,588,079
- Bytes: 69,864,279

Formal M₀ observation conditions are exactly six:

- IAST / `surface_word`
- IAST / `legacy_joined`
- IAST / `continuous`
- Devanagari / `surface_word`
- Devanagari / `legacy_joined`
- Devanagari / `continuous`

Older names such as `lexical_boundary` and `observed` are not formal M₀ conditions.

## Branch division

- `exp/m0-core-methods`: latent/sandhi core-method line.
- `exp/m0-baseline-validation`: baseline production and validation line.

The two lines share the frozen corpus contract, representation definitions, evaluation contracts, and provenance standards. The baseline line does not own latent learner implementation.

## Formal baseline matrix

The formal matrix contains exactly 22 independently trained conditions:

- BPE: IAST + Devanagari × three spacing conditions = 6.
- Unigram: IAST + Devanagari × three spacing conditions = 6.
- Unicode code point: IAST + Devanagari × three spacing conditions = 6.
- Akṣara-safe BPE: Devanagari `continuous` = 1.
- Surface-lattice: IAST × three spacing conditions = 3.

Total: 22.

## TransLIST

TransLIST is a separate supervised Sanskrit segmentation/desandhi reference. It is not a twenty-third matrix condition.

## Baseline responsibility

The baseline branch owns baseline implementation, validation, configurations, artifacts, tests, and reports. It must not implement the latent lexical core method or import core-method internals into baseline state documentation.

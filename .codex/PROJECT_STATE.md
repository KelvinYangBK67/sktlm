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

## Formal baseline implementation

- Commit `59d60ce` implements the exact 22-cell matrix schema and completeness validator.
- The baseline loader consumes the six frozen representation trees directly from `data/manifests/representations.csv`; it does not regenerate observation conditions dynamically.
- All 22 formal cells are runnable. BPE, Unigram, Unicode code point, Akṣara-safe BPE, and Surface-lattice each fit independently from their own frozen train representation and have unique method/script/spacing/seed artifact directories.
- Baseline tokenizer preparation and evaluation are streaming on the Python side. SentencePiece input preparation no longer materializes the full selected corpus in a Python list.
- Every supported run records the required method, script, spacing, effective config, seed, clean Git commit, M₀ freeze ID, both manifest hashes, software versions, and artifact location. Existing artifact directories are never overwritten.
- Commit `449adde` implements the approved Akṣara-safe BPE v1 and Surface-lattice v1 contracts. Their exact atomizers, barriers, deterministic surrogate training, decoding, lattice likelihood, and reproducibility requirements are recorded in `.codex/DECISIONS.md` and `reports/baselines/m0_method_contracts.md`.
- Akṣara-safe BPE uses an explicit Devanagari orthographic atomizer and cannot split an atom or cross a barrier. Surface-lattice constructs a complete learned-piece DAG over recorded-version IAST grapheme clusters, reports a deterministic Viterbi diagnostic path, and marginalizes all complete paths for BPC/BPB.
- A read-only full train-split inventory audit found 11,373 Akṣara types (11,378 required slots including reserved/internal symbols) and 40 Surface-lattice atom types (45 required slots) in each IAST condition, all below the formal 24k budget.
- No formal full-corpus baseline production run has been launched.

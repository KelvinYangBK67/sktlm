# DECISIONS.md

This file records durable decisions that should not be casually re-litigated in each session.

## Frozen corpus and observation conditions

1. M₀ is frozen.
2. The annotated `m0` tag must never move.
3. Frozen M₀ observation conditions are exactly six: IAST and Devanagari, each with `surface_word`, `legacy_joined`, and `continuous`. The derived M₀-prime consumer is a separate substrate identity.
4. Script and spacing are independent controlled factors.

## Formal baseline matrix

5. The historical baseline design contains exactly 22 conditions and remains recorded in the versioned manifest.
6. The historical M₀-only production matrix contains exactly 18 representation-valid conditions. The current full-M₀ production matrix separately contains 22 runnable cells: those 18 plus four explicit M₀-prime replacements.
7. BPE, Unigram, Unicode code point, and Surface-lattice under IAST `continuous` are retired by `iast-continuous-representation-validity-v1`: space deletion is not injective because cross-word vowel hiatus can collide with standard IAST diphthong spelling.
8. In the historical M₀-only matrix, BPE, Unigram, and Unicode code point each run on five conditions: IAST under `surface_word` and `legacy_joined`, plus Devanagari under all three spacings. Full-M₀ adds one `iast_m0_prime/continuous` cell for each.
9. Akṣara-safe BPE runs only on Devanagari `continuous`.
10. Historical Surface-lattice production runs on M₀ IAST `surface_word` and `legacy_joined`; full-M₀ also runs it on M₀-prime `iast_m0_prime/continuous`. Original M₀ IAST-continuous remains retired diagnostic evidence only.
11. TransLIST is a separate supervised reference, not a nineteenth historical cell or a twenty-third full-M₀ cell.
12. Each tokenizer × script × spacing condition is trained independently.
13. A condition must not inherit tokenizer or LM initialization from another condition.

## Comparability and provenance

14. No tokenizer may modify the frozen corpus.
15. Methods must not silently use different normalization or corpus subsets.
16. Necessary method-specific preprocessing must be explicit, documented, and reproducible.
17. Every formal run must record method, script, spacing, condition status, config, seed, code commit, corpus/data/tokenizer/environment provenance, software versions, fresh training identity, and artifact location.
18. Generated artifacts are not themselves tracked research reports.

## Ownership

19. The baseline branch does not implement the latent lexical core method.

## Approved remaining baseline contracts

20. Akṣara-safe BPE v1 uses an explicit Devanagari orthographic atomizer, not generic `\X`: a consonant plus any virāma-linked consonants and trailing Devanagari/Vedic marks is one atom. ZWJ continues a conjunct; ZWNJ closes the current atom and is a merge barrier.
21. Akṣara-safe BPE learns SentencePiece BPE merges over deterministic private-use surrogate code points, one per train-observed akṣara atom. Spaces, avagraha, daṇḍas, other punctuation, digits, controls, script changes, isolated marks, and ZWNJ-closed forms are singleton merge barriers. No learned token may split an atom.
22. Surface-lattice v1 uses Unicode extended grapheme clusters from the recorded `regex` runtime as surface atoms. A cluster is mergeable only when all code points are Unicode letters or marks and at least one is a letter; spaces, punctuation (including avagraha/apostrophe), digits, symbols, and controls are singleton barriers.
23. Surface-lattice vocabulary and log scores are fitted train-only with an identity-normalized SentencePiece Unigram model over deterministic private-use atom surrogates. The lattice is the complete DAG of matching learned pieces inside mergeable spans plus singleton barrier/unknown arcs; arcs never cross a barrier.
24. Surface-lattice intrinsic likelihood is the log-sum-exp over all complete DAG paths. Its intrinsic BPC/BPB use exact surface Unicode-character/UTF-8-byte counts. Diagnostics and the common downstream LM use the deterministic maximum-score path, breaking ties by fewer arcs, then lower token ID, then earlier predecessor.
25. Both methods use a 16-atom maximum learned piece, reserved IDs `<unk>=0`, `<s>=1`, `</s>=2`, `<pad>=3`, an unknown-atom log score of `-20.0` for Surface-lattice, exact reconstruction for known atoms, train-only fitting, independent per-cell models, and serialized atom maps. Runtime package versions are provenance and atomizer compatibility inputs.

## Pre-cloud evaluation and production

26. Standard SentencePiece and surrogate SentencePiece whitespace/normalization policies are explicit in effective config and fingerprints; changing them requires a new contract version.
27. Devanagari dependent-vowel, virāma, and avagraha-fragment metrics are illustrative script-specific diagnostics. Ordinary and M₀-prime IAST record them as not applicable. Full-M₀ declares the M₀-prime/Devanagari continuous script comparison explicitly.
28. All 22 full-M₀ cells use `m0-common-downstream-lm-v1`: fresh TinyDecoderOnlyTransformer/AdamW initialization, fixed split/budget/context/seed/scoring, common BPC/BPB, and bits per frozen IAST-surface-word canonical code point. Surface-lattice intrinsic likelihood remains separate.
29. Full-M₀ formal aggregation requires exactly 22 complete production bundles, rejects retired/bounded/duplicate/mismatched artifacts, and validates completion hashes plus code/data/tokenizer/environment provenance and per-cell M₀/M₀-prime observation-manifest identity before emitting any result. The historical 18-cell aggregate remains readable and valid under its old config.
30. TransLIST uses `sktlm-translist-adapter-v1` under an independent reference artifact root and never participates in baseline completeness.
31. Unbounded execution requires the explicit production gate. The first recommended cell is Unicode code point × Devanagari × `surface_word`; no later cell is scheduled until its audit passes.
32. `full-m0-v1` is frozen M₀ excluding original IAST `continuous`, plus derived M₀-prime corrected IAST `continuous`; the latter is exposed only as substrate `M0-prime`, script `iast_m0_prime`, representation `continuous`, derivation `m0-prime-iast-continuous-v1`, and pinned formal manifest SHA-256 `3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`.
33. M₀-prime Surface-lattice uses the separately versioned `iast_m0_prime_surface_lattice_v1` contract. It currently shares the Unicode letter/mark grapheme and barrier mechanics of ordinary IAST v1, but the separate identity prevents silently broadening the ordinary-IAST scientific claim and enters tokenizer fingerprints through `m0-prime-tokenizer-compatibility-v1`.
34. Shared analysis standardizes evidence/status/comparison/publication structure, not experiment-family metric names. Baseline evidence is admitted only after native 22-cell aggregate validation. Ordinary M₀ IAST surface/legacy versus M₀-prime continuous is descriptive, not a pure spacing effect, because orthographic encoding changes simultaneously.

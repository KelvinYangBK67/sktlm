# DECISIONS.md

This file records durable decisions that should not be casually re-litigated in each session.

## Frozen corpus and observation conditions

1. M₀ is frozen.
2. The annotated `m0` tag must never move.
3. Formal observation conditions are exactly six: IAST and Devanagari, each with `surface_word`, `legacy_joined`, and `continuous`.
4. Script and spacing are independent controlled factors.

## Formal baseline matrix

5. The formal baseline matrix contains exactly 22 conditions.
6. BPE, Unigram, and Unicode code point each run on IAST + Devanagari × three spacing conditions.
7. Akṣara-safe BPE runs only on Devanagari `continuous`.
8. Surface-lattice runs on IAST × three spacing conditions.
9. TransLIST is a separate supervised reference, not a twenty-third condition.
10. Each tokenizer × script × spacing condition is trained independently.
11. A condition must not inherit tokenizer initialization from another condition.

## Comparability and provenance

12. No tokenizer may modify the frozen corpus.
13. Methods must not silently use different normalization or corpus subsets.
14. Necessary method-specific preprocessing must be explicit, documented, and reproducible.
15. Every formal run must record method, script, spacing, config, seed, code commit, corpus provenance, software versions, and artifact location.
16. Generated artifacts are not themselves tracked research reports.

## Ownership

17. The baseline branch does not implement the latent lexical core method.

## Approved remaining baseline contracts

18. Akṣara-safe BPE v1 uses an explicit Devanagari orthographic atomizer, not generic `\X`: a consonant plus any virāma-linked consonants and trailing Devanagari/Vedic marks is one atom. ZWJ continues a conjunct; ZWNJ closes the current atom and is a merge barrier.
19. Akṣara-safe BPE learns SentencePiece BPE merges over deterministic private-use surrogate code points, one per train-observed akṣara atom. Spaces, avagraha, daṇḍas, other punctuation, digits, controls, script changes, isolated marks, and ZWNJ-closed forms are singleton merge barriers. No learned token may split an atom.
20. Surface-lattice v1 uses Unicode extended grapheme clusters from the recorded `regex` runtime as surface atoms. A cluster is mergeable only when all code points are Unicode letters or marks and at least one is a letter; spaces, punctuation (including avagraha/apostrophe), digits, symbols, and controls are singleton barriers.
21. Surface-lattice vocabulary and log scores are fitted train-only with an identity-normalized SentencePiece Unigram model over deterministic private-use atom surrogates. The lattice is the complete DAG of matching learned pieces inside mergeable spans plus singleton barrier/unknown arcs; arcs never cross a barrier.
22. Surface-lattice likelihood is the log-sum-exp over all complete DAG paths. Its common BPC/BPB values use negative marginal log-likelihood divided by exact surface Unicode-character/UTF-8-byte counts. Diagnostics use the deterministic maximum-score path, breaking ties by fewer arcs, then lower token ID, then earlier predecessor.
23. Both methods use a 16-atom maximum learned piece, reserved IDs `<unk>=0`, `<s>=1`, `</s>=2`, `<pad>=3`, an unknown-atom log score of `-20.0` for Surface-lattice, exact reconstruction for known atoms, train-only fitting, independent per-cell models, and serialized atom maps. Runtime package versions are provenance and atomizer compatibility inputs.

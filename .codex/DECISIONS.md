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

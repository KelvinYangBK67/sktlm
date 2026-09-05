# S1M2 P1c readiness checkpoint

Date: 2026-09-05

```text
S1M1=FROZEN
M0_PRIME=COMPLETE_AND_VALIDATED
S1M2_P0=AVAILABLE
S1M2_P1A=AVAILABLE
S1M2_P1B=AVAILABLE
S1M2_P1C=READY_TO_START
```

This checkpoint is an implementation-readiness boundary. It does not implement
P1c, run S1M2 on the corpus, claim an S1M2 scientific result, or authorize a
full-corpus experiment.

## Integrated ancestry

The branch was rebuilt from updated `main` at
`bf3396e630f7b28ff3172bd765979e2f64c351bf`, which contains:

- S1M1 scientific/archival freeze commit `3ed1841`;
- M0-prime implementation commit
  `e7f5b7d8e57b81868c97000b3058347160030df2`;
- validated M0-prime checkpoint commit `bf3396e`.

The prior S1M2 work was preserved by replaying only its two implementation
commits onto that base:

| Prior commit | Synchronized commit | Scope |
|---|---|---|
| `f95bc5f1bb92ce4beb899b13fa5a83070852d734` | `c976bdf` | P0 reference oracle and bounded M1 profiler |
| `3d4c5127c74201fa22af5fbf1673faa4096aa456` | `3ba3d80` | P1a production scoring and P1b lazy candidates |

The obsolete branch base tracked `notes/reviewer/*`; neither replayed commit
touches `notes/**`, the synchronized tree contains no tracked `notes/**`, and
no local note was modified, copied, staged, restored, or checked out.

## Scientific and implementation contract

Reusable pieces are untyped script-neutral `PhonologicalForm` sequences below
the grammar-licensed lexical form `u`. A legal segmentation
`p1 ... pk` must satisfy exact concatenation:

```text
concat(p1, ..., pk) = u
```

S1M2 introduces no lemma, POS, stem, suffix, root, paradigm, grammatical-
feature label, TransLIST/gold segmentation, dictionary, morphological analyzer,
pretrained Sanskrit model, Sanskrit-specific suffix inventory, or learned
internal morphophonological rewrite. The fixed Stage-1 external-sandhi grammar
remains separate and unchanged. There is no reward merely for using sandhi.

P0 remains the exact numerical oracle. Its legal piece DAG retains every
singleton, every allowed contiguous slice, and the whole form; both atomization
and memorization remain real competitors. Its independent-boundary prior is
renormalized exactly over the legal DAG, and exact forward/backward supplies
the reference log score and conditional expected piece counts.

P1a supplies fixed-pass production scoring with normalized countable base
measure

```text
H(p) = q (1-q)^(len(p)-1) |Sigma|^(-len(p))
P(p) = (count_A(p) + alpha H(p)) / (N + alpha)
```

where `Sigma` is the complete script-neutral phoneme inventory and inactive
pieces remain legal. P1b preserves M1 candidate membership and metadata in a
lazy node/span representation without persistent lexical-edge rows.

P1c is now ready to implement one exact shared/composed inference kernel over
those lazy spans. It must not instantiate an independent P0 lattice for every
lexical form and must not introduce a beam or early hard decoding. Required
tiny gates remain:

1. per-form prior normalizer, log score, and expected piece counts versus P0;
2. lazy/materialized outer partition and lexical expected-count equivalence;
3. composed expected piece counts;
4. identity/latent mass, expected lexical tokens, boundaries, rule usage, and
   total posterior mass;
5. deterministic counters for traversal, states/transitions, scoring/cache/
   store lookups, and bounded pass-local cache state.

## Substrate and validation

The branch inherits the validated downstream six-cell representation contract:

```text
M0 IAST:        surface_word, legacy_joined
M0 Devanagari:  surface_word, legacy_joined, continuous
M0-prime IAST:  continuous (iast_m0_prime)
```

M0-prime validation is `VALID` for 240 documents at manifest SHA-256
`3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922`.
No S1M2 code depends on the invalid original M0 IAST `continuous` cell.

Validation on the synchronized tree:

```text
focused pieces/profiler/M0-prime integration: 48 passed
full repository suite: 616 passed, 4 warnings
git diff --check: passed
tracked notes in tree/delta: none
```

The warnings are the existing PyTorch nested-tensor and SentencePiece SWIG
deprecation warnings. No scientific artifact was deleted or newly tracked.

## Exact next boundary

```text
S1M2 P1c READY TO START
```

The next task is P1c implementation only. Full trainer integration,
full-corpus S1M2 execution, S1M2 scientific interpretation, S1M3, Stage 2, and
downstream tuning remain outside this readiness checkpoint.

# Full-M0 baseline pre-production contract

## Frozen identities and scope

The production substrate is `full-m0-v1`:

- five unchanged, representation-valid M0 conditions;
- corrected M0-prime `iast_m0_prime/continuous`;
- 240 documents per condition, hence 1,440 catalog files;
- 18 unchanged M0 baseline cells plus four M0-prime replacements, hence 22
  independently trained production cells.

Original M0 `iast/continuous` remains `NA_SCIENTIFICALLY_EXCLUDED`. It is
present only in the historical `m0-baselines-v2` record and is not exposed by
the production catalog.

The read-only M0-prime interface was checked against the tracked main-branch
workflow, formal config, and 2026-09-05 checkpoint:

```text
derivation: m0-prime-iast-continuous-v1
manifest schema: sktlm-m0-prime-representation/v1
manifest SHA-256: 3a8cbb3359ce8cce2a7d551281a8faf50b9fed33f9b8d4bce3425d28237ae922
source M0 representation manifest: c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520
source M0 canonical manifest: ccec95eedc9ab37634d24d7d8fa2c47fc3189c3960b07cceb87fd48417ab3cb5
freeze: 9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40
documents: 240
```

The consumer validates manifest bytes, schema and derivation IDs, canonical
membership, document IDs, splits, formal sorted manifest order, source
Devanagari-continuous identity, output paths, sizes, and hashes. It imports no
M0-prime generator and no core-method package. Test fixtures carry an explicit
non-formal identity and production mode rejects them.

## Tokenizer compatibility

All M0-prime cells carry
`m0-prime-tokenizer-compatibility-v1` in effective config and tokenizer
fingerprints. BPE and Unigram preserve `ē`, `ō`, and modifier `ʰ` under the
identity SentencePiece contract when observed in training. Unicode-codepoint
tokenization preserves each code point. Surface-lattice uses the separate
`iast_m0_prime_surface_lattice_v1` contract: Unicode letter/mark grapheme
clusters are mergeable, punctuation/space/symbol/control clusters are barriers,
and unknown atoms remain singleton arcs with fixed negative log score.

This separate contract is required because `iast_surface_lattice_v1` named and
froze ordinary IAST; identical current atomization mechanics do not justify
silently broadening its scientific claim.

## Validation, analysis, and transport

The runner and queue load either historical or full-M0 configuration explicitly.
Each full-M0 artifact records substrate and its observation manifest. The
full-M0 aggregator requires exactly 22 complete unbounded bundles while sharing
only canonical/freeze, commit, seed, environment, and downstream-contract
invariants across cells; observation-manifest identity is checked per cell.

The shared-analysis core owns only evidence/status schemas, declared selector
comparisons, scalar arithmetic, and atomic JSON/TSV/Markdown publication. The
baseline adapter first invokes the native full-M0 aggregator, then maps validated
metrics into scientific and engineering groups. Surface-lattice intrinsic
likelihood remains separately named from common downstream utility.

Cloud transfer is driven by `configs/cloud/full_m0_baselines.yaml`. The bridge
contains transport, Git, mount, path, receipt, audit-hash, resume, and host
assignment safety; the thin baseline audit owns bundle semantics. Formal
collection defaults to the complete bundle because `COMPLETED.json` currently
declares and hashes the complete inventory.

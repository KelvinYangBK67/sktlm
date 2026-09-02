# M0 tokenizer evaluation contract

Status: frozen for pre-cloud production by condition manifest
`m0-baselines-v2`.

All 18 valid cells report the same script-neutral segmentation and inventory
fields: token count, occupied token types, grapheme split rate, invalid grapheme
boundary rate, `unk_count`, and `unk_rate`. Each tokenizer exposes its unknown
ID and a method-specific semantics string:

- BPE/Unigram: SentencePiece unknown piece for an unseen surface sequence;
- Unicode code point: a code point absent from that cell's train vocabulary;
- Akṣara-safe BPE: an akṣara atom absent from its serialized train inventory;
- Surface-lattice: an unseen IAST grapheme singleton arc with the fixed unknown
  log score.

Unknown rates are token-event rates on the diagnostic/Viterbi encoding. The
Surface-lattice intrinsic likelihood still marginalizes the complete lattice;
the unknown count does not replace that method-specific quantity.

Dependent-vowel starts, virama endings, and the avagraha fragment patterns are
illustrative Devanagari-only diagnostics. IAST artifacts record these quantities
as null, the pattern list as empty, and applicability as `not_applicable`. They
must not be used for IAST/Devanagari paired quantitative claims. Grapheme-boundary
metrics remain script-neutral, subject to the recorded Unicode/`regex` runtime.

## SentencePiece spacing policy

Standard BPE and Unigram explicitly preserve their historical SentencePiece
defaults: identity normalization; dummy prefix enabled; extra whitespace
cleanup enabled; whitespace escaping and whitespace splitting enabled; Unicode
script and number splitting enabled; whitespace suffix and whitespace-only
pieces disabled.

Akṣara-safe BPE and Surface-lattice retain their separately approved surrogate
policy: identity normalization; no dummy prefix; no extra-whitespace cleanup;
whitespace escaping enabled; whitespace, Unicode-script, and number splitting
disabled; whitespace suffix and whitespace-only pieces disabled. Their explicit
pretokenization delimiter remains the barrier mechanism. Both policy mappings
are part of effective config, tokenizer fingerprint, and serialized surrogate
metadata.

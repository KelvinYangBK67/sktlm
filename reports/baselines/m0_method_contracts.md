# M₀ baseline method contracts

Status: **APPROVED 2026-08-31**

These contracts define the one Akṣara-safe BPE cell and three Surface-lattice
cells reserved by the formal 22-condition matrix. Both methods consume frozen
representation text directly, fit only on the selected train split, and remain
independent across cells.

The Akṣara profile is a project-specific tailoring informed by
[Unicode UAX #29](https://unicode.org/reports/tr29/) grapheme rule GB9c and its
Indic conjunct model; it remains explicit here rather than delegating formal
behavior to whichever generic `\X` implementation is installed. Surface-lattice
intentionally uses recorded-version `\X` behavior.

## Shared surrogate training contract

Both methods first map every train-observed surface atom, sorted by Unicode
code-point sequence, to one deterministic Unicode private-use code point. The
map is serialized beside the model. SentencePiece receives only these
surrogates under identity normalization, without a dummy prefix, input
shuffling, whitespace splitting, Unicode-script splitting, or parallel
training. A user-defined pretokenization delimiter prevents learned pieces from
crossing barriers and is never exposed as a surface token.

The vocabulary budget includes `<unk>=0`, `<s>=1`, `</s>=2`, `<pad>=3`, and the
internal delimiter. The maximum learned piece is 16 surface atoms. Fitting must
fail if the budget cannot contain all train-observed atoms and reserved pieces.
Unknown evaluation atoms receive ID 0 and retain their exact source span.

## Akṣara-safe BPE v1

Domain: Devanagari / `continuous` only.

The atomizer is an explicit Devanagari profile rather than an alias for generic
extended grapheme clusters:

- an independent vowel, Devanagari letter-like base, or consonant begins an
  atom;
- a consonant may absorb any sequence of virāma, optional ZWJ, and another
  consonant;
- dependent vowel signs, anusvāra, visarga, nukta, Devanagari accent marks,
  and Vedic combining marks attach to that atom;
- ZWNJ attaches to and closes the current atom, making it a merge barrier;
- an explicit final virāma remains inside the current atom; and
- spaces, avagraha, daṇḍas, other punctuation, digits, controls, script
  changes, and isolated marks are singleton merge barriers.

SentencePiece BPE operates on one surrogate code point per atom. It may merge
adjacent mergeable atoms but can never split one or cross a barrier. Encoded
pieces project surrogate offsets back to exact source-character spans. Decoding
concatenates the serialized atoms and is lossless whenever no unknown atom is
present.

## Surface-lattice v1

Domain: IAST under `surface_word`, `legacy_joined`, and `continuous`, fitted
independently.

Surface atoms are Unicode extended grapheme clusters produced by the exact
recorded `regex` package version. A cluster is mergeable only if every code
point is a Unicode letter or mark and at least one code point is a letter.
Combining accents therefore stay with their base. Spaces, apostrophe/avagraha,
other punctuation, digits, symbols, and controls are singleton barriers.

An identity-normalized SentencePiece Unigram model learns the surface-only
piece inventory and piece log scores from the train split. It sees neither
gold/dev/test boundaries nor frozen boundary sidecars. At evaluation time:

1. nodes are ordered surface-atom boundaries, represented as source-character
   offsets;
2. every learned piece matching at a node contributes an arc when it stays
   inside one mergeable span;
3. barriers have exactly one singleton arc;
4. an unseen atom receives one singleton unknown arc with log score `-20.0`;
5. the complete-string log likelihood is the log-sum-exp over all complete DAG
   paths; and
6. the diagnostic encoding is the maximum-score path, breaking exact ties by
   fewer arcs, then lower token ID, then earlier predecessor.

Common likelihood metrics are:

- `BPC = -log2 P(surface) / Unicode code-point count`;
- `BPB = -log2 P(surface) / UTF-8 byte count`.

Known-token decoding is exact. The serialized metadata stores the atom mapping,
barrier inventory, atomizer contract/version, maximum piece length, and unknown
score; the artifact fingerprint records both metadata and SentencePiece model
hashes.

## Acceptance requirements

- all 22 formal cells are enumerated and runnable;
- no method changes frozen text, membership, or split assignment;
- every Akṣara-safe token boundary is an approved atom boundary;
- every lattice is connected, acyclic, exact-span preserving, and barrier-safe;
- repeat training at the same deterministic artifact location yields identical
  atom mapping and model bytes;
- each cell has an independent model and artifact directory;
- required provenance and software versions are complete; and
- neither method imports, copies, or modifies `src/sktlm/latent/`.

## Frozen M₀ train readiness audit

A read-only scan of the 832,012 non-empty train segments per condition found:

| Method / condition | Surface atoms | Atom types | Barrier types | Minimum required vocabulary |
|---|---:|---:|---:|---:|
| Akṣara-safe BPE / Devanagari `continuous` | 16,730,381 | 11,373 | 6 | 11,378 |
| Surface-lattice / IAST `surface_word` | 44,074,953 | 40 | 3 | 45 |
| Surface-lattice / IAST `legacy_joined` | 43,252,764 | 40 | 3 | 45 |
| Surface-lattice / IAST `continuous` | 40,138,023 | 40 | 3 | 45 |

The formal 24,000-piece budget therefore contains every required base atom and
reserved/internal symbol in all four cells. This audit trained no model and
modified no frozen file.

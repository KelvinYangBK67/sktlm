# Pending M₀ baseline method contracts

Status: **PROPOSED, NOT FROZEN**

The formal matrix reserves one Akṣara-safe BPE cell and three Surface-lattice
cells. Their names and domains are durable project decisions, but the repository
does not yet define enough behavior to produce comparable results. The baseline
runner therefore fails closed for these four cells instead of silently mapping
them to an existing tokenizer.

## Akṣara-safe BPE

Fixed domain: Devanagari / `continuous` only.

Proposed invariant: BPE operates on a deterministic sequence of orthographic
akṣara atoms, and every learned-piece boundary must coincide with an atom
boundary. A Unicode extended grapheme cluster is not automatically accepted as
an akṣara: conjuncts, virāma behavior, Vedic marks, join controls, punctuation,
and malformed-but-frozen sequences need an explicit policy.

The method contract must freeze:

1. the exact akṣara segmentation algorithm and Unicode/`regex` version policy;
2. whether spaces, daṇḍas, punctuation, digits, and script changes are merge
   barriers;
3. the BPE pair-counting, tie-breaking, vocabulary-budget, reserved-ID, and
   unknown-symbol rules;
4. lossless decoding and character-span projection from akṣara atoms; and
5. train-only fitting plus deterministic serialization and fingerprinting.

Acceptance tests must prove that no encoded token splits a frozen-input akṣara,
that decoding reconstructs the input under the declared policy, and that a
repeat fit produces identical model bytes and vocabulary ordering.

## Surface-lattice

Fixed domain: IAST under `surface_word`, `legacy_joined`, and `continuous`, with
each cell trained independently.

"Surface-lattice" currently leaves several experiment-defining choices open.
The contract must freeze:

1. lattice nodes (normally character offsets) and the exact allowed arc set;
2. how candidate arcs are obtained using surface evidence only, including the
   treatment of spaces, punctuation, avagraha, accents, and unknown characters;
3. whether the lattice is deterministically constructed or learned from the
   train split, and its vocabulary/complexity budget;
4. the training objective, path marginalization or decoding rule, and
   deterministic tie-breaking;
5. how lattice likelihood is exposed to the common BPC/BPB evaluation contract;
6. the serialization, span, reconstruction, and provenance requirements; and
7. a leakage test showing that dev/test gold boundaries, frozen side knowledge,
   and latent/core-method internals are not used.

The three spacing conditions cannot share fitted initialization. A whitespace
split, the generic grapheme tokenizer, or code from `src/sktlm/latent/` is not a
valid substitute for this method.

## Required decision before implementation

The research owner must approve the two contracts above or provide a different
formal definition, especially the akṣara atomizer/barrier rules and the lattice
arc/objective definition. Once approved, they should move from this proposal
into the durable decision record before implementation and production runs.

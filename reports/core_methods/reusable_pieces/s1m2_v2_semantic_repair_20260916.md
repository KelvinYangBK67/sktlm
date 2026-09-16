# S1M2 V2 candidate and reuse-semantics repair

Date: 2026-09-16
Status: implemented locally; Full M₀ scientific validation not run

## Scope

This is the minimal V2 repair following the documented
`reusable_pieces_v1` whole-form-memorization failure. It corrects four
identified semantic defects without changing the piece-scoring objective,
its hyperparameters, the fixed sandhi inventory, or joint outer/inner exact
inference.

The V1 defects were:

- a lexical factor could merge across observed whitespace;
- visible-boundary inversion omitted joined surface realizations whose rule
  surface did not contain an explicit boundary marker;
- reusable-piece qualification used evidence from distinct token
  occurrences, so repetition of one lexical form could qualify its own whole
  form;
- piece count and support identities did not distinguish lexical position.

This note records an implementation contract, not a claim that V2 has passed
a real-corpus scientific gate or eliminated the previously observed collapse.

## Candidate semantics

Observed whitespace is now a one-way structural constraint:

```text
observed whitespace => lexical boundary
no observed whitespace =/> no lexical boundary
```

Candidate construction therefore never emits a lexical factor spanning an
observed space. This applies to every representation in which a space remains
visible. Deleted boundaries in `legacy_joined`, and all lexical boundaries in
`continuous`, remain latent and use the existing internal candidate
mechanism. An S1M2 configuration that explicitly requests the old merge
behavior is rejected rather than silently ignored; frozen S1M1 defaults are
not redefined by this V2 repair.

A hard lexical fence does not assert that surface material on each side is
identical to its underlying lexical material. At each visible fence, every
fixed external-sandhi rule with a joined surface realization is considered at
every exact split of that realization. Forward reconstruction must reproduce
the observed left and right surface portions exactly. Thus frozen
`ū + e -> ve` can invert both:

```text
continuous/internal: ...ve... -> ...ū | e...
visible fence:        ...v e... -> ...ū | e...
```

In particular, regression coverage now includes
`svayaṃbhv ekam -> svayaṃbhū | ekam`. No sandhi rule was added or changed.

## Positional piece identity

A reusable-piece parameter is keyed by the pair `(phonological form, role)`.
The role is derived from the existing piece span and lexical-form length:

```text
WHOLE     start == 0 and end == lexical length
LEFT      start == 0 and end < lexical length
RIGHT     start > 0  and end == lexical length
INTERNAL  start > 0  and end < lexical length
```

The role travels as edge metadata and in compact store keys; it does not
create four lattices or four copies of the shared trie. Expected counts,
fixed-pass scoring, support, checkpoint state, inspection output, and artifact
comparison all use the same positional identity. Consequently evidence for
`m@RIGHT` cannot raise the score or qualification of `m@LEFT`.

The scorer equations and declared hyperparameters are unchanged. Only the
identity on which a count is looked up is more specific.

## Host lexical-type qualification

Between-pass activation now separates posterior expected count from reusable
qualification. For each stable host lexical-form key `h`, lexical posterior
mass is first aggregated across all occurrences and derivations:

```text
S(piece, role, h) = aggregated posterior mass of host type h
```

Each legal positional piece identity in that host receives this host mass.
The streaming store then counts distinct host types whose aggregated mass
meets the explicit threshold:

```text
host_type_support(piece, role)
  = |{h : S(piece, role,h) >= host_support_threshold}|
```

The conservative default is `host_support_threshold = 1.0`, meaning one
expected host occurrence after aggregation. A multi-phoneme identity is
retained only when its qualifying host-type count is at least
`min_reuse_host_types = 2`. This default was not tuned on a corpus. Singleton
identities remain active base support.

Repeated occurrences of one whole lexical form therefore have host diversity
one and cannot qualify that multi-phoneme `WHOLE` identity by themselves.
Conversely, `deva@LEFT` may qualify when supported by multiple distinct host
forms. Support rows are accumulated by compact `(piece-role key, host-form
key)` in SQLite and reduced between passes; token occurrence objects and the
complete active inventory are not retained or scanned per token.

## Preserved support and architecture

The whole lexical form remains a legal escape/fallback edge even when it is
longer than `max_piece_length`. Legality is separate from activation: the
model may still choose an unanalyzed whole form, but repeated tokens of that
form no longer constitute cross-type reuse evidence.

The repair preserves the existing exact joint lexical/piece posterior and the
same legal piece support. Shared-prefix/trie topology, lazy candidate
construction, compact exact inference, bounded caches, streaming/sharded
aggregation, SQLite-backed parameter state, execution bundles, topology
reuse, canonical reduction, and production scheduling remain the production
architecture. The inner direct/shared/compact score and marginal paths only
receive role-conditioned keys; no four-DP replacement was introduced.

## Validation boundary

Tiny deterministic regressions cover:

- hard whitespace fences and rejection of the obsolete merge setting;
- paired internal `ve -> ū | e` and visible-fence inversion;
- the full `svayaṃbhv ekam -> svayaṃbhū | ekam` example;
- repeated whole-form host diversity of one;
- cross-host `deva@LEFT` qualification;
- separation of `m@RIGHT` and `m@LEFT` counts/support;
- legal long whole-form fallback;
- exact role-conditioned agreement of the compact/shared kernel with the
  reference oracle;
- streaming SQLite finalization plus serial/parallel and bundled reduction on
  tiny fixtures.

No Full M₀ run, representative or stress corpus, performance/RAM benchmark,
VM/cloud operation, hyperparameter search, commit, or push was performed.
Whether the unchanged scoring objective still collapses after these semantic
repairs remains a required human-run bounded scientific and performance gate.

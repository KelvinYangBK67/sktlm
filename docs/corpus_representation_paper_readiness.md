# Corpus and representation paper-readiness audit

Date: 2026-09-06

Overall status: **READY_WITH_CAVEATS**

This is a static documentation audit of the tracked repository. It did not
re-run corpus construction, validation, representation generation, tests, or
research analysis, and it did not inspect ignored corpus payloads. The status
therefore means that the tracked evidence is sufficient to draft the technical
corpus and representation methods; it is not a new validation result.

## Readiness checklist

| Paper requirement | Status | Tracked authority | Finding and claim boundary |
|---|---|---|---|
| Source and technical provenance | `READY_WITH_CAVEAT` | [canonical-corpus specification](methodology/canonical_corpus.md), [`canonical_corpus.csv`](../data/manifests/canonical_corpus.csv), and [corpus manifest summary](../reports/cleaning/corpus_manifest_summary.txt) | Stable source paths, file identities, hashes, splits, and freeze identity are tracked. A consolidated per-text bibliographic catalogue is not. |
| Corpus inclusion and exclusion | `READY` | [`gretil_whitelist.txt`](../configs/corpus/gretil_whitelist.txt) and [cleaning report index](../reports/cleaning/README.md) | The final 240-document membership and the adjudication boundary are documented. |
| Cleaning-stage sequence | `READY` | [cleaning workflow](workflows/corpus_cleaning.md) and [cleaning report index](../reports/cleaning/README.md) | Stage order, positive-match constraints, audits, and promotion gates are documented. |
| Final normalization policy | `READY_WITH_CAVEAT` | [canonical-corpus specification](methodology/canonical_corpus.md), [cleaning workflow](workflows/corpus_cleaning.md), and final closure reports listed below | The final policy is documented, but the two `v1` methodology pages are historical inputs and are not sufficient by themselves to describe the final freeze. |
| Canonical freeze and identity | `READY` | [canonical freeze summary](../reports/cleaning/gretil_canonical_freeze_summary.txt) and [`canonical_corpus.csv`](../data/manifests/canonical_corpus.csv) | The final summary records 240 files, corpus size, SHA-256 identity, strict-character closure, and the implementation identity. These are existing reported values, not recomputed here. |
| Final corpus closure | `READY` | [semantic closure](../reports/cleaning/pre_m0_semantic_closure.md), [tokenizer-final closure](../reports/cleaning/pre_m0_tokenizer_final_closure.md), [single-consonant closure](../reports/cleaning/pre_m0_single_consonant_final_closure.md), and [final closure](../reports/cleaning/pre_m0_final_closure.md) | The progression from provenance-based repairs through final membership and occurrence-level decisions is available for methods and limitations. |
| Representation family | `READY` | [formal representation definition](methodology/representations.md), [representation report index](../reports/representations/README.md), and [generation summary](../reports/representations/representation_generation_summary.txt) | The two-script by three-spacing M0 design, ordering, punctuation behavior, and exclusions are explicitly defined. |
| Script conversion | `READY` | [formal representation definition](methodology/representations.md) | Conversion occurs before spacing manipulation; Devanagari recomposition and the boundary between orthography and linguistic inference are documented. |
| Spacing conditions | `READY` | [formal representation definition](methodology/representations.md) and [generation summary](../reports/representations/representation_generation_summary.txt) | `surface_word`, `legacy_joined`, and `continuous` have explicit operational definitions; lexical boundary is not equated with punctuation or line structure. |
| Representation provenance and counts | `READY` | [`representations.csv`](../data/manifests/representations.csv) and [generation summary](../reports/representations/representation_generation_summary.txt) | The tracked manifest binds 1,440 reported representation files to the same 240-document freeze across six cells. Generated payloads themselves are ignored. |
| Continuous-IAST limitation | `READY` | [representation report index](../reports/representations/README.md), [continuous source analysis](../reports/core_methods/latent_lexicon/continuous_performance_source_analysis.md), and [M0-prime checkpoint](../reports/core_methods/latent_lexicon/m0_prime_formal_checkpoint_20260905.md) | Ordinary M0 IAST `continuous` is scientifically excluded. It must not be presented as an available final experimental cell. |
| M0-prime derivation | `READY` | [M0-prime workflow](workflows/m0_prime.md) and [formal checkpoint](../reports/core_methods/latent_lexicon/m0_prime_formal_checkpoint_20260905.md) | The derived IAST continuous substrate, its source, injective distinctions, identity, validation claims, and six-cell downstream contract are documented without altering frozen M0. |
| Licensing and attribution | `READY_WITH_CAVEAT` | [data licensing](../DATA_LICENSE.md) and [third-party notices](../THIRD_PARTY_NOTICES.md) | The project/GRETIL license boundary and attribution obligations are explicit. Per-text bibliographic attribution still needs a paper-facing catalogue. |
| Reproduction and data access | `READY_WITH_CAVEAT` | Commands in the [canonical-corpus specification](methodology/canonical_corpus.md), [cleaning workflow](workflows/corpus_cleaning.md), [formal representation definition](methodology/representations.md), and [M0-prime workflow](workflows/m0_prime.md) | Tracked entry points and identities support technical reconstruction, but a clean clone does not contain ignored raw, canonical, representation, M0-prime, or artifact payloads. A paper-facing availability statement is still required. |

## Historical specifications that must not stand alone

- [`gretil_iast_v1.md`](methodology/gretil_iast_v1.md) records an earlier
  extraction, cleaning, and conversion specification. It is useful historical
  context, but later strict projection and pre-M0 closure documents define the
  final canonical method.
- [`normalization_v1.md`](methodology/normalization_v1.md) records the first
  general normalization rules. It is not the complete final GRETIL IAST freeze
  policy.

For a paper's final corpus methods, use the current
[canonical-corpus specification](methodology/canonical_corpus.md), the
[cleaning workflow](workflows/corpus_cleaning.md), and the final tracked closure
reports together. For representations, use
[`representations.md`](methodology/representations.md) together with the
representation manifest and generation summary.

## Documentation gaps before publication

### `DOCUMENTATION_GAP` — per-text bibliographic attribution

The repository already tracks technical provenance: selected source-relative
paths, stable document identifiers, split assignments, source and output
hashes, corpus membership, freeze identity, and the GRETIL licensing boundary.
What is not consolidated in a tracked, paper-facing source is a per-document
mapping of work title, source edition, data-entry or other credited
contributors, upstream record or URL, and preferred citation where those
fields are supplied upstream.

This is a documentation and attribution-catalogue gap. It must not be described
as proof that the underlying notices or metadata do not exist. Before
publication, extract or curate the available upstream attribution into a
durable catalogue, cite its version, and distinguish fields unavailable from
fields not yet transcribed.

### `DOCUMENTATION_GAP` — paper-facing data availability and access

The repository deliberately ignores `data/raw/`, `data/intermediate/`,
`data/canonical/`, `data/representations/`, `data/derived/`, and `artifacts/`.
A clean clone therefore supplies tracked manifests, rules, code, reports, and
reconstruction commands, but not the referenced GRETIL-derived bytes or local
run payloads.

The paper still needs a concise statement specifying which datasets or
snapshots can be redistributed, where readers can obtain authorized source
material, which upstream terms apply, and what provisioned inputs are required
before running the documented commands. Local retention and cryptographic
manifests must not be presented as equivalent to public distribution or
long-term public availability.

## Publication judgment

The tracked repository supports drafting the technical corpus construction,
cleaning, freeze, representation, continuous-condition limitation, and
M0-prime sections, including the already reported counts and identities. Final
publication readiness remains conditional on closing the two documentation
gaps above and on citing the final authorities rather than the historical `v1`
specifications alone.

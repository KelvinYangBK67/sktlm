# GRETIL cleaning workflow

The retained historical input is
data/intermediate/gretil/pass3b_v3_hyphen_normalized_gretil_iast. The previous
round's canonical freeze is preserved as
data/intermediate/gretil/pre_strict_canonical_checkpoint_gretil_iast, with its
manifest and report under the corresponding checkpoints directories.

## Required order

1. Run sktlm-clean-gretil-known-files. It consumes the preserved pre-strict
   checkpoint, applies only the 27 manually adjudicated file conventions, and
   writes data/intermediate/gretil/known_file_cleaned_gretil_iast.
2. Run sktlm-clean-gretil-document-structure on that output. This removes titles, standalone
   sigla, repeated running headers and repeated edition abbreviations as whole
   lines. Removed lines become blank lines; they are never lowercased into
   apparent Sanskrit text.
3. Run sktlm-project-gretil-strict-final. This removes editorial units,
   lowercases uppercase Sanskrit only in surviving body text, resolves
   hyphens/source separators, and normalizes punctuation that carries a textual
   boundary to ASCII danda.
4. Run sktlm-validate-gretil-strict. Both invalid-character and
   invalid-apostrophe counts must be zero.
5. Only then run sktlm-freeze-gretil-canonical and
   sktlm-validate-gretil-freeze.
6. Run sktlm-close-gretil-pre-m0. It applies only fixed-point NFC, LF,
   ASCII-space, blank-line, and ASCII-danda layout normalization to the
   canonical freeze, refreshes derived manifest hashes/counts, then performs
   the read-only isolated-consonant and adjacent-vowel audit. The final
   zero-modification pass is mandatory and guarded by a maximum iteration
   count.
7. Run sktlm-close-gretil-pre-m0-semantic. It reproducibly rebuilds the
   mechanical checkpoint from the strict candidate, normalizes vowel-adjacent
   ḷ/ḷh, audits non-Sanskrit residue, and traces adjacent vowels through the
   document checkpoint and raw source. It restores a space only where aligned
   provenance proves that an ASCII lexical space was lost; source-present and
   unresolved forms remain unchanged and are reported.
8. Run sktlm-close-gretil-pre-m0-tokenizer-final. It consumes the immutable
   246-document semantic checkpoint, filters membership through the
   authoritative whitelist, removes only adjudicated path-scoped
   English/editorial spans, and promotes a strictly validated 240-document
   candidate. The stage includes an exact occurrence gate and a surviving-token
   subsequence guard: it cannot add, split, or rewrite Sanskrit lexical tokens.
   Its standalone single-letter scan is read-only and writes the three requested
   TSV files under data/_reports.
9. Run sktlm-close-gretil-pre-m0-single-consonants. Before changing any line,
   it materializes and validates the exact `file + original line + token +
   occurrence count + context` KEEP list against the pre-cleanup audit. It
   removes every other standalone consonant, removes only adjudicated
   English/editorial units, re-normalizes to a fixed point, and reconciles the
   final audit back to the occurrence-level KEEP provenance.
10. Generate representations from the closed canonical corpus as a separate
   stage.

## Known-file boundary

The known-file stage is deliberately path-scoped and positive-match only. It
does not perform general normalization of spaces, blank lines, line-initial or
line-final danda, standalone danda lines, adjacent vowels, or isolated letters.
One exceptional source, brhajj_u.txt, is rebuilt from its retained raw HTML
through the historical pure cleaning stages because an upstream locator-prefix
rule had removed most of its body. Every rule writes occurrence, evidence, and
unified-diff reports before the later document-structure and strict projection
stages run.

The strict final alphabet is closed: lowercase NFC IAST letters, ASCII
apostrophe only when it passes the positive avagraha environment, ASCII |,
ASCII space and LF. Combining accents, digits, editorial punctuation, foreign
letters and other whitespace are forbidden.

## Structure policy

Structure deletion precedes case normalization. In
1_veda/3_ara/sankharu.txt, the standalone title
Śāṅkhāyanāraṇyakam and every standalone ŚĀ or ŚĀ = KU line are explicit
source-specific matches. Generic rules cover first-line standalone titles,
short all-uppercase sigla, explicit edition-note lines, and repeated short
headers containing edition punctuation. Every removal records path, physical
line, rule and removed text.

## Projection policy

- Balanced apparatus containing digits, foreign letters or editorial keywords
  is deleted as a unit; digits and apparatus letters are never converted to |.
- Pure Sanskrit supplied inside square or angle delimiters survives without the
  delimiters. Round and curly edition units are removed.
- Compact source locators are removed as tokens while their following Sanskrit
  body is retained.
- Intraword hyphens are removed; a structural hyphen becomes | when deleting it
  would lose a boundary.
- Periods, commas, semicolons, colons and equivalent surviving textual
  punctuation become |.
- Uppercase Sanskrit body letters are lowercased after titles, sigla and headers
  have been removed.
- ASCII apostrophe survives only when followed immediately by a lowercase IAST
  letter and preceded, ignoring spaces but not crossing danda or LF, by e or o.
  This is the positive orthographic environment for avagraha after e/o sandhi.

All stages write generated detailed audits under reports/cleaning/generated.
Compact summaries and the final manifest remain tracked. Representation
generation never participates in corpus cleaning.

## pre-M0 closure boundary

The pre-M0 mechanical stage removes standalone danda lines and line-initial
single danda, while retaining and spacing line-initial double danda. It does
not change lexical content, isolated letters, adjacent vowels, Sanskrit forms,
or sandhi. The anomaly TSV files are generated only after normalization has
converged, and path-and-content hashes taken before and after that audit must
remain identical.

The following semantic stage keeps the mechanical corpus as
`data/intermediate/gretil/pre_m0_mechanical_closed_gretil_iast` and builds
`data/intermediate/gretil/pre_m0_semantic_candidate_gretil_iast` before an
atomic canonical promotion. Candidate promotion is gated by the strict
character/apostrophe validator and the fixed-point mechanical validator.
Adjacent-vowel repair requires occurrence-level evidence of a literal ASCII
space in an aligned source; hyphens and linguistic expectation are not treated
as proof of a lost lexical boundary.

## Tokenizer-final boundary

The tokenizer-final stage removes the six explicitly excluded sources only
from whitelist-controlled canonical membership; their raw HTML remains
archived. Its source-specific editorial rules are limited to the seven
adjudicated retained files and must hit their recorded occurrence counts
exactly. In particular, `sūtra division emended` is removed as one editorial
suffix, standalone `chapter` lines are deleted, edition apparatus is deleted
as a unit, and Sanskrit headwords before Anandakośa classification tails are
retained. No adjacent-vowel repair, Sanskrit emendation, lateral normalization,
or single-letter deletion belongs to this stage.

## Single-consonant final boundary

The occurrence specification is tracked at
`configs/corpus/pre_m0_single_consonant_keep.tsv`; the materialized copy under
`data/_reports` binds every entry to its original checkpoint context. File-level
or token-level widening is forbidden. Standalone vowels and signs are never
targets of the consonant rule. A whole adjudicated editorial/apparatus unit may
still contain such a token; in that case the unit rule, not the single-letter
rule, removes it.

Confirmed English/editorial triggers include `chapter`, `division`, edition
terminology, and the later `lost`, `only ins`, `denotes`, `check`, `printed`,
and `reads` findings. The already-removed `sūtra division emended` suffix is
kept in the final forbidden-trigger validator so that it cannot regress.

The stage consumes the immutable
`data/intermediate/gretil/pre_m0_single_consonant_input_gretil_iast`
checkpoint and first builds a candidate. Promotion requires 240-file whitelist
membership, strict and mechanical validators, zero confirmed-English
survivors, exact after-audit reconciliation, no newly introduced or increased
adjacent-vowel form, and byte-count preservation of all `ḷ`/`ḹ` characters.

# GRETIL Corpus Cleaning: Technical Provenance and Artifact Guide

This document records the construction, cleaning, adjudication, and final closure of the GRETIL Sanskrit corpus used by `sktlm`.

It serves two purposes:

1. to provide a reproducible technical history of how the canonical corpus was produced; and
2. to explain the status of the files under `reports/cleaning/`, including which reports describe historical checkpoints and which files describe the current final corpus.

The corpus-cleaning pipeline is intentionally separated from representation generation. Script conversion, spacing conditions, tokenization, and model experiments operate only on the closed canonical corpus and do not participate in corpus cleaning.

---

## 1. Final authoritative state

The current closed pre-M0 GRETIL corpus is:

| Field                                                   | Final value                                                        |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| Canonical root                                          | `data/canonical/gretil_iast`                                       |
| Authoritative source whitelist                          | `configs/corpus/gretil_whitelist.txt`                              |
| Authoritative manifest                                  | `data/manifests/canonical_corpus.csv`                              |
| Documents                                               | **240**                                                            |
| Characters                                              | **57,588,079**                                                     |
| Bytes                                                   | **69,864,279**                                                     |
| Corpus SHA256                                           | `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40` |
| Invalid characters                                      | 0                                                                  |
| Invalid apostrophes                                     | 0                                                                  |
| Standalone consonants outside the adjudicated whitelist | 0                                                                  |

The compact report describing this final state is:

```text
reports/cleaning/gretil_canonical_freeze_summary.txt
```

The detailed report for the final text-changing stage is:

```text
reports/cleaning/pre_m0_single_consonant_final_closure.md
```

The final corpus obeys the following methodological boundary:

* source-present Sanskrit spelling is not generally emended;
* sandhi is not reconstructed or corrected;
* lexical boundaries are not inferred from linguistic expectation;
* source-present adjacent-vowel forms are retained unless aligned provenance proves that the pipeline itself removed an ASCII lexical space;
* surviving `ḷ` / `ḹ` material is preserved;
* remaining standalone consonants are retained only when individually adjudicated;
* English, apparatus, sigla, locators, and other editorial material are removed only by positive, documented rules.

---

## 2. Repository storage policy

The repository separates corpus data, configuration, reports, and executable code.

```text
configs/corpus/                  authoritative corpus decisions
data/raw/                        retained source material
data/intermediate/               stage-specific corpus checkpoints/candidates
data/canonical/                  final canonical corpus
data/manifests/                  tracked corpus metadata and hashes

reports/cleaning/                compact tracked cleaning reports
reports/cleaning/checkpoints/    explicitly retained historical checkpoints
reports/cleaning/generated/      reproducible large/detail audits; Git-ignored

src/sktlm/corpus/gretil/cleaning/
                                cleaning implementations
```

The following generated data directories are intentionally ignored by Git:

```text
data/raw/
data/intermediate/
data/processed/
data/canonical/
data/representations/
reports/cleaning/generated/
```

The corpus itself is therefore reproduced from source/configuration/code, while the tracked manifest and compact reports preserve its identity and cleaning history.

Reports do not define corpus membership or linguistic cleaning decisions. Those decisions live in configuration and code. Some audit files may be reread by a later stage as a provenance/consistency gate; in such cases the authoritative decision remains the corresponding tracked configuration, not the report itself.

---

# 3. Pipeline overview

The effective cleaning history is:

```text
GRETIL HTML archive
        |
        v
raw HTML/plain-text extraction
        |
        v
exact whitelist selection
        |
        v
historical mechanical/editorial/hyphen cleanup
        |
        v
pre-strict canonical checkpoint
        |
        v
27-file positive-match cleanup
        |
        v
document-structure cleanup
        |
        v
strict final projection
        |
        v
strict validation + canonical freeze
        |
        v
pre-M0 mechanical closure
        |
        v
pre-M0 semantic/provenance closure
        |
        v
tokenizer-final closure
    246 documents -> 240 documents
        |
        v
standalone-consonant closure
        |
        v
FINAL PRE-M0 CANONICAL CORPUS
```

The corresponding current CLI entry points are:

```text
sktlm-build-gretil-extraction
sktlm-validate-gretil-extraction

sktlm-clean-gretil-known-files
sktlm-clean-gretil-document-structure
sktlm-project-gretil-strict-final
sktlm-validate-gretil-strict
sktlm-freeze-gretil-canonical
sktlm-validate-gretil-freeze

sktlm-close-gretil-pre-m0
sktlm-close-gretil-pre-m0-semantic
sktlm-close-gretil-pre-m0-tokenizer-final
sktlm-close-gretil-pre-m0-single-consonants
```

---

# 4. Stage 0 — Raw GRETIL conversion

## Purpose

The initial source-preparation pass converted the retained GRETIL HTML archive into machine-readable text.

Historical conversion statistics:

```text
HTML files:          2,126
successful:          2,126
failed:              0
output characters:   364,772,990
output lines:        8,022,293
```

This was source preparation, not corpus membership selection.

## Main data

```text
data/raw/gretil/
```

## Tracked reports

```text
reports/cleaning/gretil_raw_summary.txt
reports/cleaning/gretil_cleaning_audit.csv
reports/cleaning/gretil_unknown_characters.csv
```

`gretil_cleaning_audit.csv` contains per-document extraction/normalization statistics such as source characters, extracted characters, canonical characters, removed characters, HTML removal, and unknown-character counts.

These reports describe early corpus construction and should not be interpreted as the final pre-M0 corpus state.

---

# 5. Stage 1 — Exact corpus selection

The experimental corpus was selected by exact GRETIL source paths rather than by directory-wide inclusion.

The authoritative selector is:

```text
configs/corpus/gretil_whitelist.txt
```

The first formal corpus contained **246 documents**.

An early snapshot reported:

```text
documents:              246
canonical characters:   59,943,668
canonical lines:        2,191,186
```

with:

```text
Veda                     40
Epic                     27
Purāṇa                   37
Religious literature     53
Poetry                    34
Śāstra                    55
```

The core boundary policy at this stage was already conservative:

> preserve source-provided lexical boundaries; do not desandhi, infer segmentation, join forms, or transliterate as part of canonical corpus construction.

## Historical report

```text
reports/cleaning/gretil_corpus_summary.txt
```

**Important:** this file describes an earlier 246-document snapshot. It is retained for provenance and is not the authoritative description of the final 240-document corpus.

---

# 6. Stage 2 — Historical preprocessing and pre-strict checkpoint

Several earlier cleaning passes handled HTML/editorial structures, separators, pluta notation, apparatus material, and hyphen conventions.

The current pipeline does not treat the old scripts as the main implementation. Superseded code is retained under:

```text
archive/legacy/cleaning/
```

The retained historical input boundary is:

```text
data/intermediate/gretil/pass3b_v3_hyphen_normalized_gretil_iast
```

A previous canonical state was preserved as:

```text
data/intermediate/gretil/pre_strict_canonical_checkpoint_gretil_iast
```

with tracked checkpoint metadata:

```text
data/manifests/checkpoints/gretil_pre_strict_canonical.csv

reports/cleaning/checkpoints/
    gretil_pre_strict_canonical_freeze_summary.txt
```

That checkpoint contained:

```text
documents:        246
characters:       58,992,314
corpus SHA256:    368731bdd1ce7db98d16341648dc4542a71617befdcebb88b675f7fb380c981c
```

Residual audit flags were still present at this point. The checkpoint is therefore a provenance boundary, not a claim that cleaning was complete.

---

# 7. Stage 3 — Manually adjudicated known-file cleanup

## Command

```text
sktlm-clean-gretil-known-files
```

## Implementation

```text
src/sktlm/corpus/gretil/cleaning/source_specific/known_files.py
```

## Input

```text
data/intermediate/gretil/pre_strict_canonical_checkpoint_gretil_iast
```

## Output

```text
data/intermediate/gretil/known_file_cleaned_gretil_iast
```

## Audit output

```text
reports/cleaning/generated/known_files/
```

The generated directory contains detailed occurrence/evidence/diff material and is intentionally ignored by Git.

## Policy

This stage was restricted to **27 manually adjudicated files**.

Rules were:

* path-scoped;
* positive-match only;
* based on observed source/editorial conventions;
* forbidden from becoming generic corpus-wide Sanskrit corrections.

Examples included removal or handling of:

* standalone `Chapter` labels;
* Tibetan/Wylie editorial material;
* Vinaya locator conventions;
* edition abbreviations and apparatus;
* English structure rows;
* supplied/variant notation;
* source-specific separator conventions.

This stage deliberately did **not** perform general whitespace normalization, danda normalization, adjacent-vowel repair, or isolated-letter deletion.

### `brhajj_u` recovery

`6_sastra/8_jyot/brhajj_u.txt` required special treatment.

An earlier generic locator-prefix rule had removed most of the actual text. The file was therefore rebuilt from its retained raw HTML through the historical pure-cleaning stages instead of accepting the truncated candidate.

This was treated as correction of an upstream pipeline failure, not as textual emendation.

---

# 8. Stage 4 — Document-structure cleanup

## Command

```text
sktlm-clean-gretil-document-structure
```

## Input

```text
data/intermediate/gretil/known_file_cleaned_gretil_iast
```

## Output

```text
data/intermediate/gretil/document_structure_cleaned_gretil_iast
```

## Tracked report

```text
reports/cleaning/gretil_document_structure_summary.txt
```

## Result

```text
files processed:      246
files changed:         78
lines removed:       1,644

characters before: 58,805,524
characters after:  58,782,947
```

Major rule totals:

```text
repeated running headers / abbreviations       883
explicit editorial structure lines             334
standalone sigla                                230
Śāṅkhāyana-specific standalone sigla            146
standalone document titles                       50
Śāṅkhāyana standalone title                       1
```

## Rationale

Structural deletion occurred **before lowercasing**.

This prevents editorial material such as document titles, section sigla, running headers, or edition abbreviations from first being converted into lowercase strings that could then resemble valid Sanskrit.

Non-matching Sanskrit body text was left textually unchanged at this stage.

---

# 9. Stage 5 — Strict canonical projection

## Command

```text
sktlm-project-gretil-strict-final
```

## Implementation

```text
src/sktlm/corpus/gretil/cleaning/finalize.py
```

## Input

```text
data/intermediate/gretil/document_structure_cleaned_gretil_iast
```

## Output

```text
data/intermediate/gretil/strict_final_candidate_gretil_iast
```

## Tracked report

```text
reports/cleaning/gretil_strict_projection_summary.txt
```

## Purpose

This stage projects surviving body text into the closed canonical character system used by the study.

Allowed canonical material is restricted to:

```text
lowercase NFC IAST letters
validated ASCII apostrophe
ASCII |
ASCII space
LF
```

## Main operations

The strict projection:

* removes balanced editorial/apparatus units before character projection;
* removes numeric locators and apparatus;
* removes non-IAST editorial segments;
* removes source-control symbols;
* removes intralexical hyphens;
* maps structural hyphens to `|` where simple deletion would erase a textual boundary;
* normalizes surviving textual punctuation to `|`;
* lowercases uppercase Sanskrit only after structural material has been removed;
* removes non-avagraha apostrophes;
* retains ASCII apostrophe only in the positive orthographic avagraha environment after `e` or `o`.

## Result

```text
files processed:      246
files changed:         232

characters before: 58,782,947
characters after:  58,082,518
delta:               -700,429
```

Selected rule totals:

```text
textual_boundary_normalized             142,254
intra_lexical_hyphen_removed             81,447
structural_hyphen_to_boundary            27,717
source_separator_removed                 25,108
source_word_separator_normalized         21,254
round_editorial_unit_removed             17,859
numeric_structural_token_removed         17,284
inline_edition_siglum_removed             9,225
editorial_delimiter_removed               8,913
square_editorial_unit_removed             8,195
non_avagraha_apostrophe_removed           7,207
curly_apparatus_unit_removed              4,389
textual_sanskrit_uppercase_lowered        3,684
combining_accent_removed                  3,313
numeric_locator_affix_removed             3,029
```

A critical invariant is that apparatus letters and digits are removed as part of their containing editorial unit; they are not blindly converted into danda.

---

# 10. Stage 6 — Strict validation and canonical freeze

## Commands

```text
sktlm-validate-gretil-strict
sktlm-freeze-gretil-canonical
sktlm-validate-gretil-freeze
```

## Validation report

```text
reports/cleaning/gretil_strict_validation_summary.txt
```

The strict gate requires:

```text
invalid characters     = 0
invalid apostrophes    = 0
```

Only a passing candidate may be promoted to:

```text
data/canonical/gretil_iast
```

The freeze stage also updates:

```text
data/manifests/canonical_corpus.csv
reports/cleaning/gretil_canonical_freeze_summary.txt
```

`gretil_canonical_freeze_summary.txt` should be understood as the **current freeze summary**. Later pre-M0 promotion stages regenerate it, so its present contents describe the final 240-document corpus rather than an earlier 246-document freeze.

Historical freeze states are preserved only where explicitly checkpointed under `data/manifests/checkpoints/` and `reports/cleaning/checkpoints/`.

---

# 11. Stage 7 — Pre-M0 mechanical closure

## Command

```text
sktlm-close-gretil-pre-m0
```

## Implementation

```text
src/sktlm/corpus/gretil/cleaning/pre_m0.py
```

## Main tracked outputs

```text
reports/cleaning/pre_m0_final_closure.md
reports/cleaning/pre_m0_final_anomaly_summary.tsv
reports/cleaning/pre_m0_final_anomaly_details.tsv
```

## Purpose

This pass performs only layout-level canonical normalization.

It does not attempt to correct Sanskrit.

The normalization is iterated to a fixed point, with a required final zero-modification pass.

Rules include:

```text
Unicode NFC
LF newline normalization
leading blank-line removal
line-edge ASCII-space removal
collapse multiple ASCII spaces
remove standalone single-danda lines
remove standalone double-danda lines
remove line-initial single danda
canonical danda spacing
collapse repeated blank lines
```

## Result

```text
documents:              246
files modified:          168
fixed-point passes:        2
```

Selected modifications:

```text
leading blank lines removed            363
standalone | lines removed           4,788
standalone || lines removed          5,304
line-start single danda removed      9,490
excess blank lines collapsed        50,315
```

After convergence, the stage ran a **read-only** anomaly audit.

Initial audit totals were:

```text
isolated consonants:       3,395
adjacent-vowel matches:    6,352
```

The anomaly audit itself was required to leave the corpus hash unchanged.

---

# 12. Stage 8 — Pre-M0 semantic/provenance closure

## Command

```text
sktlm-close-gretil-pre-m0-semantic
```

## Implementation

```text
src/sktlm/corpus/gretil/cleaning/semantic.py
```

## Reproducible mechanical checkpoint

The stage rebuilds:

```text
data/intermediate/gretil/pre_m0_mechanical_closed_gretil_iast
```

from:

```text
data/intermediate/gretil/strict_final_candidate_gretil_iast
```

It then builds:

```text
data/intermediate/gretil/pre_m0_semantic_candidate_gretil_iast
```

before promotion.

## Tracked outputs

```text
reports/cleaning/pre_m0_semantic_closure.md
reports/cleaning/pre_m0_non_sanskrit_candidates.tsv
reports/cleaning/pre_m0_remaining_l.tsv
reports/cleaning/pre_m0_adjacent_vowel_provenance.tsv
```

Additional manual-investigation material retained from this phase includes:

```text
reports/cleaning/pre_m0_manual_followup.md
reports/cleaning/pre_m0_manual_followup.tsv
```

These are diagnostic/provenance records, not descriptions of the current final state.

---

## 12.1 Historical contextual `ḷ` normalization

This semantic-closure implementation contained an earlier contextual normalization rule for vowel-adjacent `ḷ` / `ḷh`.

It produced:

```text
ḷ  -> ḍ       487 replacements
ḷh -> ḍh       93 replacements
```

and left 295 occurrences for manual/provenance review.

The surviving forms were recorded in:

```text
reports/cleaning/pre_m0_remaining_l.tsv
```

Subsequent review established that remaining `ḷ` / `ḹ` material included legitimate lexical and metalinguistic uses. Later stages therefore explicitly prohibit further lateral normalization and verify preservation of `ḷ` / `ḹ` counts.

This historical transformation is part of the actual provenance and is retained here rather than retrospectively omitted.

---

## 12.2 Adjacent-vowel provenance

Adjacent non-`ai`/`au` vowel sequences were treated as an audit/provenance problem, not as a Sanskrit correction rule.

After the semantic lateral pass:

```text
adjacent-vowel anomalies:             5,380

PIPELINE_BOUNDARY_LOSS_FIXED:             2
SOURCE_PRESENT:                        2,596
UNRESOLVED:                            2,782

remaining after confirmed repairs:    5,378
```

A space was restored only if an aligned intermediate or raw source contained a literal ASCII lexical space that had demonstrably been lost by the pipeline.

Two confirmed repairs were:

```text
ataeva       -> ata eva
svādhyāyaeva -> svādhyāya eva
```

No repair was authorized merely because:

* a form looked linguistically unlikely;
* a dictionary analysis suggested a boundary;
* a hyphen occurred elsewhere;
* Sanskrit grammar suggested that two lexical items were present.

Source-present and unresolved forms were retained.

Full provenance is stored in:

```text
reports/cleaning/pre_m0_adjacent_vowel_provenance.tsv
```

---

## 12.3 Non-Sanskrit candidate scan

The same stage performed a conservative positive-match audit for editorial, European-language, Tibetan-transliteration, and obvious non-textual residues.

At that point:

```text
candidate spans:      521
files involved:         7
```

The scan was an audit. It did not authorize generic deletion of all English-looking or unusual strings.

The candidate file was:

```text
reports/cleaning/pre_m0_non_sanskrit_candidates.tsv
```

---

# 13. Stage 9 — Tokenizer-final corpus closure

## Command

```text
sktlm-close-gretil-pre-m0-tokenizer-final
```

## Implementation

```text
src/sktlm/corpus/gretil/cleaning/tokenizer_final.py
```

## Immutable input checkpoint

On first execution, the semantic 246-document canonical state is copied to:

```text
data/intermediate/gretil/pre_m0_tokenizer_final_input_gretil_iast
```

This checkpoint is reused rather than silently regenerated from later corpus states.

## Candidate output

```text
data/intermediate/gretil/pre_m0_tokenizer_final_candidate_gretil_iast
```

## Tracked outputs

```text
reports/cleaning/pre_m0_tokenizer_final_closure.md
reports/cleaning/pre_m0_tokenizer_final_cleanup_details.tsv

reports/cleaning/checkpoints/
    pre_m0_non_sanskrit_candidates_before_tokenizer_final.tsv
```

The current implementation also generates single-letter audit tables with default paths:

```text
reports/cleaning/pre_m0_single_letter_tokens.tsv
reports/cleaning/pre_m0_single_letter_summary.tsv
reports/cleaning/pre_m0_single_letter_by_file.tsv
```

These are stage/audit artifacts; not every runtime-generated audit table is necessarily retained in Git after final closure.

---

## 13.1 Source-level exclusions: 246 -> 240

Six sources were removed from **canonical membership**, while their raw HTML remained retained:

```text
5_poetry/4_narr/suksaptu.htm

6_sastra/4_dharma/sutra/apastd_u.htm
6_sastra/4_dharma/sutra/vaikhd_u.htm

6_sastra/8_jyot/bijaganu.htm
6_sastra/8_jyot/brsphutu.htm
6_sastra/8_jyot/lilavatu.htm
```

These sources were excluded because their digital representation was judged unsuitable for the controlled tokenizer corpus, e.g. explicit analytical segmentation, non-surface encoding, or unreliable/non-proofread boundary representation.

No substitute documents were added.

The transition was:

```text
documents:          246 -> 240
characters:  57,987,374 -> 57,600,159
```

Four large, noisy but usable texts were explicitly retained:

```text
3_purana/agp_bi_u.txt
3_purana/nardp1_u.txt
4_rellit/buddh/divyav_u.txt
6_sastra/3_phil/buddh/vakobhau.txt
```

---

## 13.2 Positive-match English/editorial cleanup

Only adjudicated path-specific rules were allowed.

Textually modified retained files at this stage included:

```text
1_veda/5_vedang/2_grhya/kaussu_u.txt
3_purana/agp_bi_u.txt
4_rellit/vaisn/ss2_bhgu.txt
4_rellit/vaisn/ss3_paru.txt
4_rellit/vaisn/vaimp__u.txt
6_sastra/7_ayur/anandk_u.txt
6_sastra/8_jyot/brhajj_u.txt
```

Examples:

```text
kaussu_u      remove exact "sūtra division emended" suffix
agp_bi_u      delete 389 standalone "chapter" lines
ss2_bhgu      delete adjudicated editorial lines
ss3_paru      delete adjudicated editorial lines
vaimp__u      delete edition-apparatus lines
anandk_u      remove English metadata and classification tails
brhajj_u      remove confirmed repeated-a junk line
```

The stage used exact expected-occurrence gates. A path-specific rule was not allowed to silently match more or fewer occurrences than adjudicated.

A surviving-token subsequence guard also prohibited the cleanup from adding, splitting, or rewriting surviving Sanskrit lexical tokens.

This stage explicitly performed:

```text
NO adjacent-vowel repair
NO Sanskrit emendation
NO new ḷ/ḹ normalization
NO standalone-consonant deletion
```

---

# 14. Stage 10 — Final standalone-consonant closure

## Command

```text
sktlm-close-gretil-pre-m0-single-consonants
```

## Implementation

```text
src/sktlm/corpus/gretil/cleaning/single_consonants.py
```

## Authoritative decision file

```text
configs/corpus/pre_m0_single_consonant_keep.tsv
```

This file is the authoritative occurrence-level KEEP specification.

It records:

```text
file
line_no
token
occurrence_count
```

No file-level or token-level widening is permitted.

## Immutable input checkpoint

```text
data/intermediate/gretil/pre_m0_single_consonant_input_gretil_iast
```

## Candidate output

```text
data/intermediate/gretil/pre_m0_single_consonant_candidate_gretil_iast
```

## Runtime provenance/audit outputs

The implementation materializes the KEEP decisions with original context as:

```text
reports/cleaning/pre_m0_single_consonant_keep_whitelist.tsv
```

and generates post-cleanup single-letter audits:

```text
reports/cleaning/pre_m0_single_letter_tokens_after_cleanup.tsv
reports/cleaning/pre_m0_single_letter_summary_after_cleanup.tsv
reports/cleaning/pre_m0_single_letter_by_file_after_cleanup.tsv
```

These are reproducible runtime audit artifacts; their presence in the tracked Git tree is not required for corpus identity.

## Tracked final outputs

```text
reports/cleaning/pre_m0_single_consonant_cleanup_details.tsv
reports/cleaning/pre_m0_single_consonant_final_closure.md
reports/cleaning/gretil_canonical_freeze_summary.txt
```

and the canonical manifest is refreshed:

```text
data/manifests/canonical_corpus.csv
```

---

## 14.1 Consonant decision

Before this pass:

```text
standalone consonants: 3,384
```

The occurrence-level adjudication retained:

```text
348
```

and removed:

```text
3,036
```

Final standalone consonant count:

```text
348
```

Every surviving standalone consonant must reconcile to the exact KEEP specification.

Standalone vowels and signs were not targets of this rule:

```text
a ā i ī u ū ṛ ṝ ḷ ḹ e o ṃ ḥ
```

The consonant rule never deletes characters from ordinary multi-character Sanskrit tokens.

---

## 14.2 Additional confirmed editorial cleanup

The final closure also removed **263 confirmed English/editorial spans** using positive-match rules.

Examples included residual forms involving:

```text
lost
only ins
only in
denotes
check
printed
reads
records
adds
omits
```

and source-specific compact apparatus constructions.

This was not a generic language-identification pass. Only adjudicated units/patterns with expected occurrence gates were removed.

---

## 14.3 Final normalization and guards

After deletion, the corpus was normalized again to the mechanical fixed point.

Final-stage statistics:

```text
documents before / after:                 240 / 240
characters before:                         57,600,159
characters after:                          57,588,079

standalone consonants before:                    3,384
whitelisted consonants retained:                   348
non-whitelisted consonants deleted:              3,036
standalone consonants remaining:                   348

modified files:                                     51
maximum fixed-point passes per file:                 2
confirmed English/editorial spans removed:          263

adjacent-vowel audit before / after:      3,170 / 3,155
new or increased adjacent-vowel forms:                0

ḷ/ḹ characters before / after:              327 / 327
```

Final guards include:

```text
strict character validator                 PASS
strict apostrophe validator                PASS
mechanical fixed-point validator           PASS
240-document whitelist membership          PASS
standalone consonant whitelist             PASS
confirmed English/editorial survivor scan  PASS
adjacent-vowel non-regression               PASS
ḷ/ḹ preservation                            PASS
audit mutation/hash check                  PASS
```

---

# 15. Final corpus invariants

After the final closure, the canonical corpus is defined by the following invariants.

## Character representation

Only the strict canonical alphabet is permitted:

* lowercase NFC IAST;
* validated ASCII apostrophe;
* ASCII danda `|`;
* ASCII space;
* LF.

## Orthographic boundaries

Canonical text preserves source-derived surface representation as far as possible.

The cleaning pipeline does not:

* desandhi text;
* infer lexical segmentation;
* reconstruct compounds;
* normalize ordinary Sanskrit spelling variants;
* correct source-present Sanskrit on phonotactic grounds;
* repair adjacent vowels without source provenance;
* treat remaining technical/metalinguistic `ḷ` / `ḹ` as corruption.

## Editorial material

Removal is based on:

* structural identification;
* path-specific source conventions;
* positive editorial markers;
* exact occurrence gates;
* manually adjudicated contexts.

Broad destructive heuristics are avoided.

---

# 16. Status of files under `reports/cleaning/`

The directory contains reports from different historical stages. They should not all be interpreted as current-state summaries.

## Current/final authoritative reports

```text
gretil_canonical_freeze_summary.txt
pre_m0_single_consonant_final_closure.md
pre_m0_single_consonant_cleanup_details.tsv
```

These describe or directly support the final 240-document pre-M0 corpus.

## Immediately preceding closure reports

```text
pre_m0_tokenizer_final_closure.md
pre_m0_tokenizer_final_cleanup_details.tsv
pre_m0_semantic_closure.md
```

These describe earlier states that are direct ancestors of the final corpus.

## Diagnostic/provenance reports

```text
pre_m0_adjacent_vowel_provenance.tsv
pre_m0_remaining_l.tsv
pre_m0_non_sanskrit_candidates.tsv

pre_m0_final_anomaly_summary.tsv
pre_m0_final_anomaly_details.tsv

pre_m0_manual_followup.md
pre_m0_manual_followup.tsv
```

These record investigation and provenance. They are not declarations that every reported anomaly should be changed.

## Historical construction reports

```text
gretil_raw_summary.txt
gretil_cleaning_audit.csv
gretil_corpus_summary.txt
gretil_document_structure_summary.txt
gretil_strict_projection_summary.txt
gretil_strict_validation_summary.txt
gretil_unknown_characters.csv
```

In particular:

```text
gretil_corpus_summary.txt
```

describes the earlier **246-document / 59,943,668-character** corpus and must not be used as the current final corpus summary.

## Explicit historical checkpoints

```text
reports/cleaning/checkpoints/
    gretil_pre_strict_canonical_freeze_summary.txt
    pre_m0_non_sanskrit_candidates_before_tokenizer_final.tsv
```

These are deliberately retained to bind later decisions to earlier immutable states.

## Broader/legacy corpus report

```text
corpus_manifest_summary.txt
```

This file describes the broader historical weighted multi-source corpus/manifest, including GRETIL, TEI and Ambuda material.

It is **not** the authoritative manifest summary for the closed 240-document GRETIL canonical corpus and should not be used to report the pre-M0 tokenizer corpus size.

The authoritative GRETIL corpus manifest is:

```text
data/manifests/canonical_corpus.csv
```

---

# 17. Artifact summary by stage

| Stage                       | Main corpus/data output                       | Main tracked report(s)                                        |
| --------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| Raw conversion              | `data/raw/gretil/`                            | `gretil_raw_summary.txt`, `gretil_cleaning_audit.csv`         |
| Initial whitelist selection | early intermediate/canonical candidate        | `gretil_corpus_summary.txt`                                   |
| Historical preprocessing    | `pass3b_v3_hyphen_normalized_gretil_iast`     | legacy/generated audits                                       |
| Pre-strict checkpoint       | `pre_strict_canonical_checkpoint_gretil_iast` | checkpoint manifest + freeze summary                          |
| Known-file cleanup          | `known_file_cleaned_gretil_iast`              | `reports/cleaning/generated/known_files/`                     |
| Structure cleanup           | `document_structure_cleaned_gretil_iast`      | `gretil_document_structure_summary.txt`                       |
| Strict projection           | `strict_final_candidate_gretil_iast`          | `gretil_strict_projection_summary.txt`                        |
| Strict validation/freeze    | `data/canonical/gretil_iast`                  | `gretil_strict_validation_summary.txt`, freeze summary        |
| Mechanical pre-M0 closure   | canonical corpus in place                     | `pre_m0_final_closure.md`, anomaly TSVs                       |
| Semantic closure            | mechanical checkpoint + semantic candidate    | `pre_m0_semantic_closure.md`, provenance TSVs                 |
| Tokenizer-final closure     | immutable input + 240-doc candidate           | `pre_m0_tokenizer_final_closure.md`, cleanup details          |
| Single-consonant closure    | immutable input + final candidate             | `pre_m0_single_consonant_final_closure.md`, cleanup details   |
| Final promotion             | `data/canonical/gretil_iast`                  | `gretil_canonical_freeze_summary.txt`, `canonical_corpus.csv` |

---

# 18. Reproducibility boundary

The cleaning history should be interpreted as a sequence of explicit corpus states rather than as a single generic normalization function.

The essential reproducibility chain is:

```text
raw source
  +
exact whitelist
  +
tracked source-specific decisions
  +
cleaning implementation
  +
immutable/checkpointed stage inputs
  +
exact occurrence gates
  +
manifest and corpus hashes
  =
closed canonical corpus
```

Large intermediate corpora and detailed generated audits are intentionally not committed to Git. They are reproducible from retained raw data, configuration, and implementation.

The tracked reports preserve enough information to identify the historical transformations and the current final state without treating obsolete intermediate statistics as current corpus metadata.

---

# 19. Current boundary for future work

Corpus cleaning is closed at the final pre-M0 state.

Downstream work must treat:

```text
data/canonical/gretil_iast
```

as immutable input.

Spacing variants, IAST/Devanagari conversion, tokenizer training, token-quality evaluation, and language-model experiments belong to later stages:

```text
src/sktlm/representations/
src/sktlm/tokenizers/
src/sktlm/experiments/
src/sktlm/evaluation/
```

Any future discovery of ordinary source noise, rare Sanskrit spelling, unusual sandhi, or unresolved adjacent-vowel forms does not by itself reopen corpus construction.

A corpus revision should require a separately versioned correction only if a reproducible pipeline error is shown to have systematically changed the experimental representation.

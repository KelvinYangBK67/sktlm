# pre-M0 semantic closure

- Implementation: gretil-pre-m0-semantic-closure-1
- Canonical SHA256 before: 3877c4af600665cdb03065d7363ea6ecacb103f0907704556000077f83fd61b8
- Canonical SHA256 after: 1f7fb69c764a1e9c4a20b9fbc30640a1574024f216c8a81739b5bbfed5e7d334
- Files processed: 246
- Files modified: 33

## Non-Sanskrit candidates

- Candidate spans: 521
- Files involved: 7
- editorial_or_european: 520
- non_sanskrit_pattern: 1
- Files:
  - `1_veda/5_vedang/2_grhya/kaussu_u.txt`
  - `3_purana/agp_bi_u.txt`
  - `4_rellit/vaisn/ss2_bhgu.txt`
  - `4_rellit/vaisn/ss3_paru.txt`
  - `4_rellit/vaisn/vaimp__u.txt`
  - `6_sastra/7_ayur/anandk_u.txt`
  - `6_sastra/8_jyot/brhajj_u.txt`

Representative candidates:

- 1_veda/5_vedang/2_grhya/kaussu_u.txt:4023 [editorial_or_european] emended
- 3_purana/agp_bi_u.txt:699 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:827 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:935 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:1084 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:1204 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:1289 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:1534 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:1665 [editorial_or_european] chapter
- 3_purana/agp_bi_u.txt:1756 [editorial_or_european] chapter

## ḷ / ḷh normalization

- ḷ → ḍ replacements: 487
- ḷh → ḍh replacements: 93
- Remaining ḷ/ḷh occurrences: 295

Remaining forms are unchanged and listed in pre_m0_remaining_l.tsv.

## Adjacent-vowel provenance

- Anomalies after lateral normalization: 5380
- PIPELINE_BOUNDARY_LOSS_FIXED: 2
- SOURCE_PRESENT: 2596
- UNRESOLVED: 2782
- Remaining anomalies after confirmed repairs: 5378

Only literal ASCII lexical-space evidence in the aligned document intermediate or raw source authorizes repair. Hyphens, generic word expectations, and mixed evidence do not.

Representative provenance rows:

- PIPELINE_BOUNDARY_LOSS_FIXED: 4_rellit/vaisn/ss5_bhku.txt:14245 ataeva [ae] → ata eva; intermediate=ataeva; raw=ata eva
- PIPELINE_BOUNDARY_LOSS_FIXED: 6_sastra/4_dharma/sutra/apastd_u.txt:2349 svādhyāyaeva [ae] → svādhyāya eva; intermediate=-; raw=svādhyāya eva
- SOURCE_PRESENT: 1_veda/2_bra/gopbra_u.txt:1407 ramantae [ae] → ramantae; intermediate=ramantae; raw=ramantae
- SOURCE_PRESENT: 1_veda/2_bra/gopbra_u.txt:3135 śrutaṛṣiḥ [aṛ] → śrutaṛṣiḥ; intermediate=śrutaṛṣiḥ; raw=śrutaṛṣiḥ
- SOURCE_PRESENT: 1_veda/2_bra/gopbra_u.txt:7849 bharadvājāa [āa] → bharadvājāa; intermediate=bharadvājāa; raw=bharadvājāa
- SOURCE_PRESENT: 1_veda/2_bra/gopbra_u.txt:8253 prajigāaya [āa] → prajigāaya; intermediate=prajigāaya; raw=prajigāaya
- UNRESOLVED: 1_veda/2_bra/pncvbr1u.txt:143 enasaenasāvayajanam [ae] → enasaenasāvayajanam; intermediate=-; raw=-
- UNRESOLVED: 1_veda/2_bra/pncvbr1u.txt:6833 goāyuṣī [oā] → goāyuṣī; intermediate=goāyuṣī; raw=-
- UNRESOLVED: 1_veda/2_bra/pncvbr1u.txt:7053 goāyuṣī [oā] → goāyuṣī; intermediate=goāyuṣī; raw=-
- UNRESOLVED: 1_veda/2_bra/pncvbr1u.txt:7059 goāyuṣī [oā] → goāyuṣī; intermediate=goāyuṣī; raw=-

## Verification

- strict invalid characters: 0
- strict invalid apostrophes: 0
- mechanical normalization: fixed point
- standalone danda/space/newline checks: PASS
- provenance audit modifies no source/intermediate file
- freeze manifest/hash validation: PASS (246 files)
- canonical anomaly audit: PASS (0 flagged files, 0 suspicious characters)
- repository tests: PASS (304 passed, 5 warnings)

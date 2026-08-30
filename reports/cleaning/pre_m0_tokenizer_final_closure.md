# pre-M0 tokenizer corpus final closure

- Implementation: gretil-pre-m0-tokenizer-final-closure-1
- Documents: 246 → 240
- Canonical characters: 57987374 → 57600159
- Corpus SHA256 before: 1f7fb69c764a1e9c4a20b9fbc30640a1574024f216c8a81739b5bbfed5e7d334
- Corpus SHA256 after: d2d39c88ac44466fac611f7f519e5c12b1a174680a1f01834717021c302f94f0
- Retained files textually modified: 7

## A. Removed documents

- `5_poetry/4_narr/suksaptu.htm`
- `6_sastra/4_dharma/sutra/apastd_u.htm`
- `6_sastra/4_dharma/sutra/vaikhd_u.htm`
- `6_sastra/8_jyot/bijaganu.htm`
- `6_sastra/8_jyot/brsphutu.htm`
- `6_sastra/8_jyot/lilavatu.htm`

Raw archive members were retained. Their SHA256 values after closure:

- `5_poetry/4_narr/suksaptu.htm`: `8182463149830d341dc3f937a7d9a5280691c32a2ad22ddee44a746f8865991a`
- `6_sastra/4_dharma/sutra/apastd_u.htm`: `6d6ee07e022a07f1cd4d2db5cee706badcee66c94affeac303f20f20180e7722`
- `6_sastra/4_dharma/sutra/vaikhd_u.htm`: `9a108077a1da9cadd9b7561666d1bf3ea33bf9ef6ca9c4ccd79331e9ea8750c8`
- `6_sastra/8_jyot/bijaganu.htm`: `bd2f57ef8697d1e46414c63c6efecded00103a77f1ddd3ef3a73eb1f73a0631f`
- `6_sastra/8_jyot/brsphutu.htm`: `1bfbc4c04ee6a82a03c087bb55ab746dc4450d31891f3c6de1a2346b78eedea1`
- `6_sastra/8_jyot/lilavatu.htm`: `4e91fcee0df46749312c7e85b7bd71f8e94b4c7d381ea68ed5b2dd23de8040c6`

## D. Confirmed non-Sanskrit/editorial removals

| file | rule/category | trigger occurrences | removed spans | removed lines | modified lines |
| --- | --- | ---: | ---: | ---: | ---: |
| 1_veda/5_vedang/2_grhya/kaussu_u.txt | kaussu_sutra_division_emended_suffix / mixed_line_editorial_suffix | 2 | 1 | 0 | 1 |
| 3_purana/agp_bi_u.txt | agp_standalone_chapter / standalone_english_line | 389 | 389 | 389 | 389 |
| 4_rellit/vaisn/ss2_bhgu.txt | ss2_confirmed_editorial_line / english_or_apparatus_line | 9 | 9 | 9 | 9 |
| 4_rellit/vaisn/ss3_paru.txt | ss3_confirmed_editorial_line / english_editorial_line | 2 | 2 | 2 | 2 |
| 4_rellit/vaisn/vaimp__u.txt | vaimp_edition_apparatus_line / edition_apparatus_line | 98 | 75 | 75 | 75 |
| 6_sastra/7_ayur/anandk_u.txt | anandk_english_metadata_line / english_metadata_line | 4 | 4 | 4 | 4 |
| 6_sastra/7_ayur/anandk_u.txt | anandk_metadata_tail / modern_classification_tail | 17 | 17 | 0 | 17 |
| 6_sastra/8_jyot/brhajj_u.txt | brhajj_repeated_a_junk / non_textual_junk_line | 1 | 1 | 1 | 1 |

All actual source-specific rules:

- `1_veda/5_vedang/2_grhya/kaussu_u.txt`: `kaussu_sutra_division_emended_suffix` (remove_editorial_suffix)
- `3_purana/agp_bi_u.txt`: `agp_standalone_chapter` (delete_line)
- `4_rellit/vaisn/ss2_bhgu.txt`: `ss2_confirmed_editorial_line` (delete_line)
- `4_rellit/vaisn/ss3_paru.txt`: `ss3_confirmed_editorial_line` (delete_line)
- `4_rellit/vaisn/vaimp__u.txt`: `vaimp_edition_apparatus_line` (delete_line)
- `6_sastra/7_ayur/anandk_u.txt`: `anandk_english_metadata_line` (delete_line)
- `6_sastra/7_ayur/anandk_u.txt`: `anandk_metadata_tail` (remove_metadata_tail)
- `6_sastra/8_jyot/brhajj_u.txt`: `brhajj_repeated_a_junk` (delete_line)

## E. Unresolved non-Sanskrit candidates

- Candidate spans: 0
- Files: 0
- None under the conservative positive-match scanner.

## F. Standalone single-letter summary

- Occurrences: 8557
- Distinct tokens: 34
- Files: 172

| token | total occurrences | documents |
| --- | ---: | ---: |
| ā | 1675 | 117 |
| a | 1282 | 58 |
| p | 1264 | 9 |
| u | 1183 | 98 |
| n | 948 | 17 |
| e | 593 | 27 |
| ś | 477 | 9 |
| k | 188 | 10 |
| m | 126 | 21 |
| b | 104 | 10 |
| ū | 96 | 22 |
| o | 93 | 25 |
| ḥ | 77 | 13 |
| v | 75 | 20 |
| r | 44 | 17 |
| i | 43 | 20 |
| c | 43 | 17 |
| ī | 35 | 13 |
| d | 31 | 14 |
| t | 26 | 17 |
| ḷ | 25 | 8 |
| ṛ | 25 | 7 |
| s | 18 | 15 |
| ḹ | 18 | 5 |
| ṃ | 14 | 9 |
| ṝ | 14 | 5 |
| h | 13 | 6 |
| l | 8 | 6 |
| y | 8 | 6 |
| g | 5 | 2 |
| j | 2 | 2 |
| ṅ | 2 | 1 |
| ṇ | 1 | 1 |
| ṣ | 1 | 1 |

## G. Top files by standalone single-letter count

| file | occurrences |
| --- | ---: |
| 3_purana/agp_bi_u.txt | 3018 |
| 6_sastra/7_ayur/vagaah_u.txt | 980 |
| 1_veda/5_vedang/1_srauta/sankhssu.txt | 375 |
| 6_sastra/5_artha/kautil_u.txt | 282 |
| 1_veda/2_bra/kausibru.txt | 276 |
| 1_veda/5_vedang/1_srauta/asvss_u.txt | 251 |
| 4_rellit/saiva/kubjt_pu.txt | 245 |
| 6_sastra/4_dharma/sutra/baudhd_u.txt | 213 |
| 6_sastra/6_kama/kamasutu.txt | 164 |
| 1_veda/5_vedang/2_grhya/kaussu_u.txt | 134 |
| 1_veda/2_bra/gopbra_u.txt | 133 |
| 4_rellit/vaisn/vaimp__u.txt | 126 |
| 6_sastra/4_dharma/sutra/vasist_u.txt | 115 |
| 1_veda/5_vedang/1_srauta/vaitss_u.txt | 108 |
| 5_poetry/5_subhas/msubhs_u.txt | 93 |
| 1_veda/5_vedang/2_paris/avpari_u.txt | 86 |
| 1_veda/2_bra/pncvbr1u.txt | 83 |
| 1_veda/2_bra/pncvbr2u.txt | 83 |
| 5_poetry/2_kavya/bhattiku.txt | 72 |
| 5_poetry/2_kavya/padnscpu.txt | 66 |

## H. Validation

- authoritative whitelist membership: PASS (240 documents)
- six stale canonical outputs absent: PASS
- six excluded sources absent from canonical manifest: PASS
- required retained documents present: PASS
- strict character/apostrophe validator: PASS
- mechanical normalization fixed point: PASS
- surviving lexical-token subsequence guard: PASS
- no adjacent-vowel repair rule executed: PASS
- no ḷ/ḹ normalization rule executed: PASS
- single-letter audit hash invariant: PASS
- retained ḷ/ḹ token inventory: PASS (326 → 326)
- retained adjacent-vowel forms: PASS (0 new or increased forms; 153 occurrences removed only with adjudicated apparatus lines)
- authoritative canonical validator: PASS (240 documents)
- canonical anomaly audit: PASS (0 flagged files, 0 suspicious characters)
- repository tests: PASS (311 passed, 5 warnings)

# pre-M0 final single-consonant closure

## Result

- implementation: `gretil-pre-m0-single-consonant-closure-1`
- documents before / after: 240 / 240
- characters before / after: 57,600,159 / 57,588,079
- standalone consonants before: 3,384
- whitelisted consonants retained: 348
- non-whitelisted consonants deleted: 3,036
- standalone consonants remaining: 348
- modified files: 51
- fixed-point normalization pass count (maximum per file): 2
- confirmed English/editorial matched spans removed: 263
- adjacent-vowel audit before / after: 3,170 / 3,155
- adjacent-vowel forms newly introduced or increased: 0
- `ḷ/ḹ` characters before / after: 327 / 327
- standalone vowels/signs removed by the consonant rule: 0
- standalone vowels/signs removed only with adjudicated whole editorial units: 2
- validated avagraha occurrences: 97478
- corpus SHA256 before: `d2d39c88ac44466fac611f7f519e5c12b1a174680a1f01834717021c302f94f0`
- corpus SHA256 after: `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`

`division` has zero occurrences in the immutable input checkpoint because the
previous positive-match tokenizer-final rule already removed the exact
`sūtra division emended` suffix. It is included in the final forbidden-trigger
validator and has zero surviving occurrences.

## English/editorial removals

| file | rule | matched spans |
|---|---|---:|
| `1_veda/4_upa/brup___u.txt` | `english_marker` | 3 |
| `2_epic/mbh/ext/hv_apppu.txt` | `harivamsa_printed_note` | 1 |
| `2_epic/mbh/mbh_02_u.txt` | `english_marker` | 1 |
| `3_purana/vipce_pu.txt` | `vipce_only_ins_apparatus` | 1 |
| `4_rellit/buddh/vinv02_u.txt` | `vinv02_lost_folios_note` | 1 |
| `4_rellit/buddh/vinv171u.txt` | `vinv171_english_summary` | 1 |
| `4_rellit/buddh/vinv_06u.txt` | `english_marker` | 2 |
| `4_rellit/saiva/kubjt_pu.txt` | `kubjt_only_in_note` | 1 |
| `4_rellit/saiva/svact_pu.txt` | `svact_reading_note` | 2 |
| `4_rellit/vaisn/ss6_priu.txt` | `here_adds_or_omits` | 1 |
| `4_rellit/vaisn/ss6_priu.txt` | `vṛ_here_adds` | 1 |
| `4_rellit/vaisn/vaimp__u.txt` | `vaimp_remaining_apparatus_line` | 88 |
| `5_poetry/2_kavya/padnscpu.txt` | `padnsc_only_in_edition_apparatus` | 1 |
| `6_sastra/4_dharma/sutra/baudhd_u.txt` | `compact_komits` | 14 |
| `6_sastra/4_dharma/sutra/baudhd_u.txt` | `compact_omitsom` | 1 |
| `6_sastra/4_dharma/sutra/baudhd_u.txt` | `siglum_adds_or_omits` | 140 |
| `6_sastra/6_kama/kamasutu.txt` | `english_marker` | 1 |
| `6_sastra/6_kama/kamasutu.txt` | `siglum_adds_or_omits` | 3 |

## Remaining one-code-point tokens

| token | count |
|---|---:|
| `a` | 1282 |
| `c` | 16 |
| `d` | 8 |
| `e` | 593 |
| `g` | 2 |
| `h` | 10 |
| `i` | 43 |
| `j` | 1 |
| `k` | 6 |
| `l` | 2 |
| `m` | 123 |
| `n` | 38 |
| `o` | 93 |
| `p` | 1 |
| `r` | 34 |
| `s` | 15 |
| `t` | 18 |
| `u` | 1183 |
| `v` | 64 |
| `y` | 2 |
| `ā` | 1673 |
| `ī` | 35 |
| `ś` | 6 |
| `ū` | 96 |
| `ḥ` | 77 |
| `ḷ` | 25 |
| `ḹ` | 18 |
| `ṃ` | 14 |
| `ṇ` | 1 |
| `ṛ` | 25 |
| `ṝ` | 14 |
| `ṣ` | 1 |

## Validation

- strict character/apostrophe validator: PASS (240 files)
- mechanical fixed-point validator: PASS (240 files)
- standalone consonant occurrence-to-whitelist reconciliation: PASS
- standalone consonants outside whitelist: 0
- canonical membership / manifest membership: 240 / 240
- confirmed English/editorial trigger scan: 0 survivors
- audit corpus mutation check: PASS (hash unchanged)
- full pytest suite: PASS (316 passed, 5 dependency/runtime warnings)

The consonant rule does not inspect or modify adjacent-vowel forms, sandhi,
Sanskrit spelling, `ḷ`/`ḹ`, or lexical material inside longer tokens.

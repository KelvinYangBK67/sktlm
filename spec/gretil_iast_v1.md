# GRETIL IAST Normalization and Devanagari Conversion v1

This spec covers GRETIL HTML input that is still in IAST or related Latin
transliteration. It is intentionally separate from `normalization_v1.md`, which
is for Devanagari input.

## Scope

- Convert GRETIL `.htm` files to cleaned intermediate IAST text.
- Preserve enough line structure for later inspection.
- Convert cleaned IAST text to Devanagari with a small rule-based converter.
- Do not train tokenizer or model in this stage.

## Raw GRETIL Cleaning

### HTML and Metadata

- Strip HTML tags while preserving meaningful line breaks.
- Ignore `head`, `style`, `script`, and encoding tables.
- Use GRETIL `<hr>` blocks and explicit markers such as `###`, `TEXT`, and `Text`
  as conservative body-start hints.
- After the GRETIL header, remove leading English editorial explanation blocks
  until a likely Sanskrit/IAST body line appears.
- Remove footer/trailer metadata such as copyright, encoding notes, URLs, and
  GRETIL usage notes.
- Remove English editorial/commentary note lines, including edition notes,
  accent-note lines, manuscript reading comments, and lines that explain
  numbering systems instead of transmitting the text.
- If a line is reduced to an English editorial fragment after other noise words
  are removed, delete the whole line.
- Skip known non-corpus `rvpp*` files.

### Allowed Raw Characters

- Keep IAST/Latin letters and combining marks.
- Keep ASCII danda markers: `|` and `||`.
- Keep comma `,`.
- Keep apostrophe `'` and `’`.
- Replace unsupported punctuation and symbols with whitespace.
- Words containing uppercase letters are noise and must be removed.
- Words containing non-IAST letters `q`, `w`, `f`, `z`, or `x` are noise and
  must be removed.
- A standalone consonant token is usually noise and is removed.
- Parenthesized text is noise and must be removed.

### Danda and Slash

- Convert final or inline slash danda markers before filtering:
  - `//` -> `||`
  - `/` -> `|`
- Process `//` before `/`.
- Collapse duplicated or noisy danda runs:
  - `|| , ||` -> `||`
  - `|| ||` -> `||`
  - repeated double danda runs -> `||`

### Numbers and References

- Remove paragraph, verse, page, manuscript, and edition numbers.
- Remove reference-only lines such as manuscript/page/chapter locator rows.
- Remove edition/page labels, including:
  - `Vaidya, p`
  - `--- Vaidya, p. N ---`
  - trailing `(ed. Speyer, vol. I)` style notes
- If a page label is followed by useful text, delete only the page label and
  keep the useful text.

### Whitespace

- Preserve ordinary line breaks.
- Do not turn every line break into a blank paragraph.
- Keep only clear paragraph blank runs as a single blank line.
- Delete spaces before commas.
- Delete spaces before danda markers.

## IAST Token Classes

### Consonants `C`

- Longest matches first:
  - `kh`, `gh`, `ch`, `jh`, `th`, `dh`, `ṭh`, `ḍh`, `ph`, `bh`
- Then single consonants:
  - `k`, `g`, `ṅ`, `h`, `c`, `j`, `ñ`, `y`, `ś`, `ṭ`, `ḍ`, `ṇ`,
    `r`, `ṣ`, `t`, `d`, `n`, `l`, `s`, `p`, `b`, `m`, `v`

### Vowels `V`

- Longest matches first:
  - `ai`, `au`
- Then:
  - `a`, `ā`, `i`, `ī`, `u`, `ū`, `ṛ`, `ṝ`, `ḷ`, `ḹ`, `e`, `o`

### Additional Signs `A`

- `ṃ`, `ḥ`, `'`, `|`, `||`

## IAST to Devanagari Rules

- Acute and grave accents are removed before matching.
- Equivalent spellings are normalized before matching:
  - `r̥` -> `ṛ`
  - `r̥̄` -> `ṝ`
  - `l̥` -> `ḷ`
  - `l̥̄` -> `ḹ`
  - `ṁ` -> `ṃ`
  - `ē` -> `e`
  - `ō` -> `o`
- A standalone `oṃ` token is converted to `ॐ`.
- If `C` is followed by `V`, output the consonant plus the dependent vowel sign.
- If `C` is followed by another `C`, whitespace, line end, or punctuation, output
  the consonant with virama.
- If `V` appears at a word start or after whitespace, output the independent
  vowel.
- Always convert additional signs:
  - `ṃ` -> `ं`
  - `ḥ` -> `ः`
  - `'` -> `ऽ`
  - `|` -> `।`
  - `||` -> `॥`

## Pre-Conversion Space Joining

Before IAST to Devanagari conversion, remove the intervening space in these
token patterns:

- `V '`
- `C C`
- `C V`

Examples:

- `yato 'nvaya` -> `यतोऽन्वय`
- `k a` -> `क`
- `t sūrayaḥ` -> `त्सूरयः`

## Devanagari Post-Normalization

- `।` must not remain at line start; delete it if it appears there.
- `,` is preserved, but must not remain at line start; delete it if it appears
  there.
- No line may start with a space.
- Delete spaces before comma and danda markers.
- Preserve ordinary line breaks and keep only clear paragraph blank runs as a
  single blank line.

## Known Limits

- This is a first-pass rule-based converter, not a full philological parser.
- Some GRETIL files contain edition notes and textual fragments that may still
  need file-specific exclusion.
- Suspicious lines should be reviewed through reports before broad deletion
  rules are added.

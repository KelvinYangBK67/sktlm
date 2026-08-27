# Normalization V1

This document defines the first normalization rules for classical Sanskrit text preprocessing.

## Unicode

- Normalize all text to NFC.
- Remove all non-semantic invisible characters and control characters.

## Whitespace

- Preserve ordinary spaces.
- Collapse consecutive ordinary spaces into one ordinary space.
- Convert tabs, non-breaking spaces, full-width spaces, and other non-standard whitespace to ordinary spaces.
- Strip leading and trailing spaces on each line.
- Normalize newline format.
- Preserve single newlines.
- Collapse multiple blank lines into one fixed paragraph separator.

## Sanskrit Punctuation

- Preserve `।`.
- Delete standalone lines that contain only `।`.
- No space is allowed before `।`.
- At most one ordinary space is allowed after `।`.
- Preserve `॥`.
- Delete standalone lines that contain only `॥`.
- No space is allowed before `॥`.
- If `॥` is followed by a newline, a paragraph separator, or the end of text, do not add a space after it.
- Do not allow body text to continue on the same line after `॥`.
- Treat numbering after `॥` as noise; normalize forms such as `॥ ३१॥`, `॥३१॥`, and `॥ २॥` to `॥`.
- Normalize `||` to `॥`, then normalize remaining single `|` to `।`.
- Preserve `ऽ`.

## Western Punctuation

- Delete `,` and `:`.
- Map other sentence-final Western punctuation to `।`.
- Delete all brackets and quotation marks.

## Digits

- Delete all Arabic digits.
- Delete all Devanagari digits.
- Treat all numbering as noise, including title numbers, verse numbers, section numbers, standalone number lines, and layout numbering.

## Character Filtering

- Delete all miscellaneous non-Devanagari characters that are not explicitly preserved by this specification.

## Layout And Editorial Noise

- Before regular text normalization, strip a trailing footer or metadata block at the end of a file.
- In a trailing metadata block, delete lines that start with `%`.
- In a trailing metadata block, delete obvious English notes, URLs, email addresses, copyright notices, encoding notes, file metadata, update notes, and timestamp lines.
- Stop trailer stripping when stable Devanagari body text is reached.
- Delete obvious page numbers, headers, footers, footnote markers, and similar layout residue.
- Delete standalone numbering lines, including numbering lines after titles, chapter names, and section names.
- Delete layout numbering lines such as `६। ७३`.
- Delete critical apparatus symbols, editor-added marks, and versioning markers in this first version.

## Structural Text

- Preserve structural text such as titles, chapter names, and section names.

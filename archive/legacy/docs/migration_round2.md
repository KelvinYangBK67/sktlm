# Round-two migration: controlled experiment semantics

This round changes experiment plumbing, not the intended linguistic or model
semantics. It separates operations that the pilot pipeline previously bundled
together so that every experimental difference is named, fingerprinted, and
testable.

## Canonical data and fixed comparison units

The experimental loader chooses the least manipulated available source for each
manifest row: GRETIL raw IAST when a matching raw file exists, and the manifest
Devanagari text for Ambuda or as a documented legacy fallback. A manifest may
override this choice with `canonical_path` and `canonical_script`.

Every non-empty physical source line becomes a canonical segment with stable
document identity, segment identity, and document-level train/dev/test split.
Filtering and split assignment happen before representation or tokenization.
All comparison conditions therefore receive the same ordered segment IDs; a
fingerprint and an explicit equality check make accidental drift detectable.

Physical lines are an engineering segmentation unit, not a claim about Sanskrit
sentences, padas, or syntactic boundaries.

## Script and spacing are independent factors

The IAST-to-Devanagari transliterator is now a clean script transform. It
preserves whitespace and does not silently join neighboring words. The reverse
Devanagari-to-IAST transform follows the same rule for the supported
orthographic inventory. Both outputs are normalized to Unicode NFC.

Spacing is selected separately:

- `observed`: preserve source whitespace exactly;
- `continuous`: remove horizontal whitespace while retaining line identity;
- `legacy_joined`: reproduce the pilot joining rule for compatibility only.

The former pipeline combined joining, transliteration, and post-normalization.
Code that depended on that behavior must now request `legacy_joined` explicitly.
The compatibility helper remains importable, but the main transliteration API no
longer applies it.

## Tokenizers and legacy artifacts

All tokenizers expose token IDs, displayed pieces, decoded text, and source
spans through one adapter interface. The implemented families are:

- SentencePiece BPE;
- SentencePiece Unigram;
- Unicode code-point characters;
- UTF-8 bytes;
- Unicode extended grapheme clusters.

The tracked 24k BPE and Unigram models were trained on the old joined
Devanagari corpus. Their correct experimental label is
`devanagari/legacy_joined`, and their tokenizer configs include
`legacy_artifact: true`. They are retained for reproducibility and regression
checks, not silently reclassified as models trained on clean `observed` or
`continuous` text.

For controlled BPE or Unigram configs, omit `model_path`. The experiment runner
then fits SentencePiece deterministically from only the selected train segment
IDs and stores the resulting model and vocabulary under the run directory.
Supplying `model_path` always means "load this artifact" and is fingerprinted as
such; it never triggers silent retraining.

An aksara tokenizer is intentionally deferred. A useful aksara baseline requires
a research definition and validation corpus that this engineering refactor must
not invent.

## Evaluation semantics

Tokenizer diagnostics include token count, occupied vocabulary, dependent-vowel
and virama edge rates, grapheme-boundary split rates, invalid grapheme-boundary
rates, and frequency-weighted occupancy. Configurable sandhi-fragment pattern
counts are explicitly labelled heuristic diagnostics; they are not sandhi
accuracy, morphological analysis, or gold linguistic annotation.

Language-model negative log likelihood is normalized as:

- BPC: total negative log likelihood in bits divided by Unicode code points;
- BPB: total negative log likelihood in bits divided by UTF-8 bytes.

Raw token loss or perplexity is not used to rank unlike tokenizers. Bits per
canonical unit is represented by the evaluation API but remains unavailable
unless a future dataset supplies a defensible, fixed canonical-unit annotation.
Boundary precision/recall/F1 is likewise omitted until a gold or declared proxy
boundary source exists.

The tiny backend creates context blocks within individual segments only. It does
not concatenate across document or split boundaries, and it scores each
available within-segment next-token transition once.

## Run provenance and scope boundary

The config-driven runner records the resolved config, manifest and ordered
segment hashes, representation, seed, tokenizer config and model hash, Git
commit (or an explicit unavailable marker), metrics, tokenization previews, and
logs. Result tables use stable columns so matched runs can be aggregated without
changing metric meanings.

This repository still does not implement latent sandhi variables,
morphophonological FSTs, boundary supervision, structure induction, or new
research objectives. Those belong to later research stages after the controlled
baselines are trustworthy.

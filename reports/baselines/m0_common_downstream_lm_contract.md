# M0 common downstream LM contract

Contract version: `m0-common-downstream-lm-v1`.

Every valid cell feeds one independently fitted tokenizer into the existing
`TinyDecoderOnlyTransformer`. Surface-lattice uses its deterministic Viterbi
path for this shared token-sequence task; its complete-DAG marginal likelihood
is reported separately as an intrinsic method metric and never substitutes for
common downstream utility.

The fixed production config is stored in `m0_matrix.yaml`: 32-token context,
64-dimensional embeddings, two heads, two layers, zero dropout, AdamW at
0.001, batch size 8, 20 optimizer steps, seed 0, and CUDA. These values reuse
the repository's existing tiny controlled path rather than introducing a new
scientifically tuned model. Local bounded smoke may override device and step
count, and the effective override is recorded; such an artifact is diagnostic
and cannot satisfy formal aggregation.

Training windows never cross frozen physical-line segments. They match
`SegmentBlockDataset`'s full-context sliding windows, are emitted from frozen
files in manifest order, and are shuffled in deterministic seed-controlled
chunks of at most 1,024 blocks. This bounds Python memory independently of
corpus size. BOS/EOS policy is enabled where the tokenizer supplies those IDs.

Evaluation uses the frozen test split. Autoregressive scoring visits each
within-segment target exactly once with a left-truncated sliding context. It
reports common BPC over evaluated representation code points, common BPB over
evaluated UTF-8 bytes, and bits per canonical unit. A canonical unit is one
Unicode code point in the identity-matched frozen IAST `surface_word` segment;
the evaluator pairs segment IDs and fails if the reference and evaluated
representation differ in membership or order.

The matrix seed initializes Python and Torch; deterministic Torch algorithms are
required. Model class, optimizer, budget, data order, context, delimiter,
scoring, normalization, resolved device, environment, and checkpoint belong to
artifact provenance. Each cell constructs a fresh model and optimizer; no
tokenizer or LM initialization is shared across cells.

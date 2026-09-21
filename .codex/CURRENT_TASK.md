# CURRENT TASK

DATE=2026-09-21
BRANCH=exp/s1m2-reusable-pieces
STATUS=S1M2_V2_SEMANTIC_DIAGNOSTICS_3_AND_5_COMPLETE

Read-only held-out diagnostics #3 and #5 are implemented and locally run on
`artifacts/diagnostics/s1m2_lexeme_probe/noun_high_deva_E000_v2_gate` without
training or inference. Exact selected-training DCS gold metadata was
reconstructible: 1,000 sentences, 4,350 valid canonical wordforms, 996 unique
sentence mappings, and four multiple-ID mappings with identical ordered gold
sequences. Fifty-eight token gold fields are explicitly unavailable.

E000 has 80 unseen and zero seen target gold wordforms. Of 76 evaluable unseen
occurrences, 31 recover exactly (0.407895); four are structurally ambiguous.
Piece metrics cover 56 occurrences: mean piece count 1.75 and whole use
0.267857. The wrong-host audit has 31 correct and 45 wrong occurrences. The
sole descriptive coalition candidate is `dev`: 16 wrong occurrences across
four distinct wrong predicted hosts, with final C=1.128234, M=0.222276, and
R=0.905958. This is held-out top-1 association, not causal or exact-posterior
evidence.

Authority:
`reports/core_methods/reusable_pieces/s1m2_v2_semantic_diagnostics_20260921.md`.
The generated v3 artifacts and training-gold sidecar are local ignored data.
No objective, trainer, inference, grammar, schema, cache, or worker semantics
changed. No new experiment is authorized automatically. Next action is
researcher review of the v3 artifacts and whether a later bounded cell with a
nonempty seen stratum is scientifically useful.

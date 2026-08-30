# Archive

`archive/legacy/` preserves superseded cleaning implementations, compatibility
scripts, pilot models, checkpoints, tokenizer artifacts, and their historical
tests. Nothing below this directory participates in the main package, test
suite, corpus build, representation generation, or baseline pipeline.

Git history is the authoritative record of how current functional modules
evolved. New work must not add version suffixes such as `v2`, `v3`, or
`final_really_final` to modules in `src/`.

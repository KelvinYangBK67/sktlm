# Archive

`archive/legacy/` preserves superseded cleaning implementations, compatibility
scripts, useful pilot source code, historical tests, and migration
documentation. Generated pilot checkpoints and SentencePiece `.model`/`.vocab`
artifacts are intentionally omitted from the public repository. Archived code
or tests may still document paths to those unavailable generated files.

Nothing below this directory participates in the main package, test suite,
corpus build, representation generation, or baseline pipeline.

Git history is the authoritative record of how current functional modules
evolved. New work must not add version suffixes such as `v2`, `v3`, or
`final_really_final` to modules in `src/`.

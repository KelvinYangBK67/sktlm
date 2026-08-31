# CURRENT_TASK.md

Current branch: `exp/m0-baseline-validation`

This branch owns baseline production and validation. It does not own the latent lexical core method.

## Workspace initialization completed

- Local frozen canonical data was copied from `/Users/dongpalmeat/Desktop/canonical/gretil_iast` into ignored `data/canonical/gretil_iast` without modifying the source.
- Local frozen representations were copied from `/Users/dongpalmeat/Desktop/representations` into ignored `data/representations`, excluding `.DS_Store` files.
- `sktlm-validate-gretil-freeze` validates 240 files with freeze ID `9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40`.
- `sktlm-validate-representations` validates all 1,440 representation files across the six formal conditions with the same freeze ID.
- The repo-local `.venv` uses Python 3.11.9 extracted from the checksum-matched official python.org macOS installer. Source `.venv/bin/activate` before using it so its repo-local framework paths are exported.
- Dependencies were installed once with `python -m pip install -e ".[test]"` from `pyproject.toml`.
- `pip check` passes; imports of `sktlm`, `sentencepiece`, `yaml`, `regex`, and `torch` pass.
- Installed key versions: pip 26.2.1, SentencePiece 0.2.2, PyTorch 2.13.0.
- Pytest collects 325 tests.

## Readiness audit

Reusable now:

- SentencePiece BPE and Unigram training/wrappers;
- deterministic Unicode code-point tokenizer;
- shared tokenizer span contract and evaluation diagnostics;
- representation transforms and frozen representation validator;
- generic config-driven runner, dry-run mode, fingerprints, provenance, and artifact layout;
- deterministic train/evaluation split selection.

The tokenizer layer can support the 18 BPE, Unigram, and Unicode code-point cells after formal matrix configs and orchestration are added.

Missing or incomplete:

- no formal 22-condition matrix enumerator/completeness validator;
- no Akṣara-safe BPE implementation (the grapheme tokenizer is not Akṣara-safe BPE);
- no Surface-lattice implementation;
- existing matrix configs cover only legacy diagnostics and include obsolete `observed` names;
- the generic runner dynamically transforms canonical segments rather than consuming the frozen representation manifest directly;
- formal cross-condition provenance/software-version reporting is incomplete.

## Known compatibility status

SentencePiece 0.2.2 deliberately rejects `encode_as_immutable_proto`. Three focused tests fail at `src/sktlm/tokenizers/sentencepiece.py:61` and report that `return_type="proto"` must be used:

- BPE factory encode test;
- Unigram factory encode test;
- experiment runner fitted-BPE test.

Do not pin a random older dependency or change tokenizer semantics to hide this. The next implementation task should add a narrow, tested compatibility adapter.

PyTorch imports successfully but warns that NumPy is absent. `pyproject.toml` remains the dependency authority; adding NumPy would be a shared dependency change and was not folded into workspace setup.

## Ownership map

Baseline-owned:

- `src/sktlm/tokenizers/`;
- baseline-specific experiment runners, configs, tokenizer training, evaluation glue, and tests;
- `reports/baselines/`;
- ignored `artifacts/<baseline...>/`.

Shared/interface-sensitive:

- `src/sktlm/representations/`;
- `src/sktlm/evaluation/`;
- `src/sktlm/experiments/artifacts.py`;
- `src/sktlm/experiments/runner.py`;
- `pyproject.toml`, tracked manifests, `reports/README.md`, `AGENTS.md`, and durable project-state contracts.

Core-owned / do not touch:

- `src/sktlm/latent/`;
- latent lexical phonology, frontend, grammar runtime, candidates, inference, stores, and training;
- latent core experiment entry points and core-method reports.

Current cross-branch diff shows no sibling changes to tokenizer, representation, evaluation, artifact, or generic-runner modules. `pyproject.toml` is already a known shared divergence because the core branch added NumPy.

## Exact next task

Audit and begin implementing the formal 22-condition baseline matrix without modifying frozen data:

1. Add the narrow SentencePiece 0.2.2 proto compatibility adapter and focused regression tests.
2. Specify a baseline-specific matrix schema/enumerator with exactly 22 unique cells and reject obsolete formal condition names.
3. Decide whether the baseline runner should load frozen representation paths directly or verify dynamic transforms against the frozen manifest.
4. Implement the 18 already-supported cells with independent tokenizer fitting and complete provenance.
5. Specify and test Akṣara-safe BPE and Surface-lattice semantics before implementing the remaining four cells.

Do not launch the formal full-corpus production matrix automatically.

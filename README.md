# sktlm

[![tests](https://github.com/KelvinYangBK67/sktlm/actions/workflows/tests.yml/badge.svg)](https://github.com/KelvinYangBK67/sktlm/actions/workflows/tests.yml)

`sktlm` is a reproducible framework for controlled Sanskrit representation,
tokenization, and small language-model experiments. The experimental path keeps
one canonical text identity and fixed train/dev/test membership, then varies
only explicit script, spacing, tokenizer, or model configuration.

## Research direction

The core research problem is latent identity under context-conditioned surface
variation: when should several observed forms share one latent identity, and
when should their variation be explained by a reusable realization grammar
rather than lexical memorization? Sanskrit sandhi is the primary testbed, not
the limit of the intended general claim.

`M₀` names the frozen common benchmark substrate—corpus, six formal
script/spacing representations, and shared provenance/evaluation contracts.
It is not a model milestone. Accordingly, `full-M₀` means full frozen-corpus
extent for one representation condition, not that the latent model is “M0”.
The project is currently in pre-S1M1 infrastructure and capacity calibration,
working toward the first formal Stage 1 scientific milestone. See the
[research roadmap](docs/research_roadmap.md) for the Stage/Milestone
nomenclature and the S1–S3 program.

The current framework provides:

- a whitelist-only formal GRETIL canonical IAST corpus builder with provenance,
  hashes, cleaning audit, and unknown-character reporting;
- canonical physical-line segments with stable `document_id`, `segment_id`, and
  split metadata;
- the formal M0 representation matrix: IAST and Devanagari, each generated as
  `surface_word`, `legacy_joined`, and `continuous`;
- a common tokenizer interface for SentencePiece BPE, SentencePiece Unigram,
  Unicode characters, UTF-8 bytes, and extended grapheme clusters;
- token span, orthographic-boundary, and explicitly heuristic sandhi-fragment
  diagnostics;
- segment-safe tiny Transformer training and likelihood reported as bits per
  Unicode character (BPC) and bits per UTF-8 byte (BPB); and
- config-driven runs with data, tokenizer, Git, metric, preview, and log
  artifacts.

## Setup and validation

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Build and validate the formal GRETIL extraction candidate from the exact paths in
`configs/corpus/gretil_whitelist.txt`:

```bash
sktlm-build-gretil-extraction
sktlm-validate-gretil-extraction
```

This extraction stage writes under `data/intermediate/gretil/` and produces
`data/manifests/gretil_extraction_manifest.csv`. It preserves source-provided
IAST word boundaries and accents. See
`docs/methodology/canonical_corpus.md` for the construction and QC contract.

After extraction, run document-structure cleanup, strict projection and strict
validation in that order with sktlm-clean-gretil-document-structure,
sktlm-project-gretil-strict-final and sktlm-validate-gretil-strict. The freeze
command refuses any nonzero invalid-character or invalid-apostrophe count.
Then freeze and derive the six representation datasets:

```bash
sktlm-freeze-gretil-canonical
sktlm-validate-gretil-freeze
sktlm-generate-representations
sktlm-validate-representations
```

The formal generator creates exactly these six text datasets and no boundary
sidecars. See `docs/methodology/representations.md` for the spacing contracts.

Run a provenance and tokenizer-diagnostics pass without model training:

```bash
sktlm-experiment --config configs/experiments/matrices/script_control/iast_character.yaml --dry-run
```

Run the controlled tiny backend:

```bash
sktlm-experiment --config configs/experiments/tiny_controlled.yaml
```

Each run writes `config.yaml`, `metrics.json`, `result.csv`, data and tokenizer
fingerprints, `git_commit.txt`, `predictions.jsonl`, and `logs.txt` below its
artifact directory. Experiment matrices live under
`configs/experiments/matrices/`; reusable condition fragments live under the
other stage-specific `configs/` directories.

Corpus cleaning, representation generation, tokenizers, experiments, and
evaluation are physically separate packages. Generated data progresses through
`data/intermediate`, `data/canonical`, and `data/representations`; generated
reports live under `reports/`. See `docs/workflows/repository_layout.md` and
`docs/workflows/corpus_cleaning.md`.

Historical pilot source code, superseded cleaning passes, and migration notes
are preserved under `archive/legacy/` and do not participate in the main
pipeline. Generated pilot checkpoints and tokenizer model/vocabulary artifacts
are intentionally excluded from the public repository.

## Reproducible experiment environments

Capture the actual installed environment used for an experiment without
globally exact-pinning the package requirements in `pyproject.toml`:

```bash
python scripts/repro/capture_environment.py --output-dir path/to/output
```

The command writes `environment.json` and a deterministically sorted
`requirements-freeze.txt`, and refuses to overwrite either file. A formal
paper/release run should preserve these alongside its exact Git commit, frozen
input fingerprint, experiment config, and run provenance. Current pre-S1M1
runs are not restarted or retroactively modified to add these files.

## License

Project-authored code, configs, tests, and documentation are licensed under the
[Apache License 2.0](LICENSE). GRETIL source texts and derived textual datasets
have separate terms described in [DATA_LICENSE.md](DATA_LICENSE.md). See also
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

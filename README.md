# sktlm

[![tests](https://github.com/KelvinYangBK67/sktlm/actions/workflows/tests.yml/badge.svg)](https://github.com/KelvinYangBK67/sktlm/actions/workflows/tests.yml)

`sktlm` is a research framework for Sanskrit tokenization and latent
lexical/compositional induction under sandhi and other context-conditioned
surface variation. Its controlled experimental path keeps one canonical text
identity and fixed train/dev/test membership, then varies only explicit
representation or model conditions.

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
S1M1 is scientifically frozen. Across its four completed controlled cells,
visible spacing has a substantially larger effect than script: weakening
boundary evidence makes the flat lexical objective produce a sharper posterior
but a much larger, low-count, over-long lexicon. The next milestone, S1M2,
tests whether reusable untyped pieces can improve compositional sharing while
concatenating exactly to each grammar-licensed lexical form. See the
[research roadmap](docs/research_roadmap.md) for the full S1–S3 program.

## Research documentation

### Start here

- [Research roadmap](docs/research_roadmap.md) — the research question,
  Stage/Milestone nomenclature, and S1–S3 program.
- [Canonical corpus contract](docs/methodology/canonical_corpus.md) — the
  construction, provenance, and freeze invariants of the shared corpus.
- [M₀ representation contract](docs/methodology/representations.md) — the six
  controlled script/spacing representations and the derived M₀′ boundary.
- [S1M1 final scientific checkpoint](reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md)
  — the frozen flat-lexical-identity result.
- [M₀′ formal substrate checkpoint](reports/core_methods/latent_lexicon/m0_prime_formal_checkpoint_20260905.md)
  — the completed, validated corrected IAST-continuous representation.
- [S1M2 continuous benchmark, profiling, and optimization record](reports/core_methods/reusable_pieces/s1m2_continuous_benchmark_definition_20260905.md)
  — the current tracked development record; S1M2 remains in progress.

### Experimental substrate

- [Corpus construction and provenance](docs/methodology/canonical_corpus.md)
  defines the formal GRETIL canonical corpus and freeze invariants.
- [Corpus cleaning workflow](docs/workflows/corpus_cleaning.md) records the
  ordered, audited path from retained source material to the frozen corpus.
- [M₀ representation contract](docs/methodology/representations.md) defines
  the six controlled observation conditions without treating spacing as latent
  lexical structure.

### Stage 1

#### S1M1 — Flat lexical identities — FROZEN

- Main result: [S1M1 final scientific analysis and freeze](reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md).
- Mechanism: [direct association/specialization evidence](reports/core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md#direct-association-level-evidence-yes)
  shows how reduced boundary evidence produces many long, low-count, narrowly
  associated lexical identities, with an explicit weighting qualification.
- Supporting analysis: the [non-continuous representation checkpoint](reports/core_methods/latent_lexicon/noncontinuous_representation_checkpoint_20260901.md)
  gives the controlled 2×2 comparison and bounded qualitative illustrations.
- Detailed historical, calibration, engineering, and provenance records remain
  in the frozen [latent-lexicon report collection](reports/core_methods/latent_lexicon/README.md).

#### M₀′ — Corrected IAST continuous substrate

- [Formal checkpoint](reports/core_methods/latent_lexicon/m0_prime_formal_checkpoint_20260905.md)
  records the validated 240-document result and downstream contract.
- [Construction and validation workflow](docs/workflows/m0_prime.md) explains
  the deterministic derivation from frozen M₀ Devanagari `continuous`.

#### S1M2 — Reusable untyped pieces — IN PROGRESS

- [P1c exact-inference closure](reports/core_methods/reusable_pieces/s1m2_p1c_closure_20260905.md)
  records the completed exact shared/composed inference gate.
- [Trainer integration checkpoint](reports/core_methods/reusable_pieces/s1m2_trainer_integration_20260905.md)
  records completed streaming, resume, and serial/parallel integration.
- [Continuous benchmark, profiling, and exact-optimization record](reports/core_methods/reusable_pieces/s1m2_continuous_benchmark_definition_20260905.md)
  is the current evolving record; it does not claim a final S1M2 result.
- The compact [S1M2 report index](reports/core_methods/reusable_pieces/README.md)
  orders the detailed scientific and implementation checkpoints.

The current framework provides:

- a whitelist-only formal GRETIL canonical IAST corpus builder with provenance,
  hashes, cleaning audit, and unknown-character reporting;
- canonical physical-line segments with stable `document_id`, `segment_id`, and
  split metadata;
- the formal M0 representation matrix: IAST and Devanagari, each generated as
  `surface_word`, `legacy_joined`, and `continuous`;
- a derived M0-prime IAST-continuous representation that preserves lexical
  diphthong/hiatus and aspirate/consonant-plus-`h` distinctions without
  changing frozen M0;
- script-neutral latent lexical induction with a fixed external-sandhi grammar,
  streaming exact inference, deterministic artifacts, and representation-level
  scientific analysis;
- exact shared/composed inference and a streaming trainer for reusable, untyped
  compositional pieces, with continuous profiling and optimization in progress;
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
M0-prime is generated separately from frozen M0 Devanagari `continuous`; see
`docs/workflows/m0_prime.md` for its contract and commands.

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
input fingerprint, experiment config, and run provenance. Completed historical
runs are not restarted or retroactively modified solely to add these files.

## License

Project-authored code, configs, tests, and documentation are licensed under the
[Apache License 2.0](LICENSE). GRETIL source texts and derived textual datasets
have separate terms described in [DATA_LICENSE.md](DATA_LICENSE.md). See also
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

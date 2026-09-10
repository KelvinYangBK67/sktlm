# Reports

This tree contains the tracked, human-readable research record. A file is not
automatically a current authority merely because it is tracked: its scientific
role and lifecycle must be established by this index, a subsystem index, or a
later explicit checkpoint.

## Current research position

- **S1M1 — FROZEN:** the authoritative result is the
  [final scientific checkpoint](core_methods/latent_lexicon/s1m1_final_checkpoint_20260903.md).
  The surrounding [latent-lexicon collection](core_methods/latent_lexicon/README.md)
  is frozen archival material and includes supporting, engineering,
  operational, and superseded records.
- **M₀′ — COMPLETE / VALID:** the
  [formal substrate checkpoint](core_methods/latent_lexicon/m0_prime_formal_checkpoint_20260905.md)
  records the corrected downstream IAST-continuous representation.
- **S1M2 — IN PROGRESS:** P1c exact inference and trainer integration are
  complete; continuous exact profiling and optimization remain active, and no
  final full-corpus S1M2 result is claimed. Start with the
  [reusable-piece index](core_methods/reusable_pieces/README.md).

The [core-method report index](core_methods/README.md) gives the shortest path
to current authorities without rewriting historical checkpoints.

## Directory map

- [`cleaning/`](cleaning/README.md) — corpus-construction evidence,
  occurrence-level decisions, and the final canonical-freeze provenance chain.
- [`representations/`](representations/README.md) — construction and validation
  of the six frozen M₀ script/spacing representations.
- [`baselines/`](baselines/) — tokenizer/model baseline samples and review
  outputs; individual files retain their recorded experimental scope.
- [`core_methods/`](core_methods/README.md) — S1M1 latent-lexicon and S1M2
  reusable-piece research records.
- [`reviews/`](reviews/README.md) — independent-review protocol and templates;
  no completed review panel is represented.

## Authority and lifecycle

| Class | How to use it |
|---|---|
| Authoritative scientific result | A checkpoint explicitly marked final or frozen supports the corresponding scientific claim. For S1M1, use the final checkpoint above. |
| Supporting scientific analysis | Adds mechanism, controlled comparison, or bounded examples without replacing the main result. |
| Implementation/engineering checkpoint | Establishes semantics, equivalence, determinism, or performance gates; it is not by itself a scientific conclusion. |
| Operational/deployment provenance | Records launch, host, transfer, monitoring, or recovery history. It remains useful provenance but is not current project status. |
| Historical/superseded record | Preserved unchanged so the sequence of decisions remains auditable. A later index or checkpoint identifies what supersedes it. |
| Generated/local artifact | Detailed outputs under `artifacts/` or `reports/cleaning/generated/`; normally ignored and never the sole durable narrative for a decision. |

The lifecycle is forward-only: generated evidence that changes a decision is
promoted into a tracked report; later checkpoints supersede earlier status
statements through navigation rather than retrospective rewriting; frozen
S1M1 records remain unchanged.

Reports never contain the canonical corpus itself. A cleaning stage may consume
an explicitly tracked audit as a reproducibility gate, but corpus bytes remain
under `data/` and generated experiment outputs remain under `artifacts/`.

## Data licensing

Some audit and provenance reports contain short excerpts or skipped lines
derived from GRETIL source texts. Those textual portions remain subject to the
GRETIL terms described in [`../DATA_LICENSE.md`](../DATA_LICENSE.md); they are
not relicensed under the project's Apache License 2.0.

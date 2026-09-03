# CURRENT_TASK.md

## Current status

Branch: `exp/s1m1-core-methods`.

The shared generic representation-analysis and artifact-inventory protocol has
been integrated through `main`.

S1M1 scientific status is:

- `AVAILABLE`: IAST/Devanagari × `surface_word`/`legacy_joined`;
- `NA_SCIENTIFICALLY_EXCLUDED`: IAST `continuous`;
- `NA_EXECUTION_INCOMPLETE`: Devanagari `continuous`.

Neither continuous partial learner state enters formal scientific aggregation.

## Immediate task

Finish the S1M1 closure interface on this branch:

1. restore the S1M1-specific final manifest, compact exporter, evidence, and
   human-run workflow from the archived `8b3e8a9` checkpoint;
2. do not restore the S1M1-specific SHA shell;
3. route local source hashing/inventory through the generic
   `inventory_artifacts.py` interface;
4. then run the human archival/aggregation/compact-export sequence.

S1M1 remains `FINAL_ANALYSIS_PENDING_HUMAN_ARCHIVAL_GATE`.

Do not delete scientific source artifacts.
Do not start M0-prime yet.
Do not resume S1M2 P1c yet.

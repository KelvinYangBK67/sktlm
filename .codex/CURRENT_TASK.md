# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`.

The unrestricted six-representation pre-S1M1 gate remains active. The five new
cells are still recorded only as RUNNING at scientific checkpoint:

    375178ba50bd1a1644d65525907692b31413b33d

IAST + `surface_word` is supplied by the four accepted unrestricted replicas.
Core-01 through core-05 remain human-operated; core-06 remains standby. No
completion, final audit, collected result, representation comparison, or S1M1
freeze is inferred in this repository state.

## Absolute operational boundary

Do not contact a VM. Do not run SSH/SCP/rsync, bridge remote operations,
status/polling, collection, remote audit, process inspection/control, restart,
resume, cleanup, deployment, or remote Git. Do not read or expose private
bridge configuration. Running jobs must finish naturally.

The next remote actions are human-only after natural completion:

1. require every `process_tree_summary.json` to report `return_code == 0`;
2. run one final audit per completed run and require `valid == true`;
3. collect each completed run once with `collect --profile scientific` into
   `artifacts/post_gate/collected`;
4. require `benchmark/`, `metrics/`, `remote_audit.json`, and
   `.sktlm-collection.json` in every collection;
5. only then run local aggregation.

## Collection control plane prepared

`collect` now accepts `--profile report|scientific|full`, defaults to `report`
for backward compatibility, and passes the selected profile through the
existing audit-first collection path. Formal scientific collection therefore
needs no separate `pull-results` call. The human-only post-completion template
is:

    python3 scripts/cloud/sktlm_bridge.py collect <RUN_ID> \
      --metrics-id <METRICS_ID> --host-profile <HOST_PROFILE> \
      --profile scientific --output-root artifacts/post_gate/collected

The scientific profile includes the existing report/metrics files plus the
canonical scientific exports and still excludes `learner.sqlite`. Audit
preservation, downloaded-hash validation, transfer receipts, registry checks,
resume identity, and refusal to overwrite remain unchanged. Focused local
synthetic bridge tests passed once (`8 passed in 0.92s`), and Python syntax
compilation passed. No bridge command or remote operation was executed.

## Local post-gate tooling prepared

`scripts/analysis/aggregate_six_representation.py` now implements the
local-only, fail-closed six-cell aggregation contract. Its manifest names exact
local run/metrics/audit paths and exact scientific commits. It refuses missing
or duplicate cells, fixed-K/scoped inputs, undeclared mixed commits, mixed
scientific configuration/provenance, nonzero return code, invalid audit,
missing canonical artifacts, or audit/hash mismatch.

Successful aggregation emits deterministic JSON, tidy TSV, and descriptive
Markdown for:

- latent structure, ambiguity, complexity, and low-count diagnostics;
- 90/95/99/99.9/99.99% lexical mass support;
- candidate graph and overflow diagnostics;
- external-rule usage and normalized distributions;
- three spacing-matched script pairs and six within-script spacing pairs;
- scalar differences/ratios with explicit zero denominators;
- TV and Jensen-Shannon divergence in nats;
- process-tree runtime/resource diagnostics kept separate from science.

The fixed analysis order, quantitative metrics, deterministic qualitative
selection, and interpretation discipline are in
`reports/core_methods/latent_lexicon/post_gate_analysis_protocol.md`. Do not
run the full local aggregation until the human returns with all six audited
collections; hashing/scanning the complete payload may exceed five minutes.

## Independent review preparation

The researcher-authored files `notes/reviewer/reviewer_prompt.txt` and
`notes/reviewer/method.txt` were originally ignored/untracked. They contained
no secrets or private infrastructure and are now preserved byte-for-byte as
tracked review sources.

`scripts/review/review_packet.py` builds and verifies a deterministic,
content-addressed packet from explicit tracked files and validates eventual
raw-review metadata against the packet/prompt/method hashes. Portable relative
path validation rejects POSIX traversal, Windows backslash traversal, and drive
or alternate-stream syntax before any packet or raw-review file is resolved.
The protocol fixes
five independent fresh sessions, the identical frozen packet/prompt, no
cross-review leakage, immutable raw responses, synthesis only after 5/5, and
separate author adjudication. No reviewer LLM has been invoked and no fake raw
review exists.

Formal review remains gated on six completed/audited/collected cells,
post-gate analysis, and a frozen S1M1 method/result packet. The current
researcher prompt names snapshot `add634e...`; before a later formal panel, the
human researcher must verify that the frozen prompt target and packet target
are the intended identical snapshot. No prompt change is allowed after
`reviewer_01` begins.

## Continuous performance preparation

`reports/core_methods/latent_lexicon/continuous_performance_source_analysis.md`
records a static source-only bottleneck map, semantics-preserving candidate
optimizations, scientific changes that cannot be disguised as speedups, and a
future post-freeze profiling-counter plan. No scientific/runtime
implementation, candidate bound, or active configuration changed. Do not tune
from partial cloud metrics.

## Validation and next trigger

Focused synthetic aggregation/review tests passed once:

    14 passed in 3.61s

Python syntax compilation passed before the focused suite. During final local
contract review, one new portable-path regression test passed (`1 passed in
0.19s`); the already-completed 14-test suite was not rerun. No full pytest,
corpus validation, artifact scan, benchmark, cloud command, or reviewer
invocation was run.

Resume only when the human reports natural completion and supplies audited
local collections. Then validate the manifest, run the one local aggregation,
perform the frozen quantitative/qualitative analysis, make the S1M1 freeze
decision, freeze the review packet, and hand the identical packet to five fresh
reviewer sessions.

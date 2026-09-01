# CURRENT_TASK.md

## Current status

Branch: `exp/m0-core-methods`.

The unrestricted non-continuous 2×2 checkpoint is complete locally for IAST
and Devanagari × `surface_word` and `legacy_joined`. Its quantitative and
bounded qualitative evidence is recorded in
`reports/core_methods/latent_lexicon/noncontinuous_representation_checkpoint_20260901.md`.
The result is that spacing effects are much larger than script effects and
that `legacy_joined` amplifies an over-long lexicalization failure mode already
visible under `surface_word`.

The continuous cells are not closed by that evidence. Do not claim a closed
six-cell gate or final M1 conclusion, and do not alter the experiment registry
from this local analysis task. Continuous hosts remain human-operated.
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
canonical scientific exports and still excludes `learner.sqlite`. Its local
inventory now hashes each downloaded scientific file once and supplies those
bytes/SHA identities directly to remote-audit validation; missing audit items,
missing files/inventory rows, and bytes/SHA mismatches still fail closed.
Report-only collection remains backward compatible. Audit preservation,
transfer receipts, registry checks, resume identity, and refusal to overwrite
remain unchanged. Focused synthetic tests and Python syntax compilation pass.
No bridge command or remote operation was executed.

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

The focused bridge and qualitative-selector test files passed together (`51
passed in 1.07s`), and Python syntax compilation passed. The final
bounded local selector stopped after 64 distinct qualified candidates at 132
matched records, reading about 1.67 MB and 1.34 MB from the two Devanagari
analysis files; it produced all four requested additional illustrations. No
full pytest, full-artifact scan, artifact hash recomputation, benchmark, cloud
command, continuous-cell operation, or registry change was performed.

Next, wait for human-supplied completed/audited continuous collections. Then
run the one frozen local aggregation across all six cells, make the S1M1
representation decision, freeze the review packet, and hand the identical
packet to five fresh reviewer sessions. Do not treat the non-continuous 2×2
checkpoint as a six-cell or final-M1 result.

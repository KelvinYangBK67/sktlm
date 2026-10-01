# S1M2 project pause and repository closure — 2026-10-01

## Status and scope

S1M2 is formally paused because the available cloud-compute budget is
exhausted. This is neither a scientific failure nor implementation
abandonment. The repository, CI, branch history, locally established runtime
work, and rescued small evidence have been closed into a resumable state.

```text
PROJECT_STATUS=PAUSED_DUE_TO_BUDGET
PAUSE_REASON=cloud_compute_budget_exhausted
REPO_CLOSURE_STATUS=PASS
CI_STATUS=PASS
S1M2_BRANCH_CLOSURE_STATUS=PASS
```

No VM, SSH, cloud operation, production workload, representative or stress
benchmark, Full M0 run, Pass 1/2/3 workload, corpus training, comparator run,
or large artifact generation was performed during this closure.

## Official branch and branch history

The retained official S1M2 branch is
`exp/s1m2-reusable-pieces`. It was the original science and production line
and contains the reusable-pieces V3 method, production contracts, and prior
Round 3 closure.

`exp/s1m2-runtime-reopen` was intentionally created after scientific freeze so
high-risk runtime/RAM/transient-storage surgery could proceed without directly
modifying the frozen production line. It carried Rounds 3B, 3C, 3D, 3D.1, and
3E-A.

The read-only audit after `git fetch --prune origin` established:

- initial official head:
  `5ec5d5c33a59abe06fadc9bde84f48b380b7fe39`;
- initial runtime head:
  `6b930abd27423987f92de4a2896a25b0730392b8`;
- merge base:
  `5ec5d5c33a59abe06fadc9bde84f48b380b7fe39`;
- official was an ancestor of runtime; runtime was not an ancestor of
  official;
- initial ahead/behind was `0/19` from official to runtime;
- official had no unique commit and runtime had 19 unique commits;
- initial file diff was 32 files, 7,205 insertions, and 600 deletions;
- no true two-sided divergence or scientific conflict existed.

The runtime-only sequence, oldest first, was:

```text
f22502c perf: bound S1M2 runtime telemetry state
ba07b73 perf: add exact neutral pass fast path
16cf561 perf: bound host adjoint working state
fa2b690 perf: stream bundle host support reduction
83cbd3d feat: prepare Pass 1 runtime comparison telemetry
58233d9 feat: add runtime benchmark capture harness
4f8e097 test: compare complete Pass 1 learned state
cf3c141 docs: hand off S1M2 runtime reopen candidate
7dc3495 perf: stream raw reducer keys and host moments
4961efd perf: bound and pack training bundle spools
ac0224b perf: bulk reusable-piece score lookups
b0780a3 perf: reuse exact neutral host templates
2b2c99f test: compare bundled V3 outputs at frozen tolerance
464e4dc perf: align compact batch piece scores
ba47313 docs: hand off S1M2 Round 3B 3C candidate
38557da perf: compact S1M2 reducer storage keys
9b4950c docs: hand off S1M2 Round 3D candidate
ddd5e0d perf: close S1M2 Round 3D.1 and 3E-A
6b930ab docs: hand off S1M2 Round 3D.1 and 3E-A
```

The closure repair added
`56bdde306a9d60d3f84edd66d22ad0fa56df37d0` (`ci: repair S1M2 closure
tests`). The official branch was then advanced with `git merge --ff-only`, so
no merge commit, rebase, squash, force push, or history rewrite was used. The
last implementation/test head before this documentation-only pause handoff is
`56bdde306a9d60d3f84edd66d22ad0fa56df37d0`.

The runtime branch should remain temporarily as a read-only historical alias.
It has no commit absent from the official branch and may be deleted later only
after an explicit administrative retention decision; it was not deleted here.

## CI diagnosis and repair

The last pre-repair runtime run was GitHub Actions run `36878359213` at
`6b930abd27423987f92de4a2896a25b0730392b8`. Python 3.11 and 3.12 each had
four failures; Python 3.10 had the same four plus one SQLite-limit portability
failure. The old official run `36311421670` at `5ec5d5c...` had 28 failures,
most of which were already repaired by the runtime-only commits.

The closure findings were:

| Failure | Root cause | Repair classification |
| --- | --- | --- |
| continuous benchmark exact-model rejection | active benchmark JSON still named historical V1 after `S1M2_MODEL` became the versioned V2 harness model | config |
| lattice expected-count mapping 7/8 | brute-force fixture still used `PhonologicalForm`; the formal lattice API returns role-aware `PieceIdentity` | test |
| outer-composed mapping 44/38 | manual fixture failed to collapse `PieceIdentity.piece`; the formal V2/V3 learned key remains role-neutral `PhonologicalForm` | test |
| full-authorization `repo_root` TypeError | monkeypatch accepted positional arguments only after the necessary production validation API gained `repo_root` | test |
| Python 3.10 SQLite batch-count mismatch | test hard-coded the 3,600-bind path instead of deriving expected batches from the runtime 900-bind fallback | test |

Regression assertions now lock both levels of key semantics: exact lattice
posteriors retain role-aware `PieceIdentity` keys, while
`PieceModel.expected_counts_from_outer()` returns role-collapsed
`PhonologicalForm` keys. No keys were filtered, no roles were merged merely to
satisfy an assertion, and production implementation was not changed.

The workflow still tests Python 3.10, 3.11, and 3.12 and still installs the
normal package contract. It now preinstalls the official CPU-only torch wheel
before `pip install -e ".[test]"`; the cache key includes the workflow and
`pyproject.toml`, preventing restoration of the former approximately 2.8 GB
CUDA-oriented cache. Package dependencies were not weakened or split.

Validation completed in the required order:

- five directly observed failures: 5 passed;
- four related modules: 69 passed;
- full local suite before closure: exit 0;
- full local suite after fast-forward: exit 0;
- expected full-suite accounting: 919 passed, 1 skipped out of 920 collected;
- runtime GitHub Actions run `36882867992`: Python 3.10, 3.11, and 3.12 all
  passed;
- `git diff --check`: passed.

The benchmark audit loaded and hash-verified all six continuous harness entries
as `reusable_pieces_v2`, `condition=continuous`, and only
`iast_m0_prime`/`devanagari`. The exact-model loader invariant was retained.
This V2 benchmark harness is separate from the frozen production V3 contract.

The branch-name audit found no `exp/s1m2-runtime-reopen` hard-code in
code/tests/config. The official `exp/s1m2-reusable-pieces` name remains in the
production/deployment contracts, production fail-closed validation, and their
tests; that is the intended formal branch binding.

GitHub emitted only non-blocking runner notices about Node 20 action migration
and the future `ubuntu-latest` image migration. These are future CI hygiene,
not closure failures.

## Frozen science and completed closure

The frozen S1M2 scientific contract is unchanged:

```text
MODEL=reusable_pieces_v3
PASSES=3
INFERENCE=exact_composed_marginals
GAMMA=1.0
RHO=0.4
PIECE_MAX_LENGTH=8
SUPPORT_EPSILON=0.0
REPRESENTATION=script-neutral pieces + latent phonological-form host
COMPARATOR_RTOL=1e-10
COMPARATOR_ATOL=1e-12
```

No approximation, pruning, sampling, truncation, reduction-order change,
generic sandhi reward, tolerance widening, host-key change, learned role split,
or frozen data/rule change occurred. The atomic
`timing_metrics.partial.json` contract remains local engineering telemetry: it
is updated at durable document commits and finalization success/failure, does
not mask the original exception, and has no comparator authority.

Scientific closure already retained is the accepted V3 semantics and bounded
qualification recorded by Decisions 131–132. Engineering closure already
retained includes the frozen exact implementation and the audited Rounds
3B/3C/3D/3D.1/3E-A code and evidence. CI/local correctness qualification does
not constitute production runtime qualification.

## Production evidence and qualification boundary

Round 3D produced real Core-08 first-document evidence for M0 Devanagari
continuous, Pass 1, W12, 39 bundles, document
`1_veda/2_bra/gopbra_u.txt`. It recorded peak process-tree RSS of approximately
8.69 GiB, removed the prior roughly 60 GiB bundle/shard backlog, and observed a
roughly 20.6 GiB final SQLite file and 20.7 GiB WAL peak over about 67 minutes.
The document commit was durable, but the run later failed at pass finalization
on a small negative `R_cross` caused by accumulated C/Q floating-point drift.
This is production evidence, not a completed Round 3D.1/3E-A qualification.

Round 3D.1 locally retained the normal validator and global eight-ULP rule,
re-reading only suspect persisted supports in canonical order and accepting
only a proved positive binary64 summation envelope. Round 3E-A locally added
BLOB/BLOB transient keys, compatibility with the admitted prior transient
layouts, and a runtime SQLite bind limit capped at 3,600. Persistent canonical
TEXT piece keys, WAL/NORMAL, page cache, transaction boundaries, and scientific
semantics remain unchanged.

```text
ROUND3D1_STATUS=LOCAL_PASS
ROUND3EA_STATUS=LOCAL_PASS
ROUND3D1_VM_QUALIFICATION=PENDING_DUE_TO_BUDGET_PAUSE
ROUND3EA_VM_QUALIFICATION=PENDING_DUE_TO_BUDGET_PAUSE
SCIENTIFIC_COMPARATOR=PENDING_DUE_TO_BUDGET_PAUSE
ROUND3EB_STATUS=PENDING_DUE_TO_BUDGET_PAUSE
VM_QUALIFICATION=PENDING_DUE_TO_BUDGET_PAUSE
```

Do not claim that Round 3D.1, Round 3E-A, Full M0 runtime viability, Pass 1/2/3
production completion, or comparator equivalence is production-qualified.

## Cloud and rescued evidence

The last known connectivity state, which was not re-tested here, is:

| Host | Last known state |
| --- | --- |
| core-01 | host key verification failed |
| core-02 | timeout |
| core-03 | timeout |
| core-04 | host key verification failed |
| core-05 | host key verification failed |
| core-06 | timeout |
| core-07 | timeout |
| core-08 | timeout |
| core-09 | reachable |
| core-10 | reachable |
| core-11 | timeout |

Do not remove host keys or reconnect to core-01/core-04/core-05 without a new,
trusted infrastructure identity. The small-artifact rescue from core-09 and
core-10 is outside this repository at:

```text
Windows: D:\sktlm_cloud_rescue_20261001
WSL: /mnt/d/sktlm_cloud_rescue_20261001
manifest: /mnt/d/sktlm_cloud_rescue_20261001/small_artifact_manifest.json
FILES=162
BYTES=53587795
```

The rescue contains small checkpoints, provenance, metrics, summaries,
audits, logs, and tabular evidence only—not large learner databases, shards,
or topology state. It was not modified, moved, deleted, or broadly analyzed.

## Resume gate and remaining risks

The likely remaining runtime bottleneck is the transient SQLite support
B-tree/WAL/single-writer serialized reducer tail. A possible 3E-B
reducer/storage redesign remains unqualified and must not be inferred from the
local 3E-A result.

Other risks are the absent VM resume proof, absent clean first-document 3E-A
qualification, absent frozen comparator, untrusted/stale VM identities, and
future GitHub runner/action migration notices. None justifies approximation or
a scientific contract change.

```text
RESUME_FIRST_GATE=Round3D1 VM resume proof -> clean Round3EA first-document production qualification -> frozen comparator
REMAINING_LIKELY_BOTTLENECK=transient SQLite support B-tree / WAL / single-writer reducer
NEXT_RESEARCH_GATE=Round3D1 VM resume proof -> clean Round3EA first-document production qualification -> frozen comparator
```

Before any future cloud work, restore the official repository state locally:

```powershell
git fetch --prune origin
git switch exp/s1m2-reusable-pieces
git pull --ff-only origin exp/s1m2-reusable-pieces
python -m pytest -q
```

Then stop and obtain new budget, explicit researcher authorization, and trusted
host/deployment identity. No reusable VM command is prescribed from the stale
connectivity state. The first authorized workload must be the Round 3D.1 VM
resume proof, followed by one clean Round 3E-A first-document production
qualification and the frozen comparator at `rtol=1e-10`, `atol=1e-12`.

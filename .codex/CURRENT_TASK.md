DATE=2026-10-01
BRANCH=exp/s1m2-reusable-pieces
PROJECT_STATUS=PAUSED_DUE_TO_BUDGET
PAUSE_REASON=cloud_compute_budget_exhausted
STATUS=REPO_AND_CI_CLOSED_AWAITING_FUTURE_BUDGETED_RESUME

The S1M2 runtime line has been safely absorbed into the official branch by
fast-forward after ancestry, diff, production-contract, benchmark-contract,
and branch-hardcode audits. The last implementation/test head before the
documentation-only pause handoff is
`56bdde306a9d60d3f84edd66d22ad0fa56df37d0`. Runtime GitHub Actions run
`36882867992` passed on Python 3.10, 3.11, and 3.12. The full local suite
completed with exit 0 before and after the fast-forward (920 collected; 919
passed and one existing environment-specific skip).

No active implementation task remains while the project is paused. Do not run
VM, SSH, cloud, representative/stress, Full M0, production Pass 1/2/3, or
comparator work without renewed budget and explicit researcher authorization.
Do not modify the frozen M0 corpus/rules or the rescue directory.

Scientific V3 remains frozen: `reusable_pieces_v3`, three passes, exact
composed marginals, gamma 1, rho 0.4, piece max length 8, support epsilon 0,
script-neutral piece/latent phonological-form host identity, and comparator
tolerances `rtol=1e-10`, `atol=1e-12`.

```text
ROUND3D1_STATUS=LOCAL_PASS
ROUND3EA_STATUS=LOCAL_PASS
ROUND3D1_VM_QUALIFICATION=PENDING_DUE_TO_BUDGET_PAUSE
ROUND3EA_VM_QUALIFICATION=PENDING_DUE_TO_BUDGET_PAUSE
SCIENTIFIC_COMPARATOR=PENDING_DUE_TO_BUDGET_PAUSE
ROUND3EB_STATUS=PENDING_DUE_TO_BUDGET_PAUSE
VM_QUALIFICATION=PENDING_DUE_TO_BUDGET_PAUSE
REMAINING_LIKELY_BOTTLENECK=transient SQLite support B-tree / WAL / single-writer reducer
NEXT_RESEARCH_GATE=Round3D1 VM resume proof -> clean Round3EA first-document production qualification -> frozen comparator
```

Authority:
`reports/core_methods/reusable_pieces/s1m2_project_pause_20261001.md`

The runtime remote branch is intentionally retained for now as a historical
alias and should only be deleted later by explicit administrative decision.
It contains no commit absent from the official branch.

When work is eventually resumed, first restore and verify the official repo:

```powershell
git fetch --prune origin
git switch exp/s1m2-reusable-pieces
git pull --ff-only origin exp/s1m2-reusable-pieces
python -m pytest -q
```

Then stop until a trusted deployment identity and explicit VM authorization
exist. The first authorized research gate is the Round 3D.1 VM resume proof,
then one clean Round 3E-A first-document production qualification, then the
frozen comparator.

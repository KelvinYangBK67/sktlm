DATE=2026-09-21
BRANCH=exp/s1m2-reusable-pieces
STATUS=S1M2_V3_IMPLEMENTATION_READY_FOR_RESEARCHER_GATE

`reusable_pieces_v3` is implemented locally. It retains role-collapsed phonological-form piece identity and latent phonological wordform hosts, but replaces V2 `R=C-M` with `R_cross=C-Q/C`, where `Q=sum_h S(q,h)^2` is computed after host aggregation. V3 authoritative state stores C/Q/M/R_cross; M is diagnostic only and the scorer uses R_cross. V1 and V2 remain historical/version-separated states.

Optional V3 role diagnostics default off. When enabled they collect bounded disk-backed `S(q,h,r)` aggregate state and compact it to per-form/per-role C_r/Q_r/R_r shadow diagnostics; role never enters the learned parameter or scorer. Held-out semantic diagnostics support V3 #3 wrong-host participation, #4 role pooling, and #5 exact DCS gold-wordform seen/unseen generalization using separate versioned artifacts.

Validation completed locally: py_compile passes; 27 V3/training/semantic-diagnostic focused tests pass; 14 lexeme probe/alignment tests pass. The scheduler/planner regression set gives the same 17 failures / 14 passes on clean baseline c67fe3c and the V3 worktree, so these are pre-existing baseline failures rather than V3 regressions.

No formal V3 E000/E100 training, VM/cloud work, Full M0, representative/stress corpus, or long benchmark has been run.

NEXT_ACTION=RESEARCHER_RUN_V3_E000_THEN_DIAGNOSTICS
Do not start E100 automatically. E000 must purchase the next scientific cell.

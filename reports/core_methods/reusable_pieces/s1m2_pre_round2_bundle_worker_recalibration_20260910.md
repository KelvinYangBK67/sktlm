# S1M2 pre-Round2 bundle worker recalibration — 2026-09-10

Round1 ended by deliberate manual termination after diagnostic convergence.
It validly excludes workers 4 and 8 from the retained search, but did not
complete the formal winner contract; `ROUND1_FORMAL_WINNER=UNRESOLVED`.

Execution bundling removes the document-50 ordered-reducer straggler mechanism
that dominated Round1, so worker count must be recalibrated under the production
bundle scheduler. Active Round2 is now the final worker-selection stage:

| Host | Workload | Workers |
| --- | --- | ---: |
| core-01 | frozen M0 Devanagari continuous representative | 12 |
| core-02 | frozen M0 Devanagari continuous representative | 16 |
| core-03 | frozen M0 Devanagari continuous representative | 24 |
| core-04 | frozen M0 Devanagari continuous stress | 12 |
| core-05 | frozen M0 Devanagari continuous stress | 16 |
| core-06 | frozen M0 Devanagari continuous stress | 24 |

Both workload-specific plans retain complete `ObservedSegment` atomicity and
fix `target_pressure=279047`, `max_segments_per_bundle=256`, and
`max_segment_tokens=128`. They bind the frozen document list, manifest,
representation sequence, planner, plan, and materialization identities.

A worker is eligible only if both workloads pass engineering safety gates.
Each workload uses the existing 10% practical wall-time threshold, then lower
peak process-tree RSS, lower canonical reducer stall, and fewer workers. If
representative and stress cannot agree, workers=20 is reserved for an explicit
decision-critical interpolation; it is not part of the primary matrix.

The former six-workload Round2 readiness stage is retired without replacement.
A PASS result and resolved `WINNER_WORKERS` now feed the unchanged full six-cell
plan directly. Neither subset bundle plan has been materialized and Round2 has
not been executed in this change.

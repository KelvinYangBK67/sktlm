# S1M2 Round1 Diagnostic Closure — 2026-09-09

## Status

Round1 was manually and normally terminated after diagnostic convergence. It
is retained as valid engineering diagnostic evidence, not classified as an
OOM, crash, failed run, or invalid run.

- Formal winner: unresolved
- Worker search lower bound: 12
- Next candidates: 12 / 16 / 24
- Round2: not started
- Full-M0 process running: no

The production Round1 winner-selection contract did not run to normal
completion. Therefore no aggregate winner can be derived or claimed from this
attempt.

## Final observed state

The final researcher snapshot was recorded at elapsed time 02:25:46:

| Host | Workers | Pass | Next doc | Train done | Train | Ready ahead | RSS | load1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| core-01 | 4 | 2 | 50 | 122 | 56.5% | 7 | 1.11 GiB | 2.63 |
| core-02 | 8 | 2 | 50 | 122 | 56.5% | 16 | 2.00 GiB | 1.00 |
| core-03 | 12 | 3 | 50 | 194 | 89.8% | 19 | 2.69 GiB | 4.27 |
| core-04 | 16 | 3 | 50 | 194 | 89.8% | 21 | 3.39 GiB | 2.24 |
| core-05 | 20 | 3 | 50 | 194 | 89.8% | 21 | 3.84 GiB | 1.02 |
| core-06 | 24 | 3 | 50 | 194 | 89.8% | 21 | 4.20 GiB | 1.02 |

## Diagnostic conclusion

Workers 4 and 8 were materially behind configurations with at least 12
workers, so the next worker search can be narrowed to 12, 16, and 24. This run
does not validly determine the exact relative winner among configurations from
12 through 24 workers.

Document index 50 repeatedly became the ordered-reducer straggler across
multiple worker configurations and passes. In particular, configurations with
16, 20, and 24 workers each had 21 later document shards ready while canonical
reduction remained blocked at index 50. The near-idle load1 values around 1 for
workers 20 and 24 show severe tail underutilization at higher worker counts.

Observed memory remained healthy: the largest final process-tree RSS was about
4.20 GiB at 24 workers. The principal Round1 finding is therefore a scheduling
granularity and straggler problem, not a renewed RAM failure. Continuing the
same document-level topology to completion had low additional information
value.

## Manual termination and evidence preservation

The researcher preserved pre-stop checkpoint, process, shard, and resource
evidence plus manual-stop receipts under:

artifacts/s1m2_manual_stops/round1_20260909T154852Z/

The decision record and stop summary classify the attempt as manually
terminated after diagnostic convergence. All six per-host receipts report
MANUALLY_STOPPED; no stop failure requires follow-up.

## Next action

Perform a separate pre-full unit-granularity audit. This closure does not begin
that work and does not predefine the eventual scientific or execution unit.

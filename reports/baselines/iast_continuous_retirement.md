# IAST continuous retirement record

Decision ID: `iast-continuous-representation-validity-v1`

Status: retired from baseline, S1M1, and S1M2 production and formal comparison.

Removing IAST word spaces is not injective. A cross-word hiatus such as
`a + i` becomes `ai`, which the frontend can parse as the standard single IAST
diphthong `/ai/`; the original `/a i/` sequence is therefore unrecoverable.
This is a representation-validity failure before tokenization or learning. It
must not be repaired with boundary escapes, special frontend branches, or a
different frozen representation.

The immutable M0 representation tree and its manifests are not changed. The
versioned baseline condition manifest retains the historical 22-cell design,
marks the four method-specific IAST-continuous cells `retired`, and schedules
only 18 valid cells. Existing diagnostic outputs, if any, belong outside the
formal production artifact root and cannot enter formal aggregation or paper
performance tables.

## Interrupted S1M1 evidence

The pre-existing S1M1 IAST-continuous diagnostic run is not present as a tracked
artifact in this branch. Its supplied audit facts are retained here without an
invented timestamp or additional provenance field: Pass 1 completed; Pass 2
completed; Pass 3 stopped at document 86. The run must not be resumed, restarted,
deleted, or rewritten. Its external audit provenance remains the authority for
details not tracked in this repository.

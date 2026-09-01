# Six-representation gate launch checkpoint (2026-09-01)

Status: **FIVE NEW CELLS RUNNING; NO COMPLETION CLAIM**.

The scientific checkpoint for every running job is:

    375178ba50bd1a1644d65525907692b31413b33d

IAST + surface_word is already supplied by the four accepted unrestricted
replicas. The other five unrestricted M0 cells were manually deployed with a
Git bundle, verified, and launched by the human operator.

| Cell | Host | Run ID | Metrics ID | Launch PID | State |
|---|---|---|---|---:|---|
| IAST + surface_word | accepted replicas | rep01-rep04 (see accepted replica records) | per-replica | n/a | DONE/accepted |
| IAST + legacy_joined | core-01 | cloud_full_m0_iast_legacy_joined_p10_w8_p3 | full_m0_iast_legacy_joined_p10_w8_p3 | 79633 | RUNNING |
| IAST + continuous | core-02 | cloud_full_m0_iast_continuous_p10_w8_p3 | full_m0_iast_continuous_p10_w8_p3 | 67914 | RUNNING |
| Devanagari + surface_word | core-03 | cloud_full_m0_devanagari_surface_word_p10_w8_p3 | full_m0_devanagari_surface_word_p10_w8_p3 | 54346 | RUNNING |
| Devanagari + legacy_joined | core-04 | cloud_full_m0_devanagari_legacy_joined_p10_w8_p3 | full_m0_devanagari_legacy_joined_p10_w8_p3 | 49117 | RUNNING |
| Devanagari + continuous | core-05 | cloud_full_m0_devanagari_continuous_p10_w8_p3 | full_m0_devanagari_continuous_p10_w8_p3 | 52423 | RUNNING |

Core-06 was not deployed or launched and remains standby. Launch PIDs are
operational evidence only; they are not durable scientific results and are
therefore recorded here rather than as registry metrics.

## Prelaunch and input verification

Before launch, all five hosts reported the exact scientific HEAD, branch
exp/m0-core-methods, a clean tree, no previous active sktlm job, and absent
target run/metrics paths.

All five authoritative frozen-input checks returned valid=true with identical
values:

| Field | Value |
|---|---|
| canonical documents | 240 |
| canonical characters | 57,588,079 |
| canonical bytes | 69,864,279 |
| representation files | 1,440 |
| freeze ID | 9c515ca46ad8f9fca7e879c0a1617207bf5ccf3df21930aaa0995227c3942c40 |
| external rule count | 1,218 |
| external rules SHA-256 | 55a204169a1ec442e8ac6e9ca90da1e6510b24998cdeba2d76f95f513bab7e90 |
| representation manifest SHA-256 | c04124b2bc4909750ebedc4e7ec939df3c18edecf1598345ab3f662a21fbc520 |

The successful production deployment used a clean published local Git
checkout, Git bundle transfer over SCP/SSH, remote bundle verification, fetch,
exact fetched-SHA verification, fast-forward-only merge, and exact final HEAD
verification. No working tree was copied to a VM.

Immediately after launch, every new cell reported PID_ALIVE=YES and
PROCESS_SAMPLE=YES.

## Completion boundary

RUNNING does not imply success. No wall time, peak RSS, return code, final
audit, scientific artifact, or cross-cell comparison exists yet. Immediate
samples must not be interpreted as final metrics or scientific evidence.

The next VM operation is human-only and occurs after natural completion:

1. require process_tree_summary.json return_code=0;
2. run one final audit and require valid=true;
3. only then collect results, compare cells, and change registry state to DONE.

Codex did not contact, poll, collect from, audit, stop, restart, resume, or
otherwise modify any VM or running job while recording this checkpoint.

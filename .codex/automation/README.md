# Generic Windows Codex automation

This directory contains one reusable Windows PowerShell 5.1 framework for
bounded Codex tasks. Task-specific instructions stay in a prompt file. Mutable
configuration, state, prompt snapshots, thread identity, and logs stay under
`artifacts/codex_automation/<automation_id>/`, which is gitignored.

The framework does not encode S1M2 or any other scientific task. It consists
of:

- `install_task.ps1`: fail-closed preflight, prompt freeze, runtime creation,
  and one fixed Scheduled Task registration.
- `run_task.ps1`: single-instance repository gate, new-thread launch, exact
  thread-id resume, logging, and status-marker state transitions.
- `control_task.ps1`: read-only status, one extra manual wake, and controlled
  recovery after an external workload.
- `helper.ps1`: shared schema, atomic JSON, schedule, invocation, marker, and
  control-plan functions.

## Install

Run Windows PowerShell as the user who will own the Scheduled Task. An elevated
shell may be required by local Task Scheduler policy.

```powershell
.\.codex\automation\install_task.ps1 `
  -TaskName "SKTLM-S1M2-PreVM-Closure" `
  -AutomationId "s1m2_prevm_closure" `
  -PromptPath "D:\Repositories\sanskrit_llm\notes\prompt\S1M2 Pre-VM Closure Codex Master Prompt.md" `
  -Branch "exp/s1m2-reusable-pieces" `
  -Start "2026-09-07 15:50" `
  -IntervalMinutes 301
```

The installer requires a clean expected branch whose local HEAD exactly equals
`origin/<branch>`. It fetches origin but never pulls, rebases, merges, repairs,
or deletes anything. It refuses an existing task/runtime root and an obvious
active SKTLM automation conflict. It verifies the Codex CLI and ScheduledTasks
commands before registering. By default it does not call
`Start-ScheduledTask`; `-StartNow` is an explicit extra wake.

`-DryRun` performs repository and CLI preflight, creates disposable runtime
files under the system temporary directory, and prints the action/schedule. It
does not query, register, enable, disable, or start a Scheduled Task and does
not start Codex. An explicit `-RuntimeRoot` can place dry-run output in another
disposable location.

## Fixed schedule semantics

`-Start` is the immutable logical anchor. Scheduled times are always:

```text
Start + n * IntervalMinutes
```

If installation occurs after the anchor, the registered first wake is the
next future member of that exact sequence. For an anchor of 15:50 and interval
301, the sequence begins 15:50, 20:51, 01:52, 06:53, 11:54, 16:55. A manual
wake is only one extra `Start-ScheduledTask` call. It never recreates the
trigger, changes the anchor/interval, or re-anchors the next scheduled wake.

Task Scheduler uses `MultipleInstances IgnoreNew`; the runner also uses a
named mutex. These are independent re-entry guards.

## Runtime layout

```text
artifacts/codex_automation/<automation_id>/
  config.json
  state.json
  initial_prompt.txt
  resume_prompt.txt
  logs/
    wake_YYYYMMDD_HHMMSS_mmm_PID.jsonl
    wake_YYYYMMDD_HHMMSS_mmm_PID.stderr.txt
    wake_YYYYMMDD_HHMMSS_mmm_PID.last.txt
```

Do not edit these files manually. The installer freezes both prompts and their
SHA-256 hashes. State replacement is atomic on the same filesystem.

## Thread and response contract

The first wake runs a new `codex exec` thread and extracts the unique
`thread.started.thread_id` from JSONL. Every later wake resumes only that exact
ID and verifies the newly observed ID against stored state. The framework never
uses or constructs `resume --last`.

The final non-empty response line must be exactly one of:

```text
AUTOMATION_STATUS=CONTINUE
AUTOMATION_STATUS=WAITING_EXTERNAL
AUTOMATION_STATUS=COMPLETE
```

Missing, multiple, unknown, or non-final markers fail closed as
`ACTIVE_NO_MARKER` and disable the task.

The state machine is:

```text
READY -> RUNNING -> ACTIVE
                 -> WAITING_EXTERNAL (task disabled)
                 -> COMPLETE         (task disabled permanently)
                 -> fail-closed phase (task disabled)
```

Fail-closed phases include `BLOCKED_DIRTY_TREE`, `BLOCKED_WRONG_BRANCH`,
`BLOCKED_INCOMPATIBLE_HEAD`, `BLOCKED_REMOTE_DIVERGENCE`,
`FAILED_NO_THREAD_ID`, `THREAD_MISMATCH`, `LAST_WAKE_FAILED`,
`ACTIVE_NO_MARKER`, and `LAUNCHER_ERROR`.

Before every Codex invocation, the runner fetches origin and requires:

- the configured branch;
- a clean working tree;
- current HEAD descended from the installed base HEAD;
- current HEAD exactly equal to the configured remote branch;
- unchanged frozen prompt hashes.

It never automatically pulls, rebases, merges, or asks Codex to repair a dirty
tree.

## Control commands

Status is read-only and reports the task/automation state, exact thread ID,
branch and HEAD fields, logs, last result/error/message tail, anchor, interval,
and next scheduled wake:

```powershell
.\.codex\automation\control_task.ps1 `
  -AutomationId "s1m2_prevm_closure" `
  -Action Status
```

One extra manual wake is allowed only for `READY` or `ACTIVE`:

```powershell
.\.codex\automation\control_task.ps1 `
  -AutomationId "s1m2_prevm_closure" `
  -Action Wake
```

This calls the existing task once and does not touch its trigger.

When Codex reports `WAITING_EXTERNAL`, the runner disables the task. After the
researcher completes the requested external workload, resume the same exact
thread without editing state:

```powershell
.\.codex\automation\control_task.ps1 `
  -AutomationId "s1m2_prevm_closure" `
  -Action ResumeExternal `
  -StartNow
```

Without `-StartNow`, `ResumeExternal` changes `WAITING_EXTERNAL` to `ACTIVE`,
enables the task, and waits for the next occurrence in the original schedule.
With `-StartNow`, it also requests one immediate extra wake. Neither form
rebuilds or modifies the trigger. `COMPLETE` cannot be resumed.

## Retiring an old task

Retirement is deliberately manual. Inspect the exact task first, then run:

```powershell
Stop-ScheduledTask -TaskName "EXACT-TASK-NAME"
Unregister-ScheduledTask -TaskName "EXACT-TASK-NAME" -Confirm:$false
```

The generic installer never deletes or overwrites old tasks, state, logs, or
runtime roots. A historical `artifacts/codex_automation/<old-id>/` directory
may be retained as provenance.

## Troubleshooting

- **Access denied:** reopen Windows PowerShell with the rights required by the
  local Task Scheduler policy. Do not weaken framework preflight.
- **Dirty tree:** inspect and resolve it manually. The runner will not stash,
  reset, commit, or ask Codex to repair it.
- **Remote divergence:** reconcile local and remote history manually. The
  framework never pulls, rebases, or merges.
- **THREAD_MISMATCH:** keep the task disabled and inspect `state.json`, JSONL,
  and stderr. Do not enter a replacement thread ID by hand.
- **ACTIVE_NO_MARKER:** inspect the last-message file. The response had no
  unique valid final marker; do not re-enable until the bounded-task contract
  is understood.
- **WAITING_EXTERNAL:** run the exact external command reported by Codex, then
  use `ResumeExternal`; do not edit `state.json`.
- **COMPLETE:** the bounded task is permanently stopped. Create a new prompt,
  automation ID, and Scheduled Task for a genuinely new task.

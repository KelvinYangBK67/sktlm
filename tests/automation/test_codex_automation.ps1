[CmdletBinding()]
param(
    [string]$FrameworkRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Started = Get-Date

if ([string]::IsNullOrWhiteSpace($FrameworkRoot)) {
    $FrameworkRoot = Join-Path (Join-Path $PSScriptRoot "..\..") ".codex\automation"
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Message)
    if ($Expected -cne $Actual) {
        throw "ASSERTION FAILED: $Message expected='$Expected' actual='$Actual'"
    }
}

$FrameworkRoot = [System.IO.Path]::GetFullPath($FrameworkRoot)
$HelperPath = Join-Path $FrameworkRoot "helper.ps1"
. $HelperPath

$Anchor = [datetime]::Parse("2026-09-07T15:50:00")
$Schedule = New-AutomationScheduleDefinition `
    -Anchor $Anchor `
    -IntervalMinutes 301 `
    -Now ([datetime]::Parse("2026-09-07T18:20:00"))
Assert-Equal "2026-09-07 20:51" ($Schedule.RegisteredStart.ToString("yyyy-MM-dd HH:mm")) "next scheduled occurrence"
$ExpectedPreview = @("15:50", "20:51", "01:52", "06:53", "11:54", "16:55")
$ObservedPreview = @($Schedule.Preview | ForEach-Object { $_.ToString("HH:mm") })
Assert-Equal ($ExpectedPreview -join ",") ($ObservedPreview -join ",") "fixed 301-minute sequence"

$ActionDefinition = New-RunnerActionDefinition -RunnerPath "C:\repo\.codex\automation\run_task.ps1" -ConfigPath "C:\runtime\config.json"
Assert-Equal "powershell.exe" $ActionDefinition.Execute "runner executable"
Assert-True ($ActionDefinition.Arguments.Contains('run_task.ps1" -ConfigPath "C:\runtime\config.json"')) "runner action carries exact config path"

$ExactThreadId = "0199cafe-1234-7000-8000-0123456789ab"
$NewInvocation = New-CodexInvocation -Repo "C:\repo" -LastMessagePath "C:\logs\last.txt" -InitialPromptPath "C:\runtime\initial.txt" -ResumePromptPath "C:\runtime\resume.txt" -ThreadId $null
Assert-Equal "NEW" $NewInvocation.Mode "new-thread mode"
Assert-Equal "-" $NewInvocation.ArgumentList[-1] "new prompt stdin"
Assert-True ($NewInvocation.ArgumentList -contains "--approve-for-me") "new invocation uses unattended automatic review"
Assert-True ($NewInvocation.ArgumentList -notcontains "-s") "new invocation does not combine -s with --approve-for-me"
Assert-True ($NewInvocation.ArgumentList -notcontains "--sandbox") "new invocation does not combine --sandbox with --approve-for-me"
Assert-True ($NewInvocation.ArgumentList -notcontains "--dangerously-bypass-approvals-and-sandbox") "new invocation does not bypass sandbox and approvals"
$ResumeInvocation = New-CodexInvocation -Repo "C:\repo" -LastMessagePath "C:\logs\last.txt" -InitialPromptPath "C:\runtime\initial.txt" -ResumePromptPath "C:\runtime\resume.txt" -ThreadId $ExactThreadId
Assert-Equal "RESUME_EXACT" $ResumeInvocation.Mode "resume mode"
Assert-Equal "-C" $ResumeInvocation.ArgumentList[1] "Codex receives explicit repository option"
Assert-Equal "C:\repo" $ResumeInvocation.ArgumentList[2] "Codex receives exact repository path"
Assert-Equal "resume" $ResumeInvocation.ArgumentList[-3] "resume subcommand"
Assert-Equal $ExactThreadId $ResumeInvocation.ArgumentList[-2] "exact thread-id resume"
Assert-True ($ResumeInvocation.ArgumentList -notcontains "--last") "resume --last forbidden"
Assert-True ($ResumeInvocation.ArgumentList -contains "--approve-for-me") "resume invocation uses same unattended policy"
Assert-True ($ResumeInvocation.ArgumentList -notcontains "-s") "resume invocation avoids conflicting sandbox flag"
Assert-True ($ResumeInvocation.ArgumentList -notcontains "--sandbox") "resume invocation avoids long sandbox flag"

$HistoricalTask = [pscustomobject]@{
    TaskName = "sktlm-m0-prime-iast-continuous-v1"
    State = "Ready"
    Actions = @([pscustomobject]@{
        Execute = "powershell.exe"
        Arguments = '-NoProfile -File "C:\historical\one_shot.ps1"'
    })
}
$HistoricalIdentity = Get-GenericAutomationTaskIdentity -Task $HistoricalTask
Assert-True (-not $HistoricalIdentity.IsGeneric) "historical one-shot task is not a generic framework task"
$HistoricalInventory = Get-AutomationTaskInventory -TaskName "SKTLM-New-Generic" -Tasks @($HistoricalTask)
Assert-Equal 0 $HistoricalInventory.ExactTaskCount "historical task does not conflict by unrelated name"
Assert-Equal 0 $HistoricalInventory.GenericTasks.Count "historical task does not become a prefix-based conflict"
$ExactTaskInventory = Get-AutomationTaskInventory -TaskName $HistoricalTask.TaskName -Tasks @($HistoricalTask)
Assert-Equal 1 $ExactTaskInventory.ExactTaskCount "exact same TaskName remains fail-closed"

$RepoMutexA = Get-AutomationRepoMutexName -Repo "C:\repo"
$RepoMutexARepeat = Get-AutomationRepoMutexName -Repo "c:\REPO\."
$RepoMutexB = Get-AutomationRepoMutexName -Repo "C:\other-repo"
Assert-Equal $RepoMutexA $RepoMutexARepeat "repository mutex is deterministic for canonical path"
Assert-True ($RepoMutexA -cne $RepoMutexB) "different repositories receive independent mutexes"

$Continue = Resolve-AutomationStatusMarker -Text "done`r`nAUTOMATION_STATUS=CONTINUE`r`n"
Assert-True $Continue.Valid "CONTINUE marker valid"
Assert-Equal "ACTIVE" $Continue.Phase "CONTINUE transition"
Assert-True (-not $Continue.DisableTask) "CONTINUE keeps task enabled"
$Waiting = Resolve-AutomationStatusMarker -Text "command`nAUTOMATION_STATUS=WAITING_EXTERNAL`n"
Assert-True $Waiting.Valid "WAITING_EXTERNAL marker valid"
Assert-Equal "WAITING_EXTERNAL" $Waiting.Phase "WAITING_EXTERNAL transition"
Assert-True $Waiting.DisableTask "WAITING_EXTERNAL disables task"
$Complete = Resolve-AutomationStatusMarker -Text "finished`nAUTOMATION_STATUS=COMPLETE"
Assert-True $Complete.Valid "COMPLETE marker valid"
Assert-Equal "COMPLETE" $Complete.Phase "COMPLETE transition"
Assert-True $Complete.DisableTask "COMPLETE disables task"
foreach ($InvalidText in @(
    "no marker",
    "AUTOMATION_STATUS=CONTINUE`ntext after",
    "AUTOMATION_STATUS=CONTINUE`nAUTOMATION_STATUS=COMPLETE",
    "AUTOMATION_STATUS=UNKNOWN"
)) {
    $Invalid = Resolve-AutomationStatusMarker -Text $InvalidText
    Assert-True (-not $Invalid.Valid) "invalid marker fails closed"
    Assert-Equal "ACTIVE_NO_MARKER" $Invalid.Phase "invalid marker phase"
    Assert-True $Invalid.DisableTask "invalid marker disables task"
}

$ThreadIds = @(Get-ThreadIdsFromJsonLines -Lines @(
    '{"type":"thread.started","thread_id":"0199cafe-1234-7000-8000-0123456789ab"}',
    '{"type":"item.completed","item":{"type":"agent_message"}}'
))
Assert-Equal 1 $ThreadIds.Count "one observed thread id"
Assert-Equal $ExactThreadId $ThreadIds[0] "observed thread id"

$WakePlan = Get-AutomationControlPlan -Action Wake -Phase ACTIVE -ThreadId $ExactThreadId
Assert-True $WakePlan.StartTask "Wake starts existing task once"
Assert-True (-not $WakePlan.EnableTask) "Wake does not re-enable"
Assert-True (-not $WakePlan.ModifyTrigger) "Wake preserves trigger"
$ResumePlan = Get-AutomationControlPlan -Action ResumeExternal -Phase WAITING_EXTERNAL -ThreadId $ExactThreadId -StartNow
Assert-Equal "ACTIVE" $ResumePlan.NewPhase "ResumeExternal transition"
Assert-True $ResumePlan.EnableTask "ResumeExternal enables task"
Assert-True $ResumePlan.StartTask "ResumeExternal StartNow extra wake"
Assert-True (-not $ResumePlan.ModifyTrigger) "ResumeExternal preserves trigger"
$RecoveryPlan = Get-AutomationControlPlan -Action RecoverPreThread -Phase LAUNCHER_ERROR -ThreadId $null
Assert-Equal "READY" $RecoveryPlan.NewPhase "RecoverPreThread returns state to READY"
Assert-True $RecoveryPlan.EnableTask "RecoverPreThread enables the existing task"
Assert-True (-not $RecoveryPlan.StartTask) "RecoverPreThread without StartNow waits for the fixed schedule"
Assert-True (-not $RecoveryPlan.ModifyTrigger) "RecoverPreThread preserves the fixed trigger"
$RecoveryWakePlan = Get-AutomationControlPlan -Action RecoverPreThread -Phase LAUNCHER_ERROR -ThreadId $null -StartNow
Assert-True $RecoveryWakePlan.StartTask "RecoverPreThread StartNow is one extra wake"
Assert-True (-not $RecoveryWakePlan.ModifyTrigger) "RecoverPreThread StartNow still preserves trigger"
$UnsafePlanRejected = $false
try { [void](Get-AutomationControlPlan -Action RecoverPreThread -Phase WAITING_EXTERNAL -ThreadId $null) }
catch { $UnsafePlanRejected = $true }
Assert-True $UnsafePlanRejected "non-launcher phase recovery is rejected"
$ThreadedRecoveryRejected = $false
try { [void](Get-AutomationControlPlan -Action RecoverPreThread -Phase LAUNCHER_ERROR -ThreadId $ExactThreadId) }
catch { $ThreadedRecoveryRejected = $true }
Assert-True $ThreadedRecoveryRejected "non-empty thread recovery is rejected"

$FixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) "sktlm_automation_test_$([guid]::NewGuid().ToString('N'))"
$FixtureRoot = [System.IO.Path]::GetFullPath($FixtureRoot)
$SystemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if (-not $FixtureRoot.StartsWith($SystemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe fixture path: $FixtureRoot"
}
$MutexHolder = $null
$MutexAsync = $null

try {
    $BareRepo = Join-Path $FixtureRoot "origin.git"
    $FixtureRepo = Join-Path $FixtureRoot "repo"
    $RuntimeRoot = Join-Path $FixtureRoot "runtime"
    New-Item -ItemType Directory -Path $FixtureRoot | Out-Null

    $MutexSignal = Join-Path $FixtureRoot "mutex-holder-ready.txt"
    $MutexHolder = [powershell]::Create()
    $MutexHolderScript = @'
param($LoadedHelperPath, $HeldMutexName, $ReadyPath)
. $LoadedHelperPath
$heldLock = Enter-AutomationMutex -Name $HeldMutexName
try {
    if (-not $heldLock.Acquired) { throw "holder failed to acquire fixture mutex" }
    Write-Utf8NoBom -Path $ReadyPath -Text "READY"
    Start-Sleep -Milliseconds 1200
}
finally {
    Exit-AutomationMutex -Lock $heldLock
}
'@
    [void]$MutexHolder.AddScript($MutexHolderScript).AddArgument($HelperPath).AddArgument($RepoMutexA).AddArgument($MutexSignal)
    $MutexAsync = $MutexHolder.BeginInvoke()
    $MutexWait = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-Path -LiteralPath $MutexSignal -PathType Leaf) -and $MutexWait.Elapsed.TotalSeconds -lt 3) {
        Start-Sleep -Milliseconds 20
    }
    Assert-True (Test-Path -LiteralPath $MutexSignal -PathType Leaf) "fixture holder acquired repository mutex"
    $ContendedLock = Enter-AutomationMutex -Name $RepoMutexA
    try {
        Assert-True (-not $ContendedLock.Acquired) "same-repository mutex contention skips concurrent execution"
    }
    finally {
        Exit-AutomationMutex -Lock $ContendedLock
    }
    [void]$MutexHolder.EndInvoke($MutexAsync)
    $MutexHolder.Dispose()
    $MutexHolder = $null
    $MutexAsync = $null

    & git.exe init --bare $BareRepo | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "fixture bare git init failed" }
    & git.exe init $FixtureRepo | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "fixture git init failed" }
    & git.exe -C $FixtureRepo branch -M automation-test
    New-Item -ItemType Directory -Path (Join-Path $FixtureRepo ".codex") | Out-Null
    Copy-Item -LiteralPath $FrameworkRoot -Destination (Join-Path $FixtureRepo ".codex\automation") -Recurse
    $FixturePrompt = Join-Path $FixtureRepo "bounded_prompt.txt"
    Write-Utf8NoBom -Path $FixturePrompt -Text "Perform one bounded fixture task.`r`n"
    & git.exe -C $FixtureRepo add .
    & git.exe -C $FixtureRepo -c user.name=AutomationTest -c user.email=automation@example.invalid commit -m fixture | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "fixture commit failed" }
    & git.exe -C $FixtureRepo remote add origin $BareRepo
    & git.exe -C $FixtureRepo push -u origin automation-test | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "fixture push failed" }

    $FixtureInstaller = Join-Path $FixtureRepo ".codex\automation\install_task.ps1"
    $DryRunOutput = @(
        & $FixtureInstaller `
            -TaskName "SKTLM-Automation-Framework-DryRun" `
            -AutomationId "framework_dryrun" `
            -PromptPath $FixturePrompt `
            -Branch "automation-test" `
            -Start $Anchor `
            -IntervalMinutes 301 `
            -Repo $FixtureRepo `
            -DryRun `
            -RuntimeRoot $RuntimeRoot 6>&1
    )
    Assert-True (($DryRunOutput -join "`n").Contains("DRY_RUN=PASS")) "installer dry-run passes"
    Assert-True (($DryRunOutput -join "`n").Contains("SCHEDULED_TASK_REGISTERED=NO")) "dry-run does not register task"
    Assert-True (($DryRunOutput -join "`n").Contains("CODEX_STARTED=NO")) "dry-run does not start Codex"

    $DryRoot = Join-Path $RuntimeRoot "framework_dryrun"
    $Config = Read-AutomationJson -Path (Join-Path $DryRoot "config.json")
    Assert-AutomationConfig -Config $Config
    $State = Read-AutomationJson -Path (Join-Path $DryRoot "state.json")
    Assert-AutomationState -State $State -Config $Config
    Assert-Equal "READY" $State.phase "initial state phase"
    Assert-Equal $null $State.thread_id "initial thread id"
    $State.last_error = "atomic-roundtrip"
    Write-AutomationJsonAtomic -Path (Join-Path $DryRoot "state.json") -Value $State
    $RoundTripState = Read-AutomationJson -Path (Join-Path $DryRoot "state.json")
    Assert-Equal "atomic-roundtrip" $RoundTripState.last_error "atomic state replacement"
    Assert-True (-not [bool]$Config.registration_performed) "dry-run config records no registration"
    Assert-Equal ($Anchor.ToString("o")) (([datetime]::Parse([string]$Config.schedule_anchor)).ToString("o")) "logical anchor retained"
    $Registered = [datetime]::Parse([string]$Config.registered_start)
    $DeltaMinutes = ($Registered - $Anchor).TotalMinutes
    Assert-Equal 0 ([int]$DeltaMinutes % 301) "registered start stays on fixed sequence"
    $FrozenPrompt = [System.IO.File]::ReadAllText([string]$Config.initial_prompt_path)
    Assert-True ($FrozenPrompt.Contains("Perform one bounded fixture task.")) "prompt frozen"
    Assert-True ($FrozenPrompt.Contains("AUTOMATION_STATUS=WAITING_EXTERNAL")) "status contract appended"
    Assert-True ([string]$Config.task_action.arguments -notmatch "framework_dryrun.*run_task.ps1") "runner remains repo-generic"

    $RootConflictRejected = $false
    try {
        & $FixtureInstaller `
            -TaskName "SKTLM-Automation-Framework-Second" `
            -AutomationId "framework_dryrun" `
            -PromptPath $FixturePrompt `
            -Branch "automation-test" `
            -Start $Anchor `
            -IntervalMinutes 301 `
            -Repo $FixtureRepo `
            -DryRun `
            -RuntimeRoot $RuntimeRoot 6>&1 | Out-Null
    }
    catch {
        $RootConflictRejected = $_.Exception.Message.Contains("Automation directory already exists")
    }
    Assert-True $RootConflictRejected "exact same runtime root remains fail-closed"

    $GenericTask = [pscustomobject]@{
        TaskName = [string]$Config.task_name
        State = "Ready"
        Actions = @([pscustomobject]@{
            Execute = [string]$Config.task_action.execute
            Arguments = [string]$Config.task_action.arguments
        })
    }
    $GenericIdentity = Get-GenericAutomationTaskIdentity -Task $GenericTask
    Assert-True $GenericIdentity.IsGeneric "generic task is detected from action/config/repository identity"
    $CoexistenceInventory = Get-AutomationTaskInventory -TaskName "SKTLM-Unrelated-New-Task" -Tasks @($HistoricalTask, $GenericTask)
    Assert-Equal 0 $CoexistenceInventory.ExactTaskCount "unrelated task name remains installable"
    Assert-Equal 1 $CoexistenceInventory.GenericTasks.Count "READY generic peer is classified without being treated as running"

    $TaskTrigger = [pscustomobject]@{
        StartBoundary = [string]$Config.registered_start
        Repetition = [pscustomobject]@{
            Interval = "PT5H1M"
            Duration = "P3650D"
        }
    }
    $ScheduledTaskFixture = [pscustomobject]@{
        TaskName = [string]$Config.task_name
        State = "Disabled"
        Actions = $GenericTask.Actions
        Triggers = @($TaskTrigger)
    }
    $TriggerBefore = $ScheduledTaskFixture.Triggers | ConvertTo-Json -Depth 8 -Compress
    $TaskIdentity = Test-ScheduledTaskIdentity -Task $ScheduledTaskFixture -Config $Config
    Assert-True $TaskIdentity.Valid "exact Scheduled Task action and fixed trigger match config"
    Assert-Equal $TriggerBefore ($ScheduledTaskFixture.Triggers | ConvertTo-Json -Depth 8 -Compress) "identity and recovery planning preserve trigger"
    $WrongActionTask = [pscustomobject]@{
        TaskName = [string]$Config.task_name
        Actions = @([pscustomobject]@{ Execute = "powershell.exe"; Arguments = "-File wrong.ps1" })
        Triggers = @($TaskTrigger)
    }
    Assert-True (-not (Test-ScheduledTaskIdentity -Task $WrongActionTask -Config $Config).Valid) "task action mismatch rejects recovery"

    $PromptIntegrity = Test-FrozenPromptIntegrity -Config $Config
    Assert-True $PromptIntegrity.Valid "matching frozen prompt hashes permit recovery gate"
    $BadHashConfig = $Config | ConvertTo-Json -Depth 16 | ConvertFrom-Json
    $BadHashConfig.resume_prompt_sha256 = ("0" * 64)
    Assert-True (-not (Test-FrozenPromptIntegrity -Config $BadHashConfig).Valid) "prompt hash mismatch rejects recovery"

    $RepoGatePass = Test-AutomationRepoSnapshot -Config $Config -CurrentBranch "automation-test" -Dirty "" -Head $Config.base_head -BaseIsAncestor $true -RemoteHead $Config.base_head
    Assert-True $RepoGatePass.Valid "clean branch compatible equal-head recovery gate passes"
    Assert-True (-not (Test-AutomationRepoSnapshot -Config $Config -CurrentBranch "wrong" -Dirty "" -Head $Config.base_head -BaseIsAncestor $true -RemoteHead $Config.base_head).Valid) "wrong branch rejects recovery"
    Assert-True (-not (Test-AutomationRepoSnapshot -Config $Config -CurrentBranch "automation-test" -Dirty "changed" -Head $Config.base_head -BaseIsAncestor $true -RemoteHead $Config.base_head).Valid) "dirty tree rejects recovery"
    Assert-True (-not (Test-AutomationRepoSnapshot -Config $Config -CurrentBranch "automation-test" -Dirty "" -Head "new-head" -BaseIsAncestor $false -RemoteHead "new-head").Valid) "incompatible head rejects recovery"
    Assert-True (-not (Test-AutomationRepoSnapshot -Config $Config -CurrentBranch "automation-test" -Dirty "" -Head "local-head" -BaseIsAncestor $true -RemoteHead "remote-head").Valid) "remote divergence rejects recovery"

    $RecoveryJsonLog = Join-Path $FixtureRoot "prethread.jsonl"
    $RecoveryStderrLog = Join-Path $FixtureRoot "prethread.stderr.txt"
    $RecoveryLastMessage = Join-Path $FixtureRoot "prethread.last.txt"
    Write-Utf8NoBom -Path $RecoveryJsonLog -Text ""
    Write-Utf8NoBom -Path $RecoveryStderrLog -Text ""
    $RecoveryState = [pscustomobject]@{
        phase = "LAUNCHER_ERROR"
        thread_id = $null
        last_error = "launcher argument conflict"
        last_exit_code = $null
        last_json_log = $RecoveryJsonLog
        last_stderr_log = $RecoveryStderrLog
        last_message_file = $RecoveryLastMessage
    }
    $RecoveryEligibility = Test-PreThreadRecoveryEligibility -State $RecoveryState
    Assert-True $RecoveryEligibility.Eligible "proven no-thread LAUNCHER_ERROR is recoverable"
    Assert-True ([string]::IsNullOrWhiteSpace([string]$RecoveryState.thread_id)) "legal recovery path keeps thread_id empty"
    $UnsafePhaseState = $RecoveryState | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    $UnsafePhaseState.phase = "WAITING_EXTERNAL"
    Assert-True (-not (Test-PreThreadRecoveryEligibility -State $UnsafePhaseState).Eligible) "non-recoverable phase is rejected"
    $UnsafeThreadState = $RecoveryState | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    $UnsafeThreadState.thread_id = $ExactThreadId
    Assert-True (-not (Test-PreThreadRecoveryEligibility -State $UnsafeThreadState).Eligible) "existing thread is rejected"
    Write-Utf8NoBom -Path $RecoveryJsonLog -Text ('{"type":"thread.started","thread_id":"' + $ExactThreadId + '"}' + "`r`n")
    Assert-True (-not (Test-PreThreadRecoveryEligibility -State $RecoveryState).Eligible) "observed thread.started event is rejected"
}
finally {
    if ($null -ne $MutexHolder) {
        try {
            if ($null -ne $MutexAsync) { [void]$MutexHolder.EndInvoke($MutexAsync) }
        }
        catch {}
        $MutexHolder.Dispose()
    }
    if (Test-Path -LiteralPath $FixtureRoot -PathType Container) {
        $ResolvedFixture = [System.IO.Path]::GetFullPath($FixtureRoot)
        if (-not $ResolvedFixture.StartsWith($SystemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing unsafe fixture cleanup path: $ResolvedFixture"
        }
        Remove-Item -LiteralPath $ResolvedFixture -Recurse -Force
    }
}

$Elapsed = ((Get-Date) - $Started).TotalSeconds
Write-Host "FOCUSED_VALIDATION=PASS"
Write-Host "TESTS=12_FOCUSED_CONTRACT_GROUPS"
Write-Host ("VALIDATION_SECONDS={0:N3}" -f $Elapsed)
Write-Host "ACTUAL_SCHEDULED_TASK_CREATED=NO"
Write-Host "CODEX_AUTOMATION_STARTED=NO"

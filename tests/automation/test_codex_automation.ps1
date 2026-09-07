[CmdletBinding()]
param(
    [string]$FrameworkRoot = (Join-Path (Join-Path $PSScriptRoot "..\..") ".codex\automation")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Started = Get-Date

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
$ResumeInvocation = New-CodexInvocation -Repo "C:\repo" -LastMessagePath "C:\logs\last.txt" -InitialPromptPath "C:\runtime\initial.txt" -ResumePromptPath "C:\runtime\resume.txt" -ThreadId $ExactThreadId
Assert-Equal "RESUME_EXACT" $ResumeInvocation.Mode "resume mode"
Assert-Equal "-C" $ResumeInvocation.ArgumentList[1] "Codex receives explicit repository option"
Assert-Equal "C:\repo" $ResumeInvocation.ArgumentList[2] "Codex receives exact repository path"
Assert-Equal "resume" $ResumeInvocation.ArgumentList[-3] "resume subcommand"
Assert-Equal $ExactThreadId $ResumeInvocation.ArgumentList[-2] "exact thread-id resume"
Assert-True ($ResumeInvocation.ArgumentList -notcontains "--last") "resume --last forbidden"

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

$FixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) "sktlm_automation_test_$([guid]::NewGuid().ToString('N'))"
$FixtureRoot = [System.IO.Path]::GetFullPath($FixtureRoot)
$SystemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if (-not $FixtureRoot.StartsWith($SystemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe fixture path: $FixtureRoot"
}

try {
    $BareRepo = Join-Path $FixtureRoot "origin.git"
    $FixtureRepo = Join-Path $FixtureRoot "repo"
    $RuntimeRoot = Join-Path $FixtureRoot "runtime"
    New-Item -ItemType Directory -Path $FixtureRoot | Out-Null
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
}
finally {
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
Write-Host "TESTS=7_CONTRACT_GROUPS"
Write-Host ("VALIDATION_SECONDS={0:N3}" -f $Elapsed)
Write-Host "ACTUAL_SCHEDULED_TASK_CREATED=NO"
Write-Host "CODEX_AUTOMATION_STARTED=NO"

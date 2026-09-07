[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$AutomationId,
    [Parameter(Mandatory = $true)][ValidateSet("Status", "Wake", "ResumeExternal")][string]$Action,
    [string]$Repo,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$HelperPath = Join-Path $PSScriptRoot "helper.ps1"
if (-not (Test-Path -LiteralPath $HelperPath -PathType Leaf)) {
    throw "Framework helper not found: $HelperPath"
}
. $HelperPath

Assert-AutomationId -AutomationId $AutomationId
if ($StartNow -and $Action -ne "ResumeExternal") {
    throw "-StartNow is valid only with -Action ResumeExternal. Wake already means one immediate extra invocation."
}
if ([string]::IsNullOrWhiteSpace($Repo)) {
    $Repo = Join-Path $PSScriptRoot "..\.."
}
$Repo = [System.IO.Path]::GetFullPath($Repo)
$AutomationRoot = Join-Path (Join-Path $Repo "artifacts\codex_automation") $AutomationId
$ConfigPath = Join-Path $AutomationRoot "config.json"
$Config = Read-AutomationJson -Path $ConfigPath
Assert-AutomationConfig -Config $Config
if ([string]$Config.automation_id -cne $AutomationId) {
    throw "Requested AutomationId does not match config.json."
}
$State = Read-AutomationJson -Path ([string]$Config.state_path)
Assert-AutomationState -State $State -Config $Config

try {
    $ScheduledTask = Get-ScheduledTask -TaskName ([string]$Config.task_name) -ErrorAction Stop
}
catch {
    throw "Cannot read Scheduled Task '$($Config.task_name)'. Verify that it exists and use an elevated Windows PowerShell shell if required: $($_.Exception.Message)"
}

$Plan = Get-AutomationControlPlan `
    -Action $Action `
    -Phase ([string]$State.phase) `
    -ThreadId ([string]$State.thread_id) `
    -StartNow:$StartNow

if ($Action -eq "Status") {
    try {
        $TaskInfo = Get-ScheduledTaskInfo -TaskName ([string]$Config.task_name) -ErrorAction Stop
    }
    catch {
        throw "Cannot read Scheduled Task status: $($_.Exception.Message)"
    }
    $CurrentBranch = $null
    $CurrentHead = $null
    if (Test-Path -LiteralPath ([string]$Config.repo) -PathType Container) {
        $CurrentBranch = ((@(& git.exe -C ([string]$Config.repo) branch --show-current 2>$null)) -join "`n").Trim()
        $CurrentHead = ((@(& git.exe -C ([string]$Config.repo) rev-parse HEAD 2>$null)) -join "`n").Trim()
    }
    $LastMessageTail = $null
    if (-not [string]::IsNullOrWhiteSpace([string]$State.last_message_file) -and
        (Test-Path -LiteralPath ([string]$State.last_message_file) -PathType Leaf)) {
        $LastMessageTail = (@(Get-Content -LiteralPath ([string]$State.last_message_file) -Tail 12) -join "`n")
    }
    [pscustomobject]@{
        TaskName = [string]$Config.task_name
        ScheduledTaskState = [string]$ScheduledTask.State
        AutomationPhase = [string]$State.phase
        ThreadId = [string]$State.thread_id
        ExpectedBranch = [string]$Config.expected_branch
        CurrentBranch = $CurrentBranch
        BaseHead = [string]$Config.base_head
        CurrentHead = $CurrentHead
        LastObservedHead = [string]$State.last_observed_head
        LastWake = $State.last_wake
        LastExitCode = $State.last_exit_code
        LastJsonLog = $State.last_json_log
        LastStderrLog = $State.last_stderr_log
        LastMessageFile = $State.last_message_file
        NextScheduledWake = $TaskInfo.NextRunTime
        ScheduleAnchor = [string]$Config.schedule_anchor
        IntervalMinutes = [int]$Config.interval_minutes
        LastError = $State.last_error
        LastMessageTail = $LastMessageTail
    } | Format-List
    exit 0
}

if ($Action -eq "Wake") {
    Start-ScheduledTask -TaskName ([string]$Config.task_name) -ErrorAction Stop
    Write-Host "MANUAL_WAKE=REQUESTED"
    Write-Host "TRIGGER_MODIFIED=NO"
    Write-Host "AUTOMATION_PHASE=$($State.phase)"
    exit 0
}

$PreviousPhase = [string]$State.phase
$State.phase = [string]$Plan.NewPhase
$State.external_resume_at = (Get-Date).ToString("o")
$State.last_error = $null
Write-AutomationJsonAtomic -Path ([string]$Config.state_path) -Value $State
try {
    Enable-ScheduledTask -TaskName ([string]$Config.task_name) -ErrorAction Stop | Out-Null
}
catch {
    $State.phase = $PreviousPhase
    $State.last_error = "ResumeExternal could not enable Scheduled Task: $($_.Exception.Message)"
    Write-AutomationJsonAtomic -Path ([string]$Config.state_path) -Value $State
    throw
}
if ($Plan.StartTask) {
    Start-ScheduledTask -TaskName ([string]$Config.task_name) -ErrorAction Stop
}
Write-Host "RESUME_EXTERNAL=PASS"
Write-Host "THREAD_ID=$($State.thread_id)"
Write-Host "AUTOMATION_PHASE=$($State.phase)"
Write-Host "TRIGGER_MODIFIED=NO"
Write-Host "STARTED_NOW=$([bool]$Plan.StartTask)"

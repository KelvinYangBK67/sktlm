[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$AutomationId,
    [Parameter(Mandatory = $true)][ValidateSet("Status", "Wake", "ResumeExternal", "RecoverPreThread")][string]$Action,
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
if ($StartNow -and @("ResumeExternal", "RecoverPreThread") -notcontains $Action) {
    throw "-StartNow is valid only with -Action ResumeExternal or RecoverPreThread. Wake already means one immediate extra invocation."
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

if ($Action -eq "RecoverPreThread") {
    if (-not [bool]$Config.registration_performed) {
        throw "RecoverPreThread requires config.json to record a completed Scheduled Task registration."
    }
    if ([string]$ScheduledTask.State -cne "Disabled") {
        throw "RecoverPreThread requires the fail-closed Scheduled Task to be Disabled; current state is $($ScheduledTask.State)."
    }
    $Eligibility = Test-PreThreadRecoveryEligibility -State $State
    if (-not $Eligibility.Eligible) {
        throw "Unsafe RecoverPreThread request: $($Eligibility.Reason)"
    }
    $PromptIntegrity = Test-FrozenPromptIntegrity -Config $Config
    if (-not $PromptIntegrity.Valid) {
        throw "Unsafe RecoverPreThread request: $($PromptIntegrity.Reason)"
    }
    $TaskIdentity = Test-ScheduledTaskIdentity -Task $ScheduledTask -Config $Config
    if (-not $TaskIdentity.Valid) {
        throw "Unsafe RecoverPreThread request: $($TaskIdentity.Reason)"
    }
    $GenericIdentity = Get-GenericAutomationTaskIdentity -Task $ScheduledTask
    if (-not $GenericIdentity.IsGeneric -or
        -not [string]::Equals([string]$GenericIdentity.ConfigPath, $ConfigPath, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals([string]$GenericIdentity.Repo, [string]$Config.repo, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe RecoverPreThread request: Scheduled Task is not the exact generic action/config/repo identity. $($GenericIdentity.Reason)"
    }

    $GitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $GitCommand) { $GitCommand = Get-Command git -ErrorAction SilentlyContinue }
    if (-not $GitCommand) { throw "Git executable not found in PATH." }
    $GitPath = $GitCommand.Source
    function Invoke-RecoveryGit {
        param([Parameter(Mandatory = $true)][string[]]$Arguments)

        $output = @(& $GitPath -C ([string]$Config.repo) @Arguments 2>&1)
        if ($LASTEXITCODE -ne 0) {
            throw "Unsafe RecoverPreThread request: git $($Arguments -join ' ') failed: $($output -join ' ')"
        }
        return ($output -join "`n").Trim()
    }
    [void](Invoke-RecoveryGit -Arguments @("fetch", "--quiet", "origin"))
    $CurrentBranch = Invoke-RecoveryGit -Arguments @("branch", "--show-current")
    $Dirty = Invoke-RecoveryGit -Arguments @("status", "--porcelain")
    $Head = Invoke-RecoveryGit -Arguments @("rev-parse", "HEAD")
    & $GitPath -C ([string]$Config.repo) merge-base --is-ancestor ([string]$Config.base_head) $Head 2>&1 | Out-Null
    $BaseIsAncestor = ($LASTEXITCODE -eq 0)
    $RemoteHead = Invoke-RecoveryGit -Arguments @("rev-parse", [string]$Config.remote_ref)
    $RepoGate = Test-AutomationRepoSnapshot `
        -Config $Config `
        -CurrentBranch $CurrentBranch `
        -Dirty $Dirty `
        -Head $Head `
        -BaseIsAncestor $BaseIsAncestor `
        -RemoteHead $RemoteHead
    if (-not $RepoGate.Valid) {
        throw "Unsafe RecoverPreThread request: $($RepoGate.Reason)"
    }
}

$PreviousState = $State | ConvertTo-Json -Depth 16 | ConvertFrom-Json
$PreviousError = [string]$State.last_error
$State.phase = [string]$Plan.NewPhase
$ControlTime = (Get-Date).ToString("o")
if ($Action -eq "ResumeExternal") {
    $State.external_resume_at = $ControlTime
}
else {
    if ($State.PSObject.Properties.Name -notcontains "prethread_recovery_at") {
        $State | Add-Member -NotePropertyName prethread_recovery_at -NotePropertyValue $null
    }
    if ($State.PSObject.Properties.Name -notcontains "prethread_recovery_reason") {
        $State | Add-Member -NotePropertyName prethread_recovery_reason -NotePropertyValue $null
    }
    $State.prethread_recovery_at = $ControlTime
    $State.prethread_recovery_reason = $PreviousError
    $State.last_exit_code = $null
}
$State.last_error = $null
Write-AutomationJsonAtomic -Path ([string]$Config.state_path) -Value $State
try {
    Enable-ScheduledTask -TaskName ([string]$Config.task_name) -ErrorAction Stop | Out-Null
}
catch {
    $PreviousState.last_error = "$Action could not enable Scheduled Task: $($_.Exception.Message)"
    Write-AutomationJsonAtomic -Path ([string]$Config.state_path) -Value $PreviousState
    throw
}
if ($Plan.StartTask) {
    Start-ScheduledTask -TaskName ([string]$Config.task_name) -ErrorAction Stop
}
if ($Action -eq "RecoverPreThread") {
    $PostRecoveryTask = Get-ScheduledTask -TaskName ([string]$Config.task_name) -ErrorAction Stop
    $PostRecoveryIdentity = Test-ScheduledTaskIdentity -Task $PostRecoveryTask -Config $Config
    if (-not $PostRecoveryIdentity.Valid) {
        throw "Scheduled Task identity changed during RecoverPreThread: $($PostRecoveryIdentity.Reason)"
    }
    Write-Host "RECOVER_PRETHREAD=PASS"
    Write-Host "THREAD_ID=EMPTY"
}
else {
    Write-Host "RESUME_EXTERNAL=PASS"
    Write-Host "THREAD_ID=$($State.thread_id)"
}
Write-Host "AUTOMATION_PHASE=$($State.phase)"
Write-Host "TRIGGER_MODIFIED=NO"
Write-Host "STARTED_NOW=$([bool]$Plan.StartTask)"

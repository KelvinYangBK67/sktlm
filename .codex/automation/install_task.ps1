[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$TaskName,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$AutomationId,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$PromptPath,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Branch,
    [Parameter(Mandatory = $true)][datetime]$Start,
    [Parameter(Mandatory = $true)][ValidateRange(1, 525600)][int]$IntervalMinutes,
    [string]$Repo,
    [ValidateRange(1, 168)][int]$ExecutionTimeLimitHours = 4,
    [switch]$StartNow,
    [switch]$DryRun,
    [string]$RuntimeRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$HelperPath = Join-Path $PSScriptRoot "helper.ps1"
if (-not (Test-Path -LiteralPath $HelperPath -PathType Leaf)) {
    throw "Framework helper not found: $HelperPath"
}
. $HelperPath

Assert-AutomationId -AutomationId $AutomationId
if ($TaskName.Contains("\") -or $TaskName.Contains("/")) {
    throw "TaskName must not contain a task-folder separator."
}
if (-not $DryRun -and -not [string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    throw "-RuntimeRoot is available only with -DryRun; real task state always uses artifacts/codex_automation/<automation_id>."
}

if ([string]::IsNullOrWhiteSpace($Repo)) {
    $Repo = Join-Path $PSScriptRoot "..\.."
}
$Repo = [System.IO.Path]::GetFullPath($Repo)
$PromptPath = [System.IO.Path]::GetFullPath($PromptPath)
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) {
    throw "Repository not found: $Repo"
}
if (-not (Test-Path -LiteralPath $PromptPath -PathType Leaf)) {
    throw "PromptPath not found: $PromptPath"
}

$RunnerPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "run_task.ps1"))
if (-not (Test-Path -LiteralPath $RunnerPath -PathType Leaf)) {
    throw "Generic runner not found: $RunnerPath"
}

$GitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $GitCommand) { $GitCommand = Get-Command git -ErrorAction SilentlyContinue }
if (-not $GitCommand) { throw "Git executable not found in PATH." }
$GitPath = $GitCommand.Source

$CodexCommand = Get-Command codex.exe -ErrorAction SilentlyContinue
if (-not $CodexCommand) { $CodexCommand = Get-Command codex.cmd -ErrorAction SilentlyContinue }
if (-not $CodexCommand) { $CodexCommand = Get-Command codex -ErrorAction SilentlyContinue }
if (-not $CodexCommand) { throw "Codex CLI not found in PATH." }
$CodexPath = $CodexCommand.Source

function Invoke-InstallGit {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& $GitPath -C $Repo @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($output -join ' ')"
    }
    return ($output -join "`n").Trim()
}

[void](Invoke-InstallGit -Arguments @("fetch", "--quiet", "origin"))
$CurrentBranch = Invoke-InstallGit -Arguments @("branch", "--show-current")
if ($CurrentBranch -cne $Branch) {
    throw "Wrong branch. Expected '$Branch', got '$CurrentBranch'."
}
$Dirty = Invoke-InstallGit -Arguments @("status", "--porcelain")
if (-not [string]::IsNullOrWhiteSpace($Dirty)) {
    throw "Working tree is dirty. Reconcile it manually before installing automation."
}
$BaseHead = Invoke-InstallGit -Arguments @("rev-parse", "HEAD")
$RemoteRef = "origin/$Branch"
$RemoteHead = Invoke-InstallGit -Arguments @("rev-parse", $RemoteRef)
if ($BaseHead -cne $RemoteHead) {
    throw "Local HEAD and $RemoteRef differ. Reconcile manually before installing. local=$BaseHead remote=$RemoteHead"
}

if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    if ($DryRun) {
        $dryName = "sktlm_codex_automation_dryrun_$([guid]::NewGuid().ToString('N'))"
        $RuntimeRoot = Join-Path ([System.IO.Path]::GetTempPath()) $dryName
    }
    else {
        $RuntimeRoot = Join-Path $Repo "artifacts\codex_automation"
    }
}
$RuntimeRoot = [System.IO.Path]::GetFullPath($RuntimeRoot)
$AutomationRoot = Join-Path $RuntimeRoot $AutomationId
if (Test-Path -LiteralPath $AutomationRoot) {
    throw "Automation directory already exists: $AutomationRoot"
}

$ScheduledTaskCommands = @(
    "Get-ScheduledTask",
    "Get-ScheduledTaskInfo",
    "New-ScheduledTaskTrigger",
    "New-ScheduledTaskAction",
    "New-ScheduledTaskSettingsSet",
    "New-ScheduledTaskPrincipal",
    "Register-ScheduledTask",
    "Start-ScheduledTask",
    "Enable-ScheduledTask",
    "Disable-ScheduledTask"
)
foreach ($commandName in $ScheduledTaskCommands) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "Required Windows Scheduled Task command is unavailable: $commandName"
    }
}

$GenericPeerNames = @()
if (-not $DryRun) {
    try {
        $AllTasks = @(Get-ScheduledTask -ErrorAction Stop)
    }
    catch {
        throw "Cannot inspect Windows Scheduled Tasks. Use an elevated Windows PowerShell shell if required: $($_.Exception.Message)"
    }
    $Inventory = Get-AutomationTaskInventory -TaskName $TaskName -Tasks $AllTasks
    if ($Inventory.ExactTaskCount -gt 0) {
        throw "Scheduled Task already exists: $TaskName"
    }
    $GenericPeerNames = @($Inventory.GenericTasks | ForEach-Object { $_.TaskName })
}

$Schedule = New-AutomationScheduleDefinition -Anchor $Start -IntervalMinutes $IntervalMinutes -Now (Get-Date)

New-Item -ItemType Directory -Path $AutomationRoot | Out-Null
$LogsDir = Join-Path $AutomationRoot "logs"
New-Item -ItemType Directory -Path $LogsDir | Out-Null
$ConfigPath = Join-Path $AutomationRoot "config.json"
$StatePath = Join-Path $AutomationRoot "state.json"
$InitialPromptPath = Join-Path $AutomationRoot "initial_prompt.txt"
$ResumePromptPath = Join-Path $AutomationRoot "resume_prompt.txt"

$MasterText = [System.IO.File]::ReadAllText($PromptPath)
$AutomationFooter = @'


# AUTOMATION CONTROL CONTRACT

At the end of every response, output exactly one of the following as the final non-empty line:

AUTOMATION_STATUS=CONTINUE
AUTOMATION_STATUS=WAITING_EXTERNAL
AUTOMATION_STATUS=WAITING_DETACHED
AUTOMATION_STATUS=COMPLETE

Use CONTINUE only when authorized bounded work remains and the next work does not require a researcher-run external workload.
Use WAITING_EXTERNAL only when researcher action is required. Before the marker, provide the exact command, code/config/input/output provenance, and pass/fail criteria.
Use WAITING_DETACHED only after successfully starting a detached workload that leaves tracked source unchanged and writes under artifacts/runtime output. Before that marker, provide exactly one AUTOMATION_DETACHED_MANIFEST=<absolute-json-path> line following the current runtime contract.
Use COMPLETE only when this bounded task is complete and every intended commit is pushed.

Never put text after the marker. Never edit automation config.json, state.json, thread_id, prompt snapshots, logs, or Scheduled Task triggers. Never use codex exec resume --last.
'@
$InitialText = $MasterText.TrimEnd() + $AutomationFooter
Write-Utf8NoBom -Path $InitialPromptPath -Text ($InitialText + "`r`n")

$ResumeText = @'
Continue the existing bounded task in this exact Codex thread.

Read the frozen initial task instructions and the current repository state. Continue only the next authorized unfinished action. Do not redo completed work or broaden scope.

Do not edit automation config.json, state.json, prompt snapshots, logs, thread_id, or Scheduled Task triggers. If researcher action is required, report exact provenance and stop with WAITING_EXTERNAL. A successfully started detached workload may use WAITING_DETACHED only with the required immutable machine-readable manifest and artifacts/runtime-only outputs.

At the end of the response, output exactly one status marker as the final non-empty line:
AUTOMATION_STATUS=CONTINUE
AUTOMATION_STATUS=WAITING_EXTERNAL
AUTOMATION_STATUS=WAITING_DETACHED
AUTOMATION_STATUS=COMPLETE

Never put text after the marker.
'@
Write-Utf8NoBom -Path $ResumePromptPath -Text ($ResumeText.TrimStart() + "`r`n")

$InitialPromptSha256 = (Get-FileHash -LiteralPath $InitialPromptPath -Algorithm SHA256).Hash.ToLowerInvariant()
$ResumePromptSha256 = (Get-FileHash -LiteralPath $ResumePromptPath -Algorithm SHA256).Hash.ToLowerInvariant()
$ActionDefinition = New-RunnerActionDefinition -RunnerPath $RunnerPath -ConfigPath $ConfigPath
$MutexName = "Local\SKTLM_CodexAutomation_$AutomationId"

$Config = [ordered]@{
    schema_version = "sktlm-codex-automation-config/v1"
    task_name = $TaskName
    automation_id = $AutomationId
    repo = $Repo
    expected_branch = $Branch
    base_head = $BaseHead
    remote_ref = $RemoteRef
    automation_root = $AutomationRoot
    state_path = $StatePath
    initial_prompt_path = $InitialPromptPath
    initial_prompt_sha256 = $InitialPromptSha256
    resume_prompt_path = $ResumePromptPath
    resume_prompt_sha256 = $ResumePromptSha256
    logs_dir = $LogsDir
    runner_path = $RunnerPath
    codex_path = $CodexPath
    mutex_name = $MutexName
    schedule_anchor = $Start.ToString("o")
    registered_start = $Schedule.RegisteredStart.ToString("o")
    interval_minutes = $IntervalMinutes
    repetition_duration_days = 3650
    execution_time_limit_hours = $ExecutionTimeLimitHours
    task_action = [ordered]@{
        execute = $ActionDefinition.Execute
        arguments = $ActionDefinition.Arguments
    }
    registration_performed = $false
}
$State = [ordered]@{
    schema_version = "sktlm-codex-automation/v1"
    task_name = $TaskName
    automation_id = $AutomationId
    repo = $Repo
    expected_branch = $Branch
    base_head = $BaseHead
    thread_id = $null
    phase = "READY"
    last_wake = $null
    last_exit_code = $null
    last_json_log = $null
    last_stderr_log = $null
    last_message_file = $null
    last_observed_head = $BaseHead
    last_error = $null
    external_resume_at = $null
    prethread_recovery_at = $null
    prethread_recovery_reason = $null
    interrupted_recovery_at = $null
    interrupted_recovery_reason = $null
    workspace_checkpoint = $null
    detached_job = $null
}
Write-AutomationJsonAtomic -Path $ConfigPath -Value $Config
Write-AutomationJsonAtomic -Path $StatePath -Value $State

if ($DryRun) {
    Write-Host "DRY_RUN=PASS"
    Write-Host "DRY_RUN_ROOT=$AutomationRoot"
    Write-Host "TASK_NAME=$TaskName"
    Write-Host "ANCHOR=$($Start.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host "REGISTERED_START=$($Schedule.RegisteredStart.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host "INTERVAL_MINUTES=$IntervalMinutes"
    Write-Host "ACTION_EXECUTE=$($ActionDefinition.Execute)"
    Write-Host "ACTION_ARGUMENTS=$($ActionDefinition.Arguments)"
    Write-Host "SCHEDULED_TASK_REGISTERED=NO"
    Write-Host "CODEX_STARTED=NO"
    exit 0
}

try {
    $Trigger = New-ScheduledTaskTrigger `
        -Once `
        -At $Schedule.RegisteredStart `
        -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
    $Action = New-ScheduledTaskAction `
        -Execute $ActionDefinition.Execute `
        -Argument $ActionDefinition.Arguments
    $Settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours $ExecutionTimeLimitHours)
    $CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $CurrentUser `
        -LogonType Interactive `
        -RunLevel Highest
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Bounded Codex automation managed by the repository generic framework." | Out-Null
    if ($StartNow) {
        Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    }
    $Config.registration_performed = $true
    Write-AutomationJsonAtomic -Path $ConfigPath -Value $Config
}
catch {
    $State.phase = "LAUNCHER_ERROR"
    $State.last_error = "Scheduled Task installation failed: $($_.Exception.Message)"
    Write-AutomationJsonAtomic -Path $StatePath -Value $State
    try {
        Disable-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null
    }
    catch {}
    throw
}

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
Write-Host "INSTALL=PASS"
Write-Host "TASK_NAME=$TaskName"
Write-Host "TASK_STATE=$($Task.State)"
Write-Host "AUTOMATION_ROOT=$AutomationRoot"
Write-Host "ANCHOR=$($Start.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "REGISTERED_START=$($Schedule.RegisteredStart.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "INTERVAL_MINUTES=$IntervalMinutes"
Write-Host "NEXT_RUN_TIME=$($TaskInfo.NextRunTime.ToString('o'))"
Write-Host "STARTED_NOW=$([bool]$StartNow)"
Write-Host "GENERIC_AUTOMATION_PEERS=$($GenericPeerNames -join ',')"

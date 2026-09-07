[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$ConfigPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$HelperPath = Join-Path $PSScriptRoot "helper.ps1"
if (-not (Test-Path -LiteralPath $HelperPath -PathType Leaf)) {
    throw "Framework helper not found: $HelperPath"
}
. $HelperPath

$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$Config = Read-AutomationJson -Path $ConfigPath
Assert-AutomationConfig -Config $Config
if (-not [bool]$Config.registration_performed) {
    throw "config.json does not record a completed Scheduled Task registration."
}
$ConfigDirectory = [System.IO.Path]::GetDirectoryName($ConfigPath)
$ConfiguredRoot = [System.IO.Path]::GetFullPath([string]$Config.automation_root)
if (-not [string]::Equals($ConfigDirectory, $ConfiguredRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "config.json is not located in its declared automation_root."
}
$ConfiguredRunner = [System.IO.Path]::GetFullPath([string]$Config.runner_path)
$ActualRunner = [System.IO.Path]::GetFullPath($MyInvocation.MyCommand.Path)
if (-not [string]::Equals($ConfiguredRunner, $ActualRunner, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "config.json runner_path does not match this generic runner."
}

$TaskName = [string]$Config.task_name
$StatePath = [string]$Config.state_path
$Repo = [string]$Config.repo
$GitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $GitCommand) { $GitCommand = Get-Command git -ErrorAction SilentlyContinue }
if (-not $GitCommand) { throw "Git executable not found in PATH." }
$GitPath = $GitCommand.Source
$State = $null
$TaskLock = $null
$RepoLock = $null
$FailureRecorded = $false
$FinalExitCode = 0

function Disable-ConfiguredTask {
    try {
        Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        Write-Error "Failed to disable Scheduled Task '$TaskName': $($_.Exception.Message)" -ErrorAction Continue
        return $false
    }
}

function Save-RunnerState {
    Assert-AutomationState -State $State -Config $Config
    Write-AutomationJsonAtomic -Path $StatePath -Value $State
}

function Record-RunnerFailure {
    param(
        [Parameter(Mandatory = $true)][string]$Phase,
        [Parameter(Mandatory = $true)][string]$Message
    )

    $script:State.phase = $Phase
    $script:State.last_wake = (Get-Date).ToString("o")
    $script:State.last_error = $Message
    Save-RunnerState
    [void](Disable-ConfiguredTask)
    $script:FailureRecorded = $true
    throw $Message
}

function Invoke-RunnerGit {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& $GitPath -C $Repo @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message "git $($Arguments -join ' ') failed: $($output -join ' ')"
    }
    return ($output -join "`n").Trim()
}

try {
    $TaskLock = Enter-AutomationMutex -Name ([string]$Config.mutex_name)
    if (-not $TaskLock.Acquired) {
        Write-Host "AUTOMATION_ALREADY_RUNNING=YES"
        exit 0
    }
    $RepoMutexName = Get-AutomationRepoMutexName -Repo $Repo
    $RepoLock = Enter-AutomationMutex -Name $RepoMutexName
    if (-not $RepoLock.Acquired) {
        Write-Host "AUTOMATION_REPO_BUSY=YES"
        Write-Host "REPO_MUTEX=$RepoMutexName"
        exit 0
    }

    $State = Read-AutomationJson -Path $StatePath
    Assert-AutomationState -State $State -Config $Config

    if (@("WAITING_EXTERNAL", "COMPLETE") -contains [string]$State.phase) {
        if (-not (Disable-ConfiguredTask)) {
            $FailureRecorded = $true
            throw "Terminal automation phase is recorded, but the Scheduled Task could not be disabled."
        }
        Write-Host "AUTOMATION_PHASE=$($State.phase)"
        exit 0
    }
    if ([string]$State.phase -eq "RUNNING") {
        Record-RunnerFailure -Phase "LAST_WAKE_FAILED" -Message "Previous wake left state phase RUNNING; manual inspection is required."
    }
    if (@("READY", "ACTIVE") -notcontains [string]$State.phase) {
        [void](Disable-ConfiguredTask)
        $FailureRecorded = $true
        throw "Automation is in fail-closed phase $($State.phase)."
    }

    $PromptChecks = @(
        [pscustomobject]@{ Path = [string]$Config.initial_prompt_path; Hash = [string]$Config.initial_prompt_sha256 },
        [pscustomobject]@{ Path = [string]$Config.resume_prompt_path; Hash = [string]$Config.resume_prompt_sha256 }
    )
    foreach ($promptCheck in $PromptChecks) {
        if (-not (Test-Path -LiteralPath $promptCheck.Path -PathType Leaf)) {
            Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message "Frozen prompt not found: $($promptCheck.Path)"
        }
        $observedHash = (Get-FileHash -LiteralPath $promptCheck.Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($observedHash -cne $promptCheck.Hash) {
            Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message "Frozen prompt hash mismatch: $($promptCheck.Path)"
        }
    }

    [void](Invoke-RunnerGit -Arguments @("fetch", "--quiet", "origin"))
    $CurrentBranch = Invoke-RunnerGit -Arguments @("branch", "--show-current")
    if ($CurrentBranch -cne [string]$Config.expected_branch) {
        Record-RunnerFailure -Phase "BLOCKED_WRONG_BRANCH" -Message "Expected branch '$($Config.expected_branch)', got '$CurrentBranch'."
    }
    $Dirty = Invoke-RunnerGit -Arguments @("status", "--porcelain")
    if (-not [string]::IsNullOrWhiteSpace($Dirty)) {
        Record-RunnerFailure -Phase "BLOCKED_DIRTY_TREE" -Message "Working tree is dirty. The runner will not ask Codex to repair it."
    }
    $Head = Invoke-RunnerGit -Arguments @("rev-parse", "HEAD")
    & $GitPath -C $Repo merge-base --is-ancestor ([string]$Config.base_head) $Head 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Record-RunnerFailure -Phase "BLOCKED_INCOMPATIBLE_HEAD" -Message "Current HEAD $Head is not descended from base HEAD $($Config.base_head)."
    }
    $RemoteHead = Invoke-RunnerGit -Arguments @("rev-parse", [string]$Config.remote_ref)
    if ($Head -cne $RemoteHead) {
        Record-RunnerFailure -Phase "BLOCKED_REMOTE_DIVERGENCE" -Message "Local HEAD and $($Config.remote_ref) differ. local=$Head remote=$RemoteHead"
    }
    $State.last_observed_head = $Head

    $LogsDir = [string]$Config.logs_dir
    if (-not (Test-Path -LiteralPath $LogsDir -PathType Container)) {
        Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message "Logs directory not found: $LogsDir"
    }
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
    $LogStem = "wake_${Stamp}_$PID"
    $JsonLog = Join-Path $LogsDir "$LogStem.jsonl"
    $StderrLog = Join-Path $LogsDir "$LogStem.stderr.txt"
    $LastMessage = Join-Path $LogsDir "$LogStem.last.txt"

    $State.phase = "RUNNING"
    $State.last_wake = (Get-Date).ToString("o")
    $State.last_exit_code = $null
    $State.last_json_log = $JsonLog
    $State.last_stderr_log = $StderrLog
    $State.last_message_file = $LastMessage
    $State.last_error = $null
    Save-RunnerState

    $StoredThreadId = [string]$State.thread_id
    $Invocation = New-CodexInvocation `
        -Repo $Repo `
        -LastMessagePath $LastMessage `
        -InitialPromptPath ([string]$Config.initial_prompt_path) `
        -ResumePromptPath ([string]$Config.resume_prompt_path) `
        -ThreadId $StoredThreadId
    $PromptText = [System.IO.File]::ReadAllText([string]$Invocation.PromptPath)
    $CodexArguments = [string[]]$Invocation.ArgumentList
    $PromptText | & ([string]$Config.codex_path) @CodexArguments 1> $JsonLog 2> $StderrLog
    $CodexExitCode = $LASTEXITCODE
    $State.last_exit_code = $CodexExitCode

    if (-not (Test-Path -LiteralPath $JsonLog -PathType Leaf)) {
        Record-RunnerFailure -Phase "FAILED_NO_THREAD_ID" -Message "Codex produced no JSONL log: $JsonLog"
    }
    try {
        $JsonLines = @([System.IO.File]::ReadLines($JsonLog))
        $ObservedThreadIds = @(Get-ThreadIdsFromJsonLines -Lines $JsonLines)
    }
    catch {
        Record-RunnerFailure -Phase "FAILED_NO_THREAD_ID" -Message $_.Exception.Message
    }
    if ($ObservedThreadIds.Count -ne 1) {
        Record-RunnerFailure -Phase "FAILED_NO_THREAD_ID" -Message "Expected exactly one unique thread.started thread_id; found $($ObservedThreadIds.Count)."
    }
    $ObservedThreadId = [string]$ObservedThreadIds[0]
    if ([string]::IsNullOrWhiteSpace($StoredThreadId)) {
        $State.thread_id = $ObservedThreadId
        Save-RunnerState
    }
    elseif ($ObservedThreadId -cne $StoredThreadId) {
        Record-RunnerFailure -Phase "THREAD_MISMATCH" -Message "THREAD_MISMATCH: stored=$StoredThreadId observed=$ObservedThreadId"
    }

    if ($CodexExitCode -ne 0) {
        Record-RunnerFailure -Phase "LAST_WAKE_FAILED" -Message "Codex wake exited with code $CodexExitCode. See $StderrLog"
    }
    if (-not (Test-Path -LiteralPath $LastMessage -PathType Leaf)) {
        Record-RunnerFailure -Phase "ACTIVE_NO_MARKER" -Message "Codex produced no last-message file: $LastMessage"
    }
    $LastText = [System.IO.File]::ReadAllText($LastMessage)
    $Marker = Resolve-AutomationStatusMarker -Text $LastText
    if (-not $Marker.Valid) {
        Record-RunnerFailure -Phase "ACTIVE_NO_MARKER" -Message ([string]$Marker.Error)
    }

    $State.phase = [string]$Marker.Phase
    $State.last_error = $null
    Save-RunnerState
    if ($Marker.DisableTask) {
        if (-not (Disable-ConfiguredTask)) {
            $FailureRecorded = $true
            throw "Automation reached $($Marker.Phase), but the Scheduled Task could not be disabled."
        }
    }
    Write-Host "AUTOMATION_PHASE=$($State.phase)"
    Write-Host "THREAD_ID=$($State.thread_id)"
}
catch {
    $FinalExitCode = 1
    if ($null -ne $State -and -not $FailureRecorded) {
        try {
            $State.phase = "LAUNCHER_ERROR"
            $State.last_wake = (Get-Date).ToString("o")
            $State.last_error = $_.Exception.Message
            Save-RunnerState
            [void](Disable-ConfiguredTask)
        }
        catch {
            Write-Error "Unable to record launcher failure: $($_.Exception.Message)" -ErrorAction Continue
        }
    }
    Write-Error $_ -ErrorAction Continue
}
finally {
    if ($null -ne $RepoLock) { Exit-AutomationMutex -Lock $RepoLock }
    if ($null -ne $TaskLock) { Exit-AutomationMutex -Lock $TaskLock }
}

exit $FinalExitCode

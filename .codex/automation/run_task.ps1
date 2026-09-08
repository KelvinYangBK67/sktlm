[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$ConfigPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$HelperPath = Join-Path $PSScriptRoot "helper.ps1"
$NativeWrapperPath = Join-Path $PSScriptRoot "invoke_codex.ps1"
foreach ($requiredPath in @($HelperPath, $NativeWrapperPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Framework file not found: $requiredPath"
    }
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
$PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
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

function Record-RecoverableInterruption {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [Parameter(Mandatory = $true)][object]$Snapshot
    )

    if ([string]::IsNullOrWhiteSpace([string]$script:State.thread_id)) {
        throw "Cannot record a recoverable interruption without an exact thread_id."
    }
    Set-AutomationObjectProperty -Object $script:State -Name "workspace_checkpoint" -Value (New-AutomationWorkspaceCheckpoint -Snapshot $Snapshot)
    $script:State.phase = "INTERRUPTED_RECOVERABLE"
    $script:State.last_observed_head = [string]$Snapshot.head
    $script:State.last_wake = (Get-Date).ToString("o")
    $script:State.last_error = $Message
    Save-RunnerState
    $script:FailureRecorded = $true
    throw $Message
}

function Invoke-RunnerGit {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $GitPath -C $Repo @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message "git $($Arguments -join ' ') failed: $($output -join ' ')"
    }
    return ($output -join "`n").Trim()
}

function Persist-ObservedThreadIds {
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Ids)

    if ($Ids.Count -gt 1) {
        throw "Expected at most one unique thread.started thread_id; found $($Ids.Count)."
    }
    if ($Ids.Count -eq 0) { return }
    $observed = [string]$Ids[0]
    if ([string]::IsNullOrWhiteSpace([string]$script:State.thread_id)) {
        $script:State.thread_id = $observed
        Save-RunnerState
    }
    elseif ([string]$script:State.thread_id -cne $observed) {
        throw "THREAD_MISMATCH: stored=$($script:State.thread_id) observed=$observed"
    }
}

function Get-StderrSummary {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).Length -eq 0) {
        return "stderr was empty"
    }
    return ((@(Get-Content -LiteralPath $Path -Tail 12) -join " ").Trim())
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
        Record-RunnerFailure -Phase "LAST_WAKE_FAILED" -Message "Previous wake left state phase RUNNING; explicit recovery is required."
    }
    if (@("READY", "ACTIVE", "INTERRUPTED_RECOVERABLE", "WAITING_DETACHED") -notcontains [string]$State.phase) {
        [void](Disable-ConfiguredTask)
        $FailureRecorded = $true
        throw "Automation is in fail-closed phase $($State.phase)."
    }

    $PromptIntegrity = Test-FrozenPromptIntegrity -Config $Config
    if (-not $PromptIntegrity.Valid) {
        Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message ([string]$PromptIntegrity.Reason)
    }

    [void](Invoke-RunnerGit -Arguments @("fetch", "--quiet", "origin"))
    $CurrentBranch = Invoke-RunnerGit -Arguments @("branch", "--show-current")
    if ($CurrentBranch -cne [string]$Config.expected_branch) {
        Record-RunnerFailure -Phase "BLOCKED_WRONG_BRANCH" -Message "Expected branch '$($Config.expected_branch)', got '$CurrentBranch'."
    }
    $Head = Invoke-RunnerGit -Arguments @("rev-parse", "HEAD")
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $GitPath -C $Repo merge-base --is-ancestor ([string]$Config.base_head) $Head 2>&1 | Out-Null
        $BaseIsAncestor = ($LASTEXITCODE -eq 0)
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if (-not $BaseIsAncestor) {
        Record-RunnerFailure -Phase "BLOCKED_INCOMPATIBLE_HEAD" -Message "Current HEAD $Head is not descended from base HEAD $($Config.base_head)."
    }
    $Snapshot = Get-AutomationWorkspaceSnapshot -Repo $Repo -GitPath $GitPath -RemoteRef ([string]$Config.remote_ref)
    $StoredThreadId = [string]$State.thread_id
    if ([string]::IsNullOrWhiteSpace($StoredThreadId)) {
        if ([string]$State.phase -cne "READY") {
            Record-RunnerFailure -Phase "FAILED_NO_THREAD_ID" -Message "Phase $($State.phase) has no stored thread_id."
        }
        if (-not [bool]$Snapshot.is_clean) {
            Record-RunnerFailure -Phase "BLOCKED_DIRTY_TREE" -Message "A NEW automation thread requires a clean working tree."
        }
        if ([string]$Snapshot.head -cne [string]$Snapshot.remote_head) {
            Record-RunnerFailure -Phase "BLOCKED_REMOTE_DIVERGENCE" -Message "A NEW automation thread requires local HEAD to equal $($Config.remote_ref). local=$($Snapshot.head) remote=$($Snapshot.remote_head)"
        }
    }
    else {
        if ($State.PSObject.Properties.Name -notcontains "workspace_checkpoint" -or $null -eq $State.workspace_checkpoint) {
            Record-RunnerFailure -Phase "BLOCKED_DIRTY_TREE" -Message "Exact continuation requires a recorded workspace checkpoint."
        }
        $Continuation = Test-AutomationContinuationCheckpoint -Snapshot $Snapshot -Checkpoint $State.workspace_checkpoint
        if (-not $Continuation.Valid) {
            if ([string]$Snapshot.remote_head -cne [string]$State.workspace_checkpoint.remote_head) {
                $phase = "BLOCKED_REMOTE_DIVERGENCE"
            }
            elseif ([string]$Snapshot.head -cne [string]$State.workspace_checkpoint.head) {
                $phase = "BLOCKED_INCOMPATIBLE_HEAD"
            }
            else {
                $phase = "BLOCKED_DIRTY_TREE"
            }
            Record-RunnerFailure -Phase $phase -Message ([string]$Continuation.Reason)
        }
    }
    $State.last_observed_head = [string]$Snapshot.head

    $DetachedContext = $null
    if ([string]$State.phase -eq "WAITING_DETACHED") {
        if ($State.PSObject.Properties.Name -notcontains "detached_job" -or $null -eq $State.detached_job) {
            Record-RunnerFailure -Phase "LAST_WAKE_FAILED" -Message "WAITING_DETACHED has no stored job identity."
        }
        $Observation = Get-AutomationDetachedJobObservation -Job $State.detached_job
        $State.detached_job.status = [string]$Observation.State
        $State.detached_job.observed_at = (Get-Date).ToString("o")
        $State.detached_job.exit_code = $Observation.ExitCode
        $State.detached_job.detail = [string]$Observation.Detail
        $State.last_wake = (Get-Date).ToString("o")
        Save-RunnerState
        if ([string]$Observation.State -eq "RUNNING") {
            Write-Host "AUTOMATION_PHASE=WAITING_DETACHED"
            Write-Host "DETACHED_JOB_ID=$($State.detached_job.job_id)"
            Write-Host "CODEX_INVOKED=NO"
            exit 0
        }
        $DetachedContext = "Detached job observation: state=$($Observation.State); exit_code=$($Observation.ExitCode); detail=$($Observation.Detail); manifest=$($State.detached_job.manifest_path)"
        $State.phase = "ACTIVE"
        Save-RunnerState
    }

    $LogsDir = [string]$Config.logs_dir
    if (-not (Test-Path -LiteralPath $LogsDir -PathType Container)) {
        Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message "Logs directory not found: $LogsDir"
    }
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
    $LogStem = "wake_${Stamp}_$PID"
    $JsonLog = Join-Path $LogsDir "$LogStem.jsonl"
    $StderrLog = Join-Path $LogsDir "$LogStem.stderr.txt"
    $LastMessage = Join-Path $LogsDir "$LogStem.last.txt"
    $WakePrompt = Join-Path $LogsDir "$LogStem.prompt.txt"
    $NativeSpecPath = Join-Path $LogsDir "$LogStem.native.json"
    $NativeResultPath = Join-Path $LogsDir "$LogStem.native-result.json"

    $State.phase = "RUNNING"
    $State.last_wake = (Get-Date).ToString("o")
    $State.last_exit_code = $null
    $State.last_json_log = $JsonLog
    $State.last_stderr_log = $StderrLog
    $State.last_message_file = $LastMessage
    $State.last_error = $null
    Save-RunnerState

    $Invocation = New-CodexInvocation `
        -Repo $Repo `
        -LastMessagePath $LastMessage `
        -InitialPromptPath ([string]$Config.initial_prompt_path) `
        -ResumePromptPath ([string]$Config.resume_prompt_path) `
        -ThreadId $StoredThreadId
    $PromptText = [System.IO.File]::ReadAllText([string]$Invocation.PromptPath)
    if (-not [string]::IsNullOrWhiteSpace($DetachedContext)) {
        $PromptText = $PromptText.TrimEnd() + "`r`n`r`n" + $DetachedContext + "`r`n"
    }
    $PromptText = Add-AutomationRuntimeContract -PromptText $PromptText
    Write-Utf8NoBom -Path $WakePrompt -Text $PromptText
    $NativeSpec = [ordered]@{
        file_path = [string]$Config.codex_path
        argument_list = [string[]]$Invocation.ArgumentList
        prompt_path = $WakePrompt
        stdout_path = $JsonLog
        stderr_path = $StderrLog
        result_path = $NativeResultPath
    }
    Write-AutomationJsonAtomic -Path $NativeSpecPath -Value $NativeSpec

    $wrapperArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -SpecPath "{1}"' -f $NativeWrapperPath, $NativeSpecPath
    try {
        $NativeProcess = Start-Process -FilePath $PowerShellPath -ArgumentList $wrapperArguments -WindowStyle Hidden -PassThru
    }
    catch {
        if (-not [string]::IsNullOrWhiteSpace([string]$State.thread_id)) {
            $StartFailureSnapshot = Get-AutomationWorkspaceSnapshot -Repo $Repo -GitPath $GitPath -RemoteRef ([string]$Config.remote_ref)
            Record-RecoverableInterruption -Snapshot $StartFailureSnapshot -Message "Native Codex wrapper could not start; exact thread will be retried: $($_.Exception.Message)"
        }
        throw
    }
    while (-not $NativeProcess.HasExited) {
        if ([string]::IsNullOrWhiteSpace([string]$State.thread_id) -and (Test-Path -LiteralPath $JsonLog -PathType Leaf)) {
            try {
                Persist-ObservedThreadIds -Ids @(Get-SalvageableThreadIdsFromJsonLog -Path $JsonLog)
            }
            catch {
                $ThreadObservationError = $_.Exception.Message
            }
        }
        Start-Sleep -Milliseconds 200
        $NativeProcess.Refresh()
    }
    $NativeProcess.WaitForExit()

    if (Test-Path -LiteralPath $JsonLog -PathType Leaf) {
        try {
            Persist-ObservedThreadIds -Ids @(Get-SalvageableThreadIdsFromJsonLog -Path $JsonLog)
        }
        catch {
            if ($_.Exception.Message -like "THREAD_MISMATCH:*") {
                Record-RunnerFailure -Phase "THREAD_MISMATCH" -Message $_.Exception.Message
            }
            Record-RunnerFailure -Phase "FAILED_NO_THREAD_ID" -Message $_.Exception.Message
        }
    }
    if (-not (Test-Path -LiteralPath $NativeResultPath -PathType Leaf)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$State.thread_id)) {
            $PostSnapshot = Get-AutomationWorkspaceSnapshot -Repo $Repo -GitPath $GitPath -RemoteRef ([string]$Config.remote_ref)
            Record-RecoverableInterruption -Snapshot $PostSnapshot -Message "Native Codex wrapper produced no result file; exact thread will be retried."
        }
        Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message "Native Codex wrapper produced no result file."
    }
    $NativeResult = Read-AutomationJson -Path $NativeResultPath
    Assert-ObjectProperties -Value $NativeResult -Label "native Codex result" -Names @("exit_code", "launcher_error", "completed_at")
    $CodexExitCode = $NativeResult.exit_code
    $State.last_exit_code = $CodexExitCode
    $PostSnapshot = Get-AutomationWorkspaceSnapshot -Repo $Repo -GitPath $GitPath -RemoteRef ([string]$Config.remote_ref)
    Set-AutomationObjectProperty -Object $State -Name "workspace_checkpoint" -Value (New-AutomationWorkspaceCheckpoint -Snapshot $PostSnapshot)
    $State.last_observed_head = [string]$PostSnapshot.head
    Save-RunnerState

    $Disposition = Resolve-CodexProcessDisposition `
        -HasThreadId (-not [string]::IsNullOrWhiteSpace([string]$State.thread_id)) `
        -ExitCode $CodexExitCode `
        -LauncherError ([string]$NativeResult.launcher_error)
    if ([string]$Disposition.Disposition -eq "SUCCESS") {
        try {
            Persist-ObservedThreadIds -Ids @(Get-ThreadIdsFromJsonLog -Path $JsonLog)
        }
        catch {
            if ($_.Exception.Message -like "THREAD_MISMATCH:*") {
                Record-RunnerFailure -Phase "THREAD_MISMATCH" -Message $_.Exception.Message
            }
            Record-RunnerFailure -Phase "FAILED_NO_THREAD_ID" -Message $_.Exception.Message
        }
    }
    if ([string]$Disposition.Disposition -ne "SUCCESS") {
        $failureText = "Codex interruption: exit_code=$CodexExitCode; launcher_error=$($NativeResult.launcher_error); $(Get-StderrSummary -Path $StderrLog). See $StderrLog"
        if ([string]$Disposition.Disposition -eq "RECOVERABLE_INTERRUPTION") {
            Record-RecoverableInterruption -Snapshot $PostSnapshot -Message $failureText
        }
        Record-RunnerFailure -Phase "LAUNCHER_ERROR" -Message $failureText
    }
    if ([string]::IsNullOrWhiteSpace([string]$State.thread_id)) {
        Record-RunnerFailure -Phase "FAILED_NO_THREAD_ID" -Message "Codex exited successfully without a thread.started ID."
    }
    if (-not (Test-Path -LiteralPath $LastMessage -PathType Leaf)) {
        Record-RunnerFailure -Phase "ACTIVE_NO_MARKER" -Message "Codex produced no last-message file: $LastMessage"
    }
    $LastText = [System.IO.File]::ReadAllText($LastMessage)
    $Marker = Resolve-AutomationStatusMarker -Text $LastText
    if (-not $Marker.Valid) {
        Record-RunnerFailure -Phase "ACTIVE_NO_MARKER" -Message ([string]$Marker.Error)
    }

    if ([string]$Marker.Status -eq "WAITING_DETACHED") {
        try {
            $ManifestPath = Resolve-AutomationDetachedManifestPath -Text $LastText
            $DetachedJob = Read-AutomationDetachedJobManifest -Path $ManifestPath -Repo $Repo
        }
        catch {
            Record-RunnerFailure -Phase "ACTIVE_NO_MARKER" -Message "Invalid WAITING_DETACHED contract: $($_.Exception.Message)"
        }
        Set-AutomationObjectProperty -Object $State -Name "detached_job" -Value $DetachedJob
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

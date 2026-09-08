$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:AutomationConfigSchema = "sktlm-codex-automation-config/v1"
$script:AutomationStateSchema = "sktlm-codex-automation/v1"
$script:AutomationPhases = @(
    "READY",
    "RUNNING",
    "ACTIVE",
    "INTERRUPTED_RECOVERABLE",
    "WAITING_DETACHED",
    "WAITING_EXTERNAL",
    "COMPLETE",
    "BLOCKED_DIRTY_TREE",
    "BLOCKED_WRONG_BRANCH",
    "BLOCKED_INCOMPATIBLE_HEAD",
    "BLOCKED_REMOTE_DIVERGENCE",
    "FAILED_NO_THREAD_ID",
    "THREAD_MISMATCH",
    "LAST_WAKE_FAILED",
    "ACTIVE_NO_MARKER",
    "LAUNCHER_ERROR"
)

function Assert-AutomationId {
    param([Parameter(Mandatory = $true)][string]$AutomationId)

    if ($AutomationId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
        throw "AutomationId must use only ASCII letters, digits, dot, underscore, or dash, and must start with a letter or digit."
    }
}

function Assert-ObjectProperties {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string[]]$Names,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $available = @($Value.PSObject.Properties.Name)
    foreach ($name in $Names) {
        if ($available -notcontains $name) {
            throw "$Label is missing required property '$name'."
        }
    }
}

function Assert-AutomationConfig {
    param([Parameter(Mandatory = $true)][object]$Config)

    Assert-ObjectProperties -Value $Config -Label "config.json" -Names @(
        "schema_version",
        "task_name",
        "automation_id",
        "repo",
        "expected_branch",
        "base_head",
        "remote_ref",
        "automation_root",
        "state_path",
        "initial_prompt_path",
        "initial_prompt_sha256",
        "resume_prompt_path",
        "resume_prompt_sha256",
        "logs_dir",
        "runner_path",
        "codex_path",
        "mutex_name",
        "schedule_anchor",
        "registered_start",
        "interval_minutes",
        "execution_time_limit_hours",
        "task_action",
        "registration_performed"
    )
    if ([string]$Config.schema_version -ne $script:AutomationConfigSchema) {
        throw "Unsupported config schema: $($Config.schema_version)"
    }
    Assert-AutomationId -AutomationId ([string]$Config.automation_id)
    if ([string]::IsNullOrWhiteSpace([string]$Config.task_name)) {
        throw "config.json task_name is empty."
    }
    if ([string]::IsNullOrWhiteSpace([string]$Config.expected_branch)) {
        throw "config.json expected_branch is empty."
    }
    if ([int]$Config.interval_minutes -lt 1) {
        throw "config.json interval_minutes must be positive."
    }
    if ([int]$Config.execution_time_limit_hours -lt 1) {
        throw "config.json execution_time_limit_hours must be positive."
    }
    [void][datetime]::Parse([string]$Config.schedule_anchor)
    [void][datetime]::Parse([string]$Config.registered_start)
}

function Assert-AutomationState {
    param(
        [Parameter(Mandatory = $true)][object]$State,
        [object]$Config = $null
    )

    Assert-ObjectProperties -Value $State -Label "state.json" -Names @(
        "schema_version",
        "task_name",
        "automation_id",
        "repo",
        "expected_branch",
        "base_head",
        "thread_id",
        "phase",
        "last_wake",
        "last_exit_code",
        "last_json_log",
        "last_stderr_log",
        "last_message_file",
        "last_observed_head",
        "last_error"
    )
    if ([string]$State.schema_version -ne $script:AutomationStateSchema) {
        throw "Unsupported state schema: $($State.schema_version)"
    }
    if ($script:AutomationPhases -notcontains [string]$State.phase) {
        throw "Unsupported automation phase: $($State.phase)"
    }
    Assert-AutomationId -AutomationId ([string]$State.automation_id)
    if ($null -ne $Config) {
        if ([string]$State.task_name -cne [string]$Config.task_name) {
            throw "state.json task_name does not match config.json."
        }
        if ([string]$State.automation_id -cne [string]$Config.automation_id) {
            throw "state.json automation_id does not match config.json."
        }
        if ([string]$State.repo -cne [string]$Config.repo) {
            throw "state.json repo does not match config.json."
        }
        if ([string]$State.expected_branch -cne [string]$Config.expected_branch) {
            throw "state.json expected_branch does not match config.json."
        }
        if ([string]$State.base_head -cne [string]$Config.base_head) {
            throw "state.json base_head does not match config.json."
        }
    }
    if ((@("ACTIVE", "INTERRUPTED_RECOVERABLE", "WAITING_DETACHED", "WAITING_EXTERNAL", "COMPLETE") -contains [string]$State.phase) -and
        [string]::IsNullOrWhiteSpace([string]$State.thread_id)) {
        throw "Phase $($State.phase) requires an exact stored thread_id."
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($Path), $Text, $encoding)
}

function Read-AutomationJson {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required JSON file not found: $Path"
    }
    try {
        return ([System.IO.File]::ReadAllText($Path) | ConvertFrom-Json -ErrorAction Stop)
    }
    catch {
        throw "Invalid JSON file '$Path': $($_.Exception.Message)"
    }
}

function Write-AutomationJsonAtomic {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Value
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $directory = [System.IO.Path]::GetDirectoryName($fullPath)
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw "JSON parent directory does not exist: $directory"
    }
    $temporary = "$fullPath.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
    $backup = "$fullPath.bak.$PID.$([guid]::NewGuid().ToString('N'))"
    $json = $Value | ConvertTo-Json -Depth 16
    try {
        Write-Utf8NoBom -Path $temporary -Text ($json + "`r`n")
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            [System.IO.File]::Replace($temporary, $fullPath, $backup)
            Remove-Item -LiteralPath $backup -Force
        }
        else {
            [System.IO.File]::Move($temporary, $fullPath)
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary -Force
        }
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            Remove-Item -LiteralPath $backup -Force
        }
    }
}

function Get-NextScheduleOccurrence {
    param(
        [Parameter(Mandatory = $true)][datetime]$Anchor,
        [Parameter(Mandatory = $true)][ValidateRange(1, 525600)][int]$IntervalMinutes,
        [Parameter(Mandatory = $true)][datetime]$Now
    )

    if ($Anchor -gt $Now) {
        return $Anchor
    }
    $elapsedMinutes = ($Now - $Anchor).TotalMinutes
    $steps = [math]::Floor($elapsedMinutes / $IntervalMinutes) + 1
    return $Anchor.AddMinutes($steps * $IntervalMinutes)
}

function New-AutomationScheduleDefinition {
    param(
        [Parameter(Mandatory = $true)][datetime]$Anchor,
        [Parameter(Mandatory = $true)][ValidateRange(1, 525600)][int]$IntervalMinutes,
        [Parameter(Mandatory = $true)][datetime]$Now,
        [ValidateRange(1, 20)][int]$PreviewCount = 6
    )

    $registeredStart = Get-NextScheduleOccurrence -Anchor $Anchor -IntervalMinutes $IntervalMinutes -Now $Now
    $preview = @()
    for ($index = 0; $index -lt $PreviewCount; $index += 1) {
        $preview += $Anchor.AddMinutes($index * $IntervalMinutes)
    }
    return [pscustomobject]@{
        Anchor = $Anchor
        RegisteredStart = $registeredStart
        IntervalMinutes = $IntervalMinutes
        Preview = $preview
    }
}

function New-RunnerActionDefinition {
    param(
        [Parameter(Mandatory = $true)][string]$RunnerPath,
        [Parameter(Mandatory = $true)][string]$ConfigPath
    )

    if ($RunnerPath.Contains('"') -or $ConfigPath.Contains('"')) {
        throw "RunnerPath and ConfigPath must not contain a double quote."
    }
    $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -ConfigPath "{1}"' -f $RunnerPath, $ConfigPath
    return [pscustomobject]@{
        Execute = "powershell.exe"
        Arguments = $arguments
    }
}

function Get-AutomationRepoMutexName {
    param([Parameter(Mandatory = $true)][string]$Repo)

    $canonical = [System.IO.Path]::GetFullPath($Repo).TrimEnd([char[]]@('\', '/')).ToUpperInvariant()
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($canonical)
        $hash = [System.BitConverter]::ToString($sha256.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
    return "Local\SKTLM_CodexAutomation_Repo_$hash"
}

function Enter-AutomationMutex {
    param([Parameter(Mandatory = $true)][string]$Name)

    $mutex = New-Object System.Threading.Mutex($false, $Name)
    try {
        try {
            $acquired = $mutex.WaitOne(0, $false)
        }
        catch [System.Threading.AbandonedMutexException] {
            $acquired = $true
        }
        return [pscustomobject]@{
            Name = $Name
            Mutex = $mutex
            Acquired = [bool]$acquired
        }
    }
    catch {
        $mutex.Dispose()
        throw
    }
}

function Exit-AutomationMutex {
    param([Parameter(Mandatory = $true)][object]$Lock)

    if ([bool]$Lock.Acquired) {
        try { $Lock.Mutex.ReleaseMutex() | Out-Null } catch {}
    }
    $Lock.Mutex.Dispose()
}

function Get-GenericAutomationTaskIdentity {
    param([Parameter(Mandatory = $true)][object]$Task)

    $notGeneric = {
        param([string]$Reason)
        return [pscustomobject]@{
            IsGeneric = $false
            Reason = $Reason
            TaskName = [string]$Task.TaskName
            Repo = $null
            ConfigPath = $null
        }
    }
    $actions = @($Task.Actions)
    if ($actions.Count -ne 1) {
        return (& $notGeneric "expected exactly one action")
    }
    $executeName = [System.IO.Path]::GetFileName([string]$actions[0].Execute)
    if (@("powershell.exe", "pwsh.exe") -notcontains $executeName.ToLowerInvariant()) {
        return (& $notGeneric "action is not PowerShell")
    }
    $pattern = '^-NoProfile\s+-NonInteractive\s+-ExecutionPolicy\s+Bypass\s+-File\s+"(?<runner>[^"]+\\\.codex\\automation\\run_task\.ps1)"\s+-ConfigPath\s+"(?<config>[^"]+\\config\.json)"$'
    $match = [regex]::Match([string]$actions[0].Arguments, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $match.Success) {
        return (& $notGeneric "action is not the generic runner contract")
    }
    $runnerPath = [System.IO.Path]::GetFullPath($match.Groups["runner"].Value)
    $configPath = [System.IO.Path]::GetFullPath($match.Groups["config"].Value)
    try {
        $config = Read-AutomationJson -Path $configPath
        Assert-AutomationConfig -Config $config
        $configuredRunner = [System.IO.Path]::GetFullPath([string]$config.runner_path)
        $configuredRoot = [System.IO.Path]::GetFullPath([string]$config.automation_root)
        $configRoot = [System.IO.Path]::GetDirectoryName($configPath)
        if (-not [string]::Equals($runnerPath, $configuredRunner, [System.StringComparison]::OrdinalIgnoreCase)) {
            return (& $notGeneric "runner path does not match config")
        }
        if (-not [string]::Equals($configRoot, $configuredRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            return (& $notGeneric "config path does not match automation root")
        }
        if (-not [string]::Equals([string]$Task.TaskName, [string]$config.task_name, [System.StringComparison]::OrdinalIgnoreCase)) {
            return (& $notGeneric "task name does not match config")
        }
        if (-not [string]::Equals([string]$actions[0].Execute, [string]$config.task_action.execute, [System.StringComparison]::OrdinalIgnoreCase) -or
            -not [string]::Equals([string]$actions[0].Arguments, [string]$config.task_action.arguments, [System.StringComparison]::OrdinalIgnoreCase)) {
            return (& $notGeneric "task action does not match config")
        }
    }
    catch {
        return (& $notGeneric "config validation failed: $($_.Exception.Message)")
    }
    return [pscustomobject]@{
        IsGeneric = $true
        Reason = $null
        TaskName = [string]$Task.TaskName
        Repo = [System.IO.Path]::GetFullPath([string]$config.repo)
        ConfigPath = $configPath
    }
}

function Get-AutomationTaskInventory {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Tasks
    )

    $exact = @($Tasks | Where-Object { [string]::Equals([string]$_.TaskName, $TaskName, [System.StringComparison]::OrdinalIgnoreCase) })
    $generic = @()
    foreach ($task in $Tasks) {
        $identity = Get-GenericAutomationTaskIdentity -Task $task
        if ($identity.IsGeneric) {
            $generic += $identity
        }
    }
    return [pscustomobject]@{
        ExactTaskCount = $exact.Count
        GenericTasks = $generic
    }
}

function Test-FrozenPromptIntegrity {
    param([Parameter(Mandatory = $true)][object]$Config)

    $checks = @(
        [pscustomobject]@{ Path = [string]$Config.initial_prompt_path; Hash = [string]$Config.initial_prompt_sha256 },
        [pscustomobject]@{ Path = [string]$Config.resume_prompt_path; Hash = [string]$Config.resume_prompt_sha256 }
    )
    foreach ($check in $checks) {
        if (-not (Test-Path -LiteralPath $check.Path -PathType Leaf)) {
            return [pscustomobject]@{ Valid = $false; Reason = "Frozen prompt not found: $($check.Path)" }
        }
        $observed = (Get-FileHash -LiteralPath $check.Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($observed -cne $check.Hash) {
            return [pscustomobject]@{ Valid = $false; Reason = "Frozen prompt hash mismatch: $($check.Path)" }
        }
    }
    return [pscustomobject]@{ Valid = $true; Reason = $null }
}

function Set-AutomationObjectProperty {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowNull()][object]$Value
    )

    if ($Object.PSObject.Properties.Name -contains $Name) {
        $Object.$Name = $Value
    }
    else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function Get-TextSha256 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        return [System.BitConverter]::ToString($sha256.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-AutomationWorkspaceSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Repo,
        [Parameter(Mandatory = $true)][string]$GitPath,
        [Parameter(Mandatory = $true)][string]$RemoteRef
    )

    $Repo = [System.IO.Path]::GetFullPath($Repo)

    function Invoke-WorkspaceGit {
        param([Parameter(Mandatory = $true)][string[]]$Arguments)

        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $output = @(& $GitPath -C $Repo @Arguments 2>$null)
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousPreference
        }
        if ($exitCode -ne 0) {
            throw "git $($Arguments -join ' ') failed while fingerprinting the workspace."
        }
        return @($output)
    }

    $unstaged = @(Invoke-WorkspaceGit -Arguments @("diff", "--binary", "--no-ext-diff", "--")) -join "`n"
    $staged = @(Invoke-WorkspaceGit -Arguments @("diff", "--cached", "--binary", "--no-ext-diff", "--")) -join "`n"
    $untracked = @(
        Invoke-WorkspaceGit -Arguments @("-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", "--") |
            Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } |
            Sort-Object
    )
    $untrackedRecords = @()
    foreach ($relativePath in $untracked) {
        $fullPath = [System.IO.Path]::GetFullPath((Join-Path $Repo ([string]$relativePath)))
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            throw "Untracked workspace file disappeared while fingerprinting: $relativePath"
        }
        $fileHash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $length = (Get-Item -LiteralPath $fullPath).Length
        $untrackedRecords += "$relativePath`t$length`t$fileHash"
    }
    $payload = @(
        "UNSTAGED_SHA256=$(Get-TextSha256 -Text $unstaged)",
        "STAGED_SHA256=$(Get-TextSha256 -Text $staged)",
        "UNTRACKED_COUNT=$($untrackedRecords.Count)",
        ($untrackedRecords -join "`n")
    ) -join "`n"
    $status = @(Invoke-WorkspaceGit -Arguments @("-c", "core.quotepath=false", "status", "--porcelain=v1", "--untracked-files=all"))
    $head = (@(Invoke-WorkspaceGit -Arguments @("rev-parse", "HEAD")) -join "`n").Trim()
    $remoteHead = (@(Invoke-WorkspaceGit -Arguments @("rev-parse", $RemoteRef)) -join "`n").Trim()
    return [pscustomobject]@{
        fingerprint = (Get-TextSha256 -Text $payload)
        head = $head
        remote_head = $remoteHead
        is_clean = ($status.Count -eq 0)
        unstaged_sha256 = (Get-TextSha256 -Text $unstaged)
        staged_sha256 = (Get-TextSha256 -Text $staged)
        untracked_count = $untrackedRecords.Count
    }
}

function New-AutomationWorkspaceCheckpoint {
    param([Parameter(Mandatory = $true)][object]$Snapshot)

    return [pscustomobject]@{
        fingerprint = [string]$Snapshot.fingerprint
        head = [string]$Snapshot.head
        remote_head = [string]$Snapshot.remote_head
        recorded_at = (Get-Date).ToString("o")
    }
}

function Test-AutomationContinuationCheckpoint {
    param(
        [Parameter(Mandatory = $true)][object]$Snapshot,
        [Parameter(Mandatory = $true)][object]$Checkpoint
    )

    try {
        Assert-ObjectProperties -Value $Checkpoint -Label "workspace checkpoint" -Names @("fingerprint", "head", "remote_head")
    }
    catch {
        return [pscustomobject]@{ Valid = $false; Reason = $_.Exception.Message }
    }
    if ([string]$Snapshot.fingerprint -cne [string]$Checkpoint.fingerprint) {
        return [pscustomobject]@{ Valid = $false; Reason = "Workspace content changed outside the recorded continuation checkpoint." }
    }
    if ([string]$Snapshot.head -cne [string]$Checkpoint.head) {
        return [pscustomobject]@{ Valid = $false; Reason = "Local HEAD changed outside the recorded continuation checkpoint." }
    }
    if ([string]$Snapshot.remote_head -cne [string]$Checkpoint.remote_head) {
        return [pscustomobject]@{ Valid = $false; Reason = "Remote HEAD changed outside the recorded continuation checkpoint." }
    }
    return [pscustomobject]@{ Valid = $true; Reason = $null }
}

function Test-AutomationRepoSnapshot {
    param(
        [Parameter(Mandatory = $true)][object]$Config,
        [Parameter(Mandatory = $true)][string]$CurrentBranch,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Dirty,
        [Parameter(Mandatory = $true)][string]$Head,
        [Parameter(Mandatory = $true)][bool]$BaseIsAncestor,
        [Parameter(Mandatory = $true)][string]$RemoteHead
    )

    if ($CurrentBranch -cne [string]$Config.expected_branch) {
        return [pscustomobject]@{ Valid = $false; Reason = "Expected branch '$($Config.expected_branch)', got '$CurrentBranch'." }
    }
    if (-not [string]::IsNullOrWhiteSpace($Dirty)) {
        return [pscustomobject]@{ Valid = $false; Reason = "Working tree is dirty." }
    }
    if (-not $BaseIsAncestor) {
        return [pscustomobject]@{ Valid = $false; Reason = "Current HEAD $Head is not descended from base HEAD $($Config.base_head)." }
    }
    if ($Head -cne $RemoteHead) {
        return [pscustomobject]@{ Valid = $false; Reason = "Local HEAD and $($Config.remote_ref) differ. local=$Head remote=$RemoteHead" }
    }
    return [pscustomobject]@{ Valid = $true; Reason = $null }
}

function Test-ScheduledTaskIdentity {
    param(
        [Parameter(Mandatory = $true)][object]$Task,
        [Parameter(Mandatory = $true)][object]$Config
    )

    if (-not [string]::Equals([string]$Task.TaskName, [string]$Config.task_name, [System.StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Valid = $false; Reason = "Scheduled Task name does not match config." }
    }
    $actions = @($Task.Actions)
    if ($actions.Count -ne 1 -or
        -not [string]::Equals([string]$actions[0].Execute, [string]$Config.task_action.execute, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals([string]$actions[0].Arguments, [string]$Config.task_action.arguments, [System.StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Valid = $false; Reason = "Scheduled Task action does not match config." }
    }
    $triggers = @($Task.Triggers)
    if ($triggers.Count -ne 1) {
        return [pscustomobject]@{ Valid = $false; Reason = "Scheduled Task must have exactly one trigger." }
    }
    try {
        $actualStart = [datetime]::Parse([string]$triggers[0].StartBoundary).ToString("yyyy-MM-ddTHH:mm:ss")
        $expectedStart = [datetime]::Parse([string]$Config.registered_start).ToString("yyyy-MM-ddTHH:mm:ss")
        $actualInterval = [System.Xml.XmlConvert]::ToTimeSpan([string]$triggers[0].Repetition.Interval).TotalMinutes
        $actualDuration = [System.Xml.XmlConvert]::ToTimeSpan([string]$triggers[0].Repetition.Duration).TotalDays
    }
    catch {
        return [pscustomobject]@{ Valid = $false; Reason = "Scheduled Task trigger is not parseable: $($_.Exception.Message)" }
    }
    if ($actualStart -cne $expectedStart -or [int]$actualInterval -ne [int]$Config.interval_minutes) {
        return [pscustomobject]@{ Valid = $false; Reason = "Scheduled Task start/interval does not match config." }
    }
    if ($Config.PSObject.Properties.Name -contains "repetition_duration_days" -and
        [int]$actualDuration -ne [int]$Config.repetition_duration_days) {
        return [pscustomobject]@{ Valid = $false; Reason = "Scheduled Task repetition duration does not match config." }
    }
    return [pscustomobject]@{ Valid = $true; Reason = $null }
}

function Test-PreThreadRecoveryEligibility {
    param([Parameter(Mandatory = $true)][object]$State)

    if ([string]$State.phase -cne "LAUNCHER_ERROR") {
        return [pscustomobject]@{ Eligible = $false; Reason = "RecoverPreThread requires phase LAUNCHER_ERROR." }
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$State.thread_id)) {
        return [pscustomobject]@{ Eligible = $false; Reason = "RecoverPreThread requires an empty thread_id." }
    }
    if ([string]::IsNullOrWhiteSpace([string]$State.last_error)) {
        return [pscustomobject]@{ Eligible = $false; Reason = "RecoverPreThread requires a recorded launcher error." }
    }
    if ($null -ne $State.last_exit_code -and [int]$State.last_exit_code -eq 0) {
        return [pscustomobject]@{ Eligible = $false; Reason = "A successful prior Codex exit is not a recoverable pre-thread launcher error." }
    }
    if ([string]::IsNullOrWhiteSpace([string]$State.last_json_log) -or
        -not (Test-Path -LiteralPath ([string]$State.last_json_log) -PathType Leaf)) {
        return [pscustomobject]@{ Eligible = $false; Reason = "RecoverPreThread requires the prior JSONL launch log." }
    }
    if ([string]::IsNullOrWhiteSpace([string]$State.last_stderr_log) -or
        -not (Test-Path -LiteralPath ([string]$State.last_stderr_log) -PathType Leaf)) {
        return [pscustomobject]@{ Eligible = $false; Reason = "RecoverPreThread requires the prior stderr launch log." }
    }
    try {
        $ids = @(Get-ThreadIdsFromJsonLines -Lines @([System.IO.File]::ReadLines([string]$State.last_json_log)))
    }
    catch {
        return [pscustomobject]@{ Eligible = $false; Reason = "Prior JSONL cannot prove no thread was created: $($_.Exception.Message)" }
    }
    if ($ids.Count -ne 0) {
        return [pscustomobject]@{ Eligible = $false; Reason = "Prior JSONL records a created Codex thread." }
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$State.last_message_file) -and
        (Test-Path -LiteralPath ([string]$State.last_message_file) -PathType Leaf) -and
        (Get-Item -LiteralPath ([string]$State.last_message_file)).Length -gt 0) {
        return [pscustomobject]@{ Eligible = $false; Reason = "Prior wake produced a last message and is not safely pre-thread." }
    }
    return [pscustomobject]@{ Eligible = $true; Reason = $null }
}

function Test-InterruptedRecoveryEligibility {
    param([Parameter(Mandatory = $true)][object]$State)

    if (@("LAUNCHER_ERROR", "LAST_WAKE_FAILED") -notcontains [string]$State.phase) {
        return [pscustomobject]@{ Eligible = $false; ThreadId = $null; Reason = "RecoverInterrupted requires a legacy interrupted phase." }
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$State.thread_id)) {
        return [pscustomobject]@{ Eligible = $false; ThreadId = $null; Reason = "RecoverInterrupted is only for legacy state with an empty thread_id." }
    }
    if ([string]::IsNullOrWhiteSpace([string]$State.last_json_log) -or
        -not (Test-Path -LiteralPath ([string]$State.last_json_log) -PathType Leaf)) {
        return [pscustomobject]@{ Eligible = $false; ThreadId = $null; Reason = "RecoverInterrupted requires the preserved JSONL log." }
    }
    try {
        $ids = @(Get-SalvageableThreadIdsFromJsonLog -Path ([string]$State.last_json_log))
    }
    catch {
        return [pscustomobject]@{ Eligible = $false; ThreadId = $null; Reason = "Cannot salvage thread identity: $($_.Exception.Message)" }
    }
    if ($ids.Count -ne 1) {
        return [pscustomobject]@{ Eligible = $false; ThreadId = $null; Reason = "RecoverInterrupted requires exactly one JSONL thread.started ID; found $($ids.Count)." }
    }
    return [pscustomobject]@{ Eligible = $true; ThreadId = [string]$ids[0]; Reason = $null }
}

function Add-AutomationRuntimeContract {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$PromptText)

    $overlay = @'


# CURRENT AUTOMATION CONTINUATION CONTRACT

This current framework contract supersedes any earlier list of allowed AUTOMATION_STATUS values in the frozen prompt.

End with exactly one status marker as the final non-empty line:
AUTOMATION_STATUS=CONTINUE
AUTOMATION_STATUS=WAITING_EXTERNAL
AUTOMATION_STATUS=WAITING_DETACHED
AUTOMATION_STATUS=COMPLETE

Use WAITING_EXTERNAL only when the researcher must perform an action; it disables scheduling. Use WAITING_DETACHED only after successfully starting a detached workload whose tracked-source workspace will remain unchanged. Its outputs must be under the repository artifacts/runtime area. Before WAITING_DETACHED, output exactly one line `AUTOMATION_DETACHED_MANIFEST=<absolute-json-path>`. The immutable JSON manifest must contain schema_version `sktlm-codex-detached-job/v1`, job_id, command_identity, process_identity, pid, process_start_time_utc, completion_marker_path, result_path, and exit_status_path. The detached wrapper must atomically write exit_status_path with matching job_id, command_identity, integer exit_code, and completed_at.

Never edit automation config/state/prompt snapshots/logs or Scheduled Task triggers. Never use resume --last.
'@
    return $PromptText.TrimEnd() + $overlay + "`r`n"
}

function Get-ThreadIdsFromJsonLog {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$AllowIncompleteLastLine
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @()
    }
    $text = [System.IO.File]::ReadAllText($Path)
    if ([string]::IsNullOrEmpty($text)) {
        return @()
    }
    $lines = @($text -split "\r?\n")
    if ($AllowIncompleteLastLine -and $text -notmatch "[\r\n]$") {
        if ($lines.Count -gt 0) {
            $lines = @($lines | Select-Object -First ($lines.Count - 1))
        }
    }
    $lines = @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($lines.Count -eq 0) { return @() }
    return @(Get-ThreadIdsFromJsonLines -Lines $lines)
}

function Get-SalvageableThreadIdsFromJsonLog {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @()
    }
    $ids = @()
    foreach ($line in [System.IO.File]::ReadLines($Path)) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line -notmatch '"thread\.started"') {
            continue
        }
        try {
            $event = $line | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            throw "A candidate thread.started JSONL line is invalid."
        }
        if ([string]$event.type -eq "thread.started") {
            if ([string]::IsNullOrWhiteSpace([string]$event.thread_id)) {
                throw "thread.started event has no thread_id."
            }
            $ids += [string]$event.thread_id
        }
    }
    return @($ids | Select-Object -Unique)
}

function Resolve-CodexProcessDisposition {
    param(
        [Parameter(Mandatory = $true)][bool]$HasThreadId,
        [AllowNull()][object]$ExitCode,
        [AllowNull()][string]$LauncherError
    )

    $abnormal = -not [string]::IsNullOrWhiteSpace($LauncherError) -or $null -eq $ExitCode -or [int]$ExitCode -ne 0
    if (-not $abnormal) {
        return [pscustomobject]@{ Disposition = "SUCCESS"; Phase = $null; DisableTask = $false }
    }
    if ($HasThreadId) {
        return [pscustomobject]@{ Disposition = "RECOVERABLE_INTERRUPTION"; Phase = "INTERRUPTED_RECOVERABLE"; DisableTask = $false }
    }
    return [pscustomobject]@{ Disposition = "PRETHREAD_FAILURE"; Phase = "LAUNCHER_ERROR"; DisableTask = $true }
}

function Resolve-AutomationDetachedManifestPath {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    $matches = [regex]::Matches($Text, '(?m)^AUTOMATION_DETACHED_MANIFEST=([^\r\n]+)\r?$')
    if ($matches.Count -ne 1) {
        throw "WAITING_DETACHED requires exactly one AUTOMATION_DETACHED_MANIFEST line; found $($matches.Count)."
    }
    $path = $matches[0].Groups[1].Value.Trim()
    if (-not [System.IO.Path]::IsPathRooted($path)) {
        throw "AUTOMATION_DETACHED_MANIFEST must be an absolute path."
    }
    return [System.IO.Path]::GetFullPath($path)
}

function Test-AutomationPathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $fullRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd([char[]]@('\', '/'))
    return $fullPath.StartsWith($fullRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function Read-AutomationDetachedJobManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Repo
    )

    $Path = [System.IO.Path]::GetFullPath($Path)
    $artifactsRoot = Join-Path ([System.IO.Path]::GetFullPath($Repo)) "artifacts"
    if (-not (Test-AutomationPathWithinRoot -Path $Path -Root $artifactsRoot)) {
        throw "Detached job manifest must be under the repository artifacts directory."
    }
    $manifest = Read-AutomationJson -Path $Path
    Assert-ObjectProperties -Value $manifest -Label "detached job manifest" -Names @(
        "schema_version", "job_id", "command_identity", "process_identity", "pid",
        "process_start_time_utc", "completion_marker_path", "result_path", "exit_status_path"
    )
    if ([string]$manifest.schema_version -cne "sktlm-codex-detached-job/v1") {
        throw "Unsupported detached job manifest schema: $($manifest.schema_version)"
    }
    foreach ($name in @("job_id", "command_identity", "process_identity", "process_start_time_utc")) {
        if ([string]::IsNullOrWhiteSpace([string]$manifest.$name)) {
            throw "Detached job manifest property '$name' is empty."
        }
    }
    if ([int64]$manifest.pid -le 0) {
        throw "Detached job manifest pid must be positive."
    }
    [void][datetime]::Parse([string]$manifest.process_start_time_utc)
    $paths = @{}
    foreach ($name in @("completion_marker_path", "result_path", "exit_status_path")) {
        $candidate = [System.IO.Path]::GetFullPath([string]$manifest.$name)
        if (-not (Test-AutomationPathWithinRoot -Path $candidate -Root $artifactsRoot)) {
            throw "Detached job manifest property '$name' must be under the repository artifacts directory."
        }
        $paths[$name] = $candidate
    }
    return [pscustomobject]@{
        manifest_path = $Path
        manifest_sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        job_id = [string]$manifest.job_id
        command_identity = [string]$manifest.command_identity
        process_identity = [string]$manifest.process_identity
        pid = [int64]$manifest.pid
        process_start_time_utc = ([datetime]::Parse([string]$manifest.process_start_time_utc)).ToUniversalTime().ToString("o")
        completion_marker_path = [string]$paths["completion_marker_path"]
        result_path = [string]$paths["result_path"]
        exit_status_path = [string]$paths["exit_status_path"]
        status = "RUNNING"
        observed_at = (Get-Date).ToString("o")
        exit_code = $null
        detail = $null
    }
}

function Get-AutomationDetachedJobObservation {
    param([Parameter(Mandatory = $true)][object]$Job)

    if (-not (Test-Path -LiteralPath ([string]$Job.manifest_path) -PathType Leaf)) {
        return [pscustomobject]@{ State = "COMPLETED_FAILURE"; ExitCode = $null; Detail = "Detached job manifest disappeared." }
    }
    $manifestHash = (Get-FileHash -LiteralPath ([string]$Job.manifest_path) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($manifestHash -cne [string]$Job.manifest_sha256) {
        return [pscustomobject]@{ State = "COMPLETED_FAILURE"; ExitCode = $null; Detail = "Detached job manifest changed after registration." }
    }
    if (Test-Path -LiteralPath ([string]$Job.exit_status_path) -PathType Leaf) {
        try {
            $status = Read-AutomationJson -Path ([string]$Job.exit_status_path)
            Assert-ObjectProperties -Value $status -Label "detached exit status" -Names @("job_id", "command_identity", "exit_code", "completed_at")
            if ([string]$status.job_id -cne [string]$Job.job_id -or
                [string]$status.command_identity -cne [string]$Job.command_identity) {
                throw "Detached exit status identity does not match the manifest."
            }
            $exitCode = [int]$status.exit_code
            [void][datetime]::Parse([string]$status.completed_at)
            if ($exitCode -eq 0 -and
                (Test-Path -LiteralPath ([string]$Job.completion_marker_path)) -and
                (Test-Path -LiteralPath ([string]$Job.result_path))) {
                return [pscustomobject]@{ State = "COMPLETED_SUCCESS"; ExitCode = 0; Detail = "Detached job completed successfully." }
            }
            return [pscustomobject]@{ State = "COMPLETED_FAILURE"; ExitCode = $exitCode; Detail = "Detached job completed without the required successful result/marker." }
        }
        catch {
            return [pscustomobject]@{ State = "COMPLETED_FAILURE"; ExitCode = $null; Detail = $_.Exception.Message }
        }
    }
    $process = Get-Process -Id ([int]$Job.pid) -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        try {
            $actualStart = $process.StartTime.ToUniversalTime()
            $expectedStart = ([datetime]::Parse([string]$Job.process_start_time_utc)).ToUniversalTime()
            if ([math]::Abs(($actualStart - $expectedStart).TotalSeconds) -lt 1.0) {
                return [pscustomobject]@{ State = "RUNNING"; ExitCode = $null; Detail = "Detached process identity is still running." }
            }
        }
        catch {}
    }
    return [pscustomobject]@{ State = "COMPLETED_FAILURE"; ExitCode = $null; Detail = "Detached process identity is no longer running and no exit status exists." }
}

function New-CodexInvocation {
    param(
        [Parameter(Mandatory = $true)][string]$Repo,
        [Parameter(Mandatory = $true)][string]$LastMessagePath,
        [Parameter(Mandatory = $true)][string]$InitialPromptPath,
        [Parameter(Mandatory = $true)][string]$ResumePromptPath,
        [AllowNull()][string]$ThreadId
    )

    $arguments = @(
        "exec",
        "-C",
        $Repo,
        "--approve-for-me",
        "--json",
        "--output-last-message",
        $LastMessagePath
    )
    if ([string]::IsNullOrWhiteSpace($ThreadId)) {
        $arguments += "-"
        $mode = "NEW"
        $promptPath = $InitialPromptPath
    }
    else {
        $arguments += @("resume", $ThreadId, "-")
        $mode = "RESUME_EXACT"
        $promptPath = $ResumePromptPath
    }
    if ($arguments -contains "--last") {
        throw "Internal error: resume --last is forbidden."
    }
    return [pscustomobject]@{
        Mode = $mode
        PromptPath = $promptPath
        ArgumentList = [string[]]$arguments
    }
}

function Resolve-AutomationStatusMarker {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    $matches = [regex]::Matches($Text, '(?m)^AUTOMATION_STATUS=([^\r\n]*)\r?$')
    if ($matches.Count -ne 1) {
        return [pscustomobject]@{
            Valid = $false
            Status = $null
            Phase = "ACTIVE_NO_MARKER"
            DisableTask = $true
            Error = "Expected exactly one AUTOMATION_STATUS marker; found $($matches.Count)."
        }
    }
    $status = $matches[0].Groups[1].Value
    if (@("CONTINUE", "WAITING_EXTERNAL", "WAITING_DETACHED", "COMPLETE") -notcontains $status) {
        return [pscustomobject]@{
            Valid = $false
            Status = $status
            Phase = "ACTIVE_NO_MARKER"
            DisableTask = $true
            Error = "Unknown AUTOMATION_STATUS marker: $status"
        }
    }
    $nonEmpty = @(
        $Text -split "\r?\n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -ne "" }
    )
    $expected = "AUTOMATION_STATUS=$status"
    if ($nonEmpty.Count -eq 0 -or $nonEmpty[-1] -cne $expected) {
        return [pscustomobject]@{
            Valid = $false
            Status = $status
            Phase = "ACTIVE_NO_MARKER"
            DisableTask = $true
            Error = "AUTOMATION_STATUS marker is not the final non-empty line."
        }
    }
    switch ($status) {
        "CONTINUE" { $phase = "ACTIVE"; $disable = $false }
        "WAITING_EXTERNAL" { $phase = "WAITING_EXTERNAL"; $disable = $true }
        "WAITING_DETACHED" { $phase = "WAITING_DETACHED"; $disable = $false }
        "COMPLETE" { $phase = "COMPLETE"; $disable = $true }
    }
    return [pscustomobject]@{
        Valid = $true
        Status = $status
        Phase = $phase
        DisableTask = $disable
        Error = $null
    }
}

function Get-ThreadIdsFromJsonLines {
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Lines)

    $ids = @()
    foreach ($line in $Lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        try {
            $event = $line | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            throw "Codex JSONL contains an invalid JSON line."
        }
        if ([string]$event.type -eq "thread.started") {
            if ([string]::IsNullOrWhiteSpace([string]$event.thread_id)) {
                throw "thread.started event has no thread_id."
            }
            $ids += [string]$event.thread_id
        }
    }
    return @($ids | Select-Object -Unique)
}

function Get-AutomationControlPlan {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Status", "Wake", "ResumeExternal", "RecoverPreThread", "RecoverInterrupted")][string]$Action,
        [Parameter(Mandatory = $true)][string]$Phase,
        [AllowNull()][string]$ThreadId,
        [switch]$StartNow
    )

    if ($Action -eq "Status") {
        return [pscustomobject]@{
            NewPhase = $Phase
            EnableTask = $false
            StartTask = $false
            ModifyTrigger = $false
        }
    }
    if ($Action -eq "Wake") {
        if (@("READY", "ACTIVE", "INTERRUPTED_RECOVERABLE") -notcontains $Phase) {
            throw "Wake requires phase READY, ACTIVE, or INTERRUPTED_RECOVERABLE; current phase is $Phase."
        }
        return [pscustomobject]@{
            NewPhase = $Phase
            EnableTask = $false
            StartTask = $true
            ModifyTrigger = $false
        }
    }
    if ($Action -eq "ResumeExternal") {
        if ($Phase -ne "WAITING_EXTERNAL") {
            throw "ResumeExternal requires phase WAITING_EXTERNAL; current phase is $Phase."
        }
        if ([string]::IsNullOrWhiteSpace($ThreadId)) {
            throw "ResumeExternal requires an existing exact thread_id."
        }
        return [pscustomobject]@{
            NewPhase = "ACTIVE"
            EnableTask = $true
            StartTask = [bool]$StartNow
            ModifyTrigger = $false
        }
    }
    if ($Action -eq "RecoverInterrupted") {
        if (@("LAUNCHER_ERROR", "LAST_WAKE_FAILED") -notcontains $Phase) {
            throw "RecoverInterrupted requires a legacy interrupted phase; current phase is $Phase."
        }
        if (-not [string]::IsNullOrWhiteSpace($ThreadId)) {
            throw "RecoverInterrupted requires legacy state with an empty thread_id."
        }
        return [pscustomobject]@{
            NewPhase = "INTERRUPTED_RECOVERABLE"
            EnableTask = $true
            StartTask = [bool]$StartNow
            ModifyTrigger = $false
        }
    }
    if ($Phase -ne "LAUNCHER_ERROR") {
        throw "RecoverPreThread requires phase LAUNCHER_ERROR; current phase is $Phase."
    }
    if (-not [string]::IsNullOrWhiteSpace($ThreadId)) {
        throw "RecoverPreThread requires an empty thread_id."
    }
    return [pscustomobject]@{
        NewPhase = "READY"
        EnableTask = $true
        StartTask = [bool]$StartNow
        ModifyTrigger = $false
    }
}

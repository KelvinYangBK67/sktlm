$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:AutomationConfigSchema = "sktlm-codex-automation-config/v1"
$script:AutomationStateSchema = "sktlm-codex-automation/v1"
$script:AutomationPhases = @(
    "READY",
    "RUNNING",
    "ACTIVE",
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
    if ((@("ACTIVE", "WAITING_EXTERNAL", "COMPLETE") -contains [string]$State.phase) -and
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
    if (@("CONTINUE", "WAITING_EXTERNAL", "COMPLETE") -notcontains $status) {
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
        [Parameter(Mandatory = $true)][ValidateSet("Status", "Wake", "ResumeExternal", "RecoverPreThread")][string]$Action,
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
        if (@("READY", "ACTIVE") -notcontains $Phase) {
            throw "Wake requires phase READY or ACTIVE; current phase is $Phase."
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

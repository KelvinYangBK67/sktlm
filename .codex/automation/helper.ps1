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
        "-s",
        "workspace-write",
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
        [Parameter(Mandatory = $true)][ValidateSet("Status", "Wake", "ResumeExternal")][string]$Action,
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

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$SpecPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$HelperPath = Join-Path $PSScriptRoot "helper.ps1"
if (-not (Test-Path -LiteralPath $HelperPath -PathType Leaf)) {
    throw "Framework helper not found: $HelperPath"
}
. $HelperPath

$Spec = Read-AutomationJson -Path ([System.IO.Path]::GetFullPath($SpecPath))
Assert-ObjectProperties -Value $Spec -Label "native invocation spec" -Names @(
    "file_path", "argument_list", "prompt_path", "stdout_path", "stderr_path", "result_path"
)
$Result = [ordered]@{
    schema_version = "sktlm-codex-native-result/v1"
    exit_code = $null
    launcher_error = $null
    completed_at = $null
}

try {
    if (-not (Test-Path -LiteralPath ([string]$Spec.file_path) -PathType Leaf)) {
        throw "Native executable not found: $($Spec.file_path)"
    }
    if (-not (Test-Path -LiteralPath ([string]$Spec.prompt_path) -PathType Leaf)) {
        throw "Invocation prompt not found: $($Spec.prompt_path)"
    }
    $PromptText = [System.IO.File]::ReadAllText([string]$Spec.prompt_path)
    $Arguments = [string[]]$Spec.argument_list
    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $script:LASTEXITCODE = $null
        $PromptText | & ([string]$Spec.file_path) @Arguments 1> ([string]$Spec.stdout_path) 2> ([string]$Spec.stderr_path)
        $NativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }
    if ($null -eq $NativeExitCode) {
        throw "Native process did not report an exit code."
    }
    $Result.exit_code = [int]$NativeExitCode
}
catch {
    $Result.launcher_error = $_.Exception.Message
}

$Result.completed_at = (Get-Date).ToString("o")
Write-AutomationJsonAtomic -Path ([string]$Spec.result_path) -Value $Result
exit 0

# IRIS Antigravity helper: wraps the persistent `agy` CLI.
# Dot-source this file to expose `ia` in the current PowerShell session:
#   . C:\kirtan\IRIS\scripts\iris-agy-profile.ps1

function ia {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$CommandArgs
    )

    $agyCommand = if ($env:AGY_CLI_COMMAND) { $env:AGY_CLI_COMMAND } else { "agy" }
    $resolved = Get-Command $agyCommand -ErrorAction SilentlyContinue
    if (-not $resolved) {
        Write-Error "Antigravity CLI not found ('$agyCommand'). Set AGY_CLI_COMMAND to its executable path."
        return
    }

    $logDir = Join-Path $HOME ".iris"
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    $logPath = Join-Path $logDir "agy_hub.log"
    $joined = ($CommandArgs -join " ").Trim()

    Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format o)] ia $joined"

    if (-not $joined) {
        & $resolved.Source
        return
    }

    if ($joined.StartsWith("/")) {
        & $resolved.Source $joined
        return
    }

    & $resolved.Source -p $joined
}

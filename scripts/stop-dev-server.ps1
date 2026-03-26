param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-server-common.ps1")

$state = Get-ServerState -BindHost $BindHost -Port $Port
$config = $state.Config

$pidToStop = $null
if ($state.PidFromFile -and $state.LauncherProcess) {
    $pidToStop = $state.PidFromFile
} elseif ($state.ListenerProcess) {
    $pidToStop = $state.ListenerProcess.ProcessId
}

if (-not $pidToStop) {
    if ($state.PidFromFile -and -not $state.LauncherProcess) {
        Remove-StalePidFile -Config $config
    }

    Write-Host "Dev server is not running on http://$($config.Address)/"
    exit 0
}

$null = & taskkill /PID $pidToStop /T /F
Start-Sleep -Seconds 1

$remainingState = Get-ServerState -BindHost $BindHost -Port $Port
if ($remainingState.Listener) {
    throw "Tried to stop the dev server, but port $Port is still listening on PID $($remainingState.Listener.OwningProcess)."
}

Remove-StalePidFile -Config $config
Write-Host "Dev server stopped."

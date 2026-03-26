param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-server-common.ps1")

$state = Get-ServerState -BindHost $BindHost -Port $Port
$config = $state.Config

if ($state.IsRunning) {
    Write-Host "Dev server is running at http://$($config.Address)/"

    if ($state.PidFromFile) {
        Write-Host "Launcher PID file: $($state.PidFromFile)"
    }

    if ($state.ListenerProcess) {
        Write-Host "Listener PID: $($state.ListenerProcess.ProcessId)"
        Write-Host "Command: $($state.ListenerProcess.CommandLine)"
    }

    exit 0
}

if ($state.PidFromFile -and -not $state.LauncherProcess) {
    Write-Host "Dev server is not running. Found stale PID file with PID $($state.PidFromFile)."
    exit 1
}

Write-Host "Dev server is not running at http://$($config.Address)/"
exit 1

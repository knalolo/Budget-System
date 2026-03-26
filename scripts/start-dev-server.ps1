param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-server-common.ps1")

$state = Get-ServerState -BindHost $BindHost -Port $Port
$config = $state.Config

if (-not (Test-Path $config.PythonPath)) {
    throw "Virtual environment Python not found at $($config.PythonPath)."
}

if ($state.IsRunning) {
    $pidToShow = if ($state.ListenerProcess) { $state.ListenerProcess.ProcessId } else { $state.PidFromFile }
    Write-Host "Dev server is already running at http://$($config.Address)/ (PID $pidToShow)."
    exit 0
}

if ($state.Listener -and -not $state.ListenerMatchesLauncher) {
    throw "Port $Port is already in use by PID $($state.Listener.OwningProcess). Stop that process before starting the Django dev server."
}

if ($state.PidFromFile -and -not $state.LauncherProcess) {
    Remove-StalePidFile -Config $config
}

$launcher = Start-Process `
    -FilePath $config.PythonPath `
    -ArgumentList "manage.py", "runserver", $config.Address, "--noreload" `
    -WorkingDirectory $config.RepoRoot `
    -RedirectStandardOutput $config.StdOutLog `
    -RedirectStandardError $config.StdErrLog `
    -PassThru

Set-Content -Path $config.PidFile -Value $launcher.Id

$runningState = Wait-ForServer -LauncherPid $launcher.Id -BindHost $BindHost -Port $Port
if (-not $runningState) {
    throw "Dev server did not start listening on http://$($config.Address)/ within the expected time. Check runserver.err.log."
}

$listenerPid = $runningState.ListenerProcess.ProcessId
Write-Host "Dev server started at http://$($config.Address)/"
Write-Host "Launcher PID: $($launcher.Id)"
Write-Host "Listener PID: $listenerPid"

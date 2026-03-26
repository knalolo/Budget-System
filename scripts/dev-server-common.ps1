Set-StrictMode -Version Latest

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-ServerConfig {
    param(
        [string]$BindHost = "127.0.0.1",
        [int]$Port = 8000
    )

    $repoRoot = Get-RepoRoot

    return @{
        RepoRoot = $repoRoot
        Host = $BindHost
        Port = $Port
        Address = "{0}:{1}" -f $BindHost, $Port
        PythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
        PidFile = Join-Path $repoRoot ".runserver.pid"
        StdOutLog = Join-Path $repoRoot "runserver.log"
        StdErrLog = Join-Path $repoRoot "runserver.err.log"
    }
}

function Get-PidFromFile {
    param([hashtable]$Config)

    if (-not (Test-Path $Config.PidFile)) {
        return $null
    }

    $rawValue = (Get-Content $Config.PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($rawValue)) {
        return $null
    }

    $pidValue = 0
    if (-not [int]::TryParse($rawValue.Trim(), [ref]$pidValue)) {
        return $null
    }

    return $pidValue
}

function Get-ProcessInfo {
    param([int]$ProcessId)

    if (-not $ProcessId) {
        return $null
    }

    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Get-ListenerConnection {
    param([hashtable]$Config)

    $connections = Get-NetTCPConnection -LocalPort $Config.Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return $null
    }

    return $connections |
        Where-Object { $_.LocalAddress -eq $Config.Host -or $_.LocalAddress -eq "0.0.0.0" -or $_.LocalAddress -eq "::" } |
        Select-Object -First 1
}

function Remove-StalePidFile {
    param([hashtable]$Config)

    if (Test-Path $Config.PidFile) {
        Remove-Item $Config.PidFile -Force
    }
}

function Get-ServerState {
    param(
        [string]$BindHost = "127.0.0.1",
        [int]$Port = 8000
    )

    $config = Get-ServerConfig -BindHost $BindHost -Port $Port
    $pidFromFile = Get-PidFromFile -Config $config
    $launcher = if ($pidFromFile) { Get-ProcessInfo -ProcessId $pidFromFile } else { $null }
    $listener = Get-ListenerConnection -Config $config
    $listenerProcess = if ($listener) { Get-ProcessInfo -ProcessId $listener.OwningProcess } else { $null }

    $listenerMatchesLauncher = $false
    if ($listenerProcess -and $launcher) {
        $listenerMatchesLauncher = (
            $listenerProcess.ProcessId -eq $launcher.ProcessId -or
            $listenerProcess.ParentProcessId -eq $launcher.ProcessId
        )
    }

    $isRunning = $false
    if ($listenerProcess) {
        if (-not $launcher) {
            $isRunning = $true
        } elseif ($listenerMatchesLauncher) {
            $isRunning = $true
        }
    }

    return @{
        Config = $config
        PidFromFile = $pidFromFile
        LauncherProcess = $launcher
        Listener = $listener
        ListenerProcess = $listenerProcess
        ListenerMatchesLauncher = $listenerMatchesLauncher
        IsRunning = $isRunning
    }
}

function Wait-ForServer {
    param(
        [int]$LauncherPid,
        [string]$BindHost = "127.0.0.1",
        [int]$Port = 8000,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $state = Get-ServerState -BindHost $BindHost -Port $Port
        if ($state.ListenerProcess) {
            if (-not $LauncherPid -or $state.ListenerProcess.ProcessId -eq $LauncherPid -or $state.ListenerProcess.ParentProcessId -eq $LauncherPid) {
                return $state
            }
        }

        Start-Sleep -Milliseconds 500
    }

    return $null
}

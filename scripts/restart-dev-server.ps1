param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop-dev-server.ps1") -BindHost $BindHost -Port $Port
& (Join-Path $PSScriptRoot "start-dev-server.ps1") -BindHost $BindHost -Port $Port

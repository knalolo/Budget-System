$ErrorActionPreference = "SilentlyContinue"

$addresses = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.AddressState -eq "Preferred" -and
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*"
    }

$defaultRouteInterfaces = @(
    Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" |
        Sort-Object RouteMetric |
        Select-Object -ExpandProperty InterfaceIndex
)

$selected = $addresses |
    Sort-Object {
        $routeIndex = [array]::IndexOf($defaultRouteInterfaces, $_.InterfaceIndex)
        if ($routeIndex -ge 0) { $routeIndex } else { 1000 + $_.InterfaceMetric }
    } |
    Select-Object -First 1

if ($selected) {
    Write-Output $selected.IPAddress
} else {
    Write-Output "127.0.0.1"
}

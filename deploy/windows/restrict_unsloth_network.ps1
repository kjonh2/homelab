[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ruleName = 'Iku Unsloth API - restrict private network access'
$blockedRemoteNetworks = @(
    '10.0.0.0/8'
    '172.16.0.0/12'
    '192.168.0.0/16'
    '100.64.0.0/10'
    '169.254.0.0/16'
    'fc00::/7'
    'fe80::/10'
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell session.'
}

Get-NetFirewallRule -PolicyStore PersistentStore -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

$rule = New-NetFirewallRule `
    -PolicyStore PersistentStore `
    -DisplayName $ruleName `
    -Description 'Keep Unsloth Studio port 8888 available to local Drisa only; block private IPv4/IPv6 LAN, link-local, and Tailscale peers.' `
    -Direction Inbound `
    -Action Block `
    -Protocol TCP `
    -LocalPort 8888 `
    -RemoteAddress $blockedRemoteNetworks `
    -Profile Any `
    -EdgeTraversalPolicy Block

if (-not $rule) {
    throw 'Windows Firewall did not return the Unsloth restriction rule.'
}

Write-Output "Installed firewall rule '$ruleName' for TCP/8888 from private, link-local, and Tailscale IPv4/IPv6 ranges."

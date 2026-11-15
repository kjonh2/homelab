param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('normal', 'gaming')]
    [string]$Mode
)

$ErrorActionPreference = 'Stop'
$drisaDir = Join-Path $env:USERPROFILE 'workspace\drisa'
$modeFile = Join-Path $drisaDir 'drisa_mode.txt'
$startScript = Join-Path $drisaDir 'start_drisa.ps1'
$configScript = Join-Path $PSScriptRoot 'drisa_remote_config.ps1'

if (-not (Test-Path -LiteralPath $startScript)) {
    throw "Drisa startup script not found: $startScript"
}
if (-not (Test-Path -LiteralPath $configScript)) {
    throw "Drisa mode configuration not found: $configScript"
}

if ($Mode -eq 'gaming') {
    Set-Content -LiteralPath $modeFile -Value 'gaming' -Encoding ascii
} else {
    Remove-Item -LiteralPath $modeFile -Force -ErrorAction SilentlyContinue
}

Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $startScript
)

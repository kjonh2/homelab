[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:USERPROFILE 'workspace\drisa'),
    [string]$HermesHome = (Join-Path $env:LOCALAPPDATA 'hermes')
)

$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$files = @(
    'audio_processor.py',
    'drisa-status.html',
    'drisa_main.py',
    'drisa_memory.py',
    'drisa_mode.ps1',
    'drisa_remote_config.ps1',
    'drisa_speech_text.py',
    'drisa_tts_sapi.ps1',
    'drisa_voice_gateway.py',
    'drisa_watchdog.ps1',
    'drisa_watchdog_hidden.vbs',
    'install_drisa.ps1',
    'kokoro_tts.py',
    'noise_adaptation.py',
    'register_drisa_watchdog.ps1',
    'requirements-drisa-gateway.txt',
    'requirements-drisa-listener.txt',
    'speech_processor.py',
    'start_drisa.ps1',
    'voice_loop_local.py',
    'wake_word_detector.py'
)

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
foreach ($name in $files) {
    $from = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $from -PathType Leaf)) {
        throw "Required Drisa project file is missing: $from"
    }
    Copy-Item -LiteralPath $from -Destination (Join-Path $Destination $name) -Force
}

$skillSource = Join-Path $source 'skills'
$hermesSkills = Join-Path $HermesHome 'skills'
foreach ($skillName in @('drisa-context-management', 'drisa-docker-mcp')) {
    $skillFile = Join-Path (Join-Path $skillSource $skillName) 'SKILL.md'
    if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
        throw "Drisa skill file is missing: $skillFile"
    }
    $runtimeSkillDir = Join-Path $hermesSkills $skillName
    New-Item -ItemType Directory -Path $runtimeSkillDir -Force | Out-Null
    Copy-Item -LiteralPath $skillFile -Destination (Join-Path $runtimeSkillDir 'SKILL.md') -Force
}

Write-Host "Updated Drisa runtime source at $Destination. Existing credentials and runtime configuration were left in place."
Write-Host "Installed Drisa skills at $hermesSkills."
Write-Host "Install listener dependencies with: `$env:USERPROFILE\workspace\drisa\venv\Scripts\python.exe -m pip install -r `"$source\requirements-drisa-listener.txt`""
Write-Host "Register or refresh logon recovery with: powershell -ExecutionPolicy Bypass -File `"$Destination\register_drisa_watchdog.ps1`""

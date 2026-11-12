$ErrorActionPreference = 'Stop'
$drisaDir = Join-Path $env:USERPROFILE 'workspace\drisa'
$logFile = Join-Path $drisaDir 'startup.log'
$gatewayPidFile = Join-Path $drisaDir 'drisa_gateway.pid'
$voicePidFile = Join-Path $drisaDir 'drisa_voice.pid'
$pythonExe = Join-Path $drisaDir 'venv\Scripts\python.exe'
$gatewayScript = Join-Path $drisaDir 'drisa_voice_gateway.py'
$normalVoiceScript = Join-Path $drisaDir 'drisa_main.py'
$gamingVoiceScript = Join-Path $drisaDir 'voice_loop_local.py'
$modeFile = Join-Path $drisaDir 'drisa_mode.txt'
$modeConfig = Join-Path $PSScriptRoot 'drisa_remote_config.ps1'

if (-not (Test-Path -LiteralPath $modeConfig)) {
    $modeConfig = Join-Path $drisaDir 'drisa_remote_config.ps1'
}
if (Test-Path -LiteralPath $modeConfig) { . $modeConfig }

function Write-DrisaWatchdogLog([string]$Message) {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "[$timestamp] Watchdog: $Message" | Out-File -FilePath $logFile -Encoding utf8 -Append
}

function Get-DrisaProcesses([string]$ScriptPath) {
    Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and
        ([string]$_.CommandLine).IndexOf($ScriptPath, [StringComparison]::OrdinalIgnoreCase) -ge 0
    }
}

function Ensure-DrisaProcess([string]$ScriptPath, [string]$PidFile, [string]$Name) {
    $running = @(Get-DrisaProcesses $ScriptPath)
    if ($Name -eq 'gateway') {
        $listener = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 8765 -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $listener) {
            Write-DrisaWatchdogLog 'gateway process found without its loopback listener; restarting it'
            foreach ($process in $running) {
                Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 2
            $running = @(Get-DrisaProcesses $ScriptPath)
        }
    }

    if ($running.Count -eq 0) {
        $started = Start-Process -FilePath $pythonExe -ArgumentList @($ScriptPath) `
            -WindowStyle Hidden -PassThru -WorkingDirectory $drisaDir
        Set-Content -LiteralPath $PidFile -Value $started.Id -Encoding ascii
        Write-DrisaWatchdogLog "started $Name pid=$($started.Id)"
        return
    }

    $listenerPid = $null
    if ($Name -eq 'gateway') {
        $listener = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 8765 -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) { $listenerPid = $listener.OwningProcess }
    }
    $selected = $running | Where-Object { $_.ProcessId -eq $listenerPid } | Select-Object -First 1
    if (-not $selected) { $selected = $running | Select-Object -First 1 }
    Set-Content -LiteralPath $PidFile -Value $selected.ProcessId -Encoding ascii
}

try {
    $gamingMode = (Test-Path -LiteralPath $modeFile) -and
        ((Get-Content -LiteralPath $modeFile -Raw).Trim().ToLowerInvariant() -eq 'gaming')
    if ($gamingMode) {
        if (Get-Command Stop-DrisaGamingModelServer -ErrorAction SilentlyContinue) {
            Stop-DrisaGamingModelServer
        }
        if (Get-Command Stop-DrisaGamingWorld -ErrorAction SilentlyContinue) {
            Stop-DrisaGamingWorld
        }
    }

    Ensure-DrisaProcess $gatewayScript $gatewayPidFile 'gateway'
    $voiceScript = if ($gamingMode) { $gamingVoiceScript } else { $normalVoiceScript }
    Ensure-DrisaProcess $voiceScript $voicePidFile 'voice listener'
} catch {
    Write-DrisaWatchdogLog "error: $($_.Exception.Message)"
}

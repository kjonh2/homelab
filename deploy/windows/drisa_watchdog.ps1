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

function Set-DrisaRuntimeEnvironment([bool]$GamingMode) {
    $configPath = Join-Path $drisaDir 'gateway_config.json'
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $env:DRISA_HOME = $drisaDir
    $env:DRISA_VAULT_PATH = Join-Path $env:USERPROFILE 'Documents\Obsidian Vault\Drisa\Voice Gateway'
    $env:DRISA_UNSLOTH_URL = if ($config.unsloth_url) { $config.unsloth_url } else { 'http://127.0.0.1:8888/v1' }
    $env:DRISA_AUDIO_URL = if ($config.audio_url) { $config.audio_url } else { 'http://127.0.0.1:8766/v1' }
    $env:DRISA_STT_ENGINE = if ($config.stt_engine) { $config.stt_engine } else { 'api' }
    $env:DRISA_TTS_ENGINE = if ($config.tts_engine) { $config.tts_engine } else { 'api' }
    $env:DRISA_STT_MODEL = if ($config.stt_model) { $config.stt_model } else { 'moss' }
    $env:DRISA_STT_FALLBACK_MODEL = if ($config.fallback_stt_model) { $config.fallback_stt_model } else { 'parakeet' }
    $env:DRISA_STT_URL = if ($config.stt_url) { $config.stt_url } elseif ($config.stt_host -eq 'homelab') { $env:DRISA_AUDIO_URL } else { $env:DRISA_UNSLOTH_URL }
    $env:DRISA_LLM_MODEL = if ($config.llm_model) { $config.llm_model } else { 'AtomicChat/LFM3-1.7B-Uncensored-GGUF' }
    $env:DRISA_LLM_HOST = if ($config.llm_host) { $config.llm_host } else { 'pc' }
    if ($config.llm_url) { $env:DRISA_LLM_URL = $config.llm_url }
    $env:DRISA_TTS_MODEL = if ($config.tts_model) { $config.tts_model } else { 'kokoro' }
    $env:DRISA_TTS_URL = if ($config.tts_url) { $config.tts_url } elseif ($config.tts_host -eq 'homelab') { $env:DRISA_AUDIO_URL } else { $env:DRISA_UNSLOTH_URL }
    $env:DRISA_TTS_VOICE = if ($config.tts_voice) { $config.tts_voice } else { 'pf_dora' }

    $keyPath = Join-Path $drisaDir 'unsloth.key'
    if (Test-Path -LiteralPath $keyPath) {
        $env:DRISA_UNSLOTH_KEY = (Get-Content -LiteralPath $keyPath -Raw).Trim()
    }
    if ($GamingMode -and (Get-Command Set-DrisaGamingEnvironment -ErrorAction SilentlyContinue)) {
        Set-DrisaGamingEnvironment
    }
}

function Write-DrisaWatchdogLog([string]$Message) {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "[$timestamp] Watchdog: $Message" | Out-File -FilePath $logFile -Encoding utf8 -Append
}

function Ensure-DrisaAudioTunnel {
    $listenAddress = '127.0.0.1'
    $listenPort = 8766
    $forward = '127.0.0.1:8766:10.43.200.200:8080'
    $sshTarget = 'kiko@100.72.114.73'
    $sshExe = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
    if (-not (Test-Path -LiteralPath $sshExe)) {
        Write-DrisaWatchdogLog 'audio tunnel skipped: Windows OpenSSH client not found'
        return
    }

    $matching = @(Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { ([string]$_.CommandLine).Contains($forward) -and ([string]$_.CommandLine).Contains($sshTarget) })
    $listener = Get-NetTCPConnection -State Listen -LocalAddress $listenAddress -LocalPort $listenPort -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener -and @($matching | Where-Object { $_.ProcessId -eq $listener.OwningProcess }).Count -gt 0) { return }
    if ($listener) {
        Write-DrisaWatchdogLog "audio tunnel skipped: $listenAddress`:$listenPort is owned by another process"
        return
    }
    if ($matching.Count -gt 0) { return }

    try {
        $started = Start-Process -FilePath $sshExe -ArgumentList @(
            '-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'BatchMode=yes',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
            '-L', $forward, $sshTarget
        ) -WindowStyle Hidden -PassThru
        Start-Sleep -Milliseconds 800
        $listener = Get-NetTCPConnection -State Listen -LocalAddress $listenAddress -LocalPort $listenPort -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener -and $listener.OwningProcess -eq $started.Id) {
            Write-DrisaWatchdogLog "audio tunnel active pid=$($started.Id) on $listenAddress`:$listenPort"
        } else {
            Write-DrisaWatchdogLog "audio tunnel failed to start (ssh pid=$($started.Id), exit=$($started.ExitCode))"
        }
    } catch {
        Write-DrisaWatchdogLog "audio tunnel error: $($_.Exception.Message)"
    }
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
    Set-DrisaRuntimeEnvironment $gamingMode
    if ($gamingMode) {
        if (Get-Command Stop-DrisaGamingModelServer -ErrorAction SilentlyContinue) {
            Stop-DrisaGamingModelServer
        }
        if (Get-Command Stop-DrisaGamingWorld -ErrorAction SilentlyContinue) {
            Stop-DrisaGamingWorld
        }
    }

    if ($gamingMode -or $env:DRISA_STT_URL -eq $env:DRISA_AUDIO_URL -or $env:DRISA_TTS_URL -eq $env:DRISA_AUDIO_URL) {
        Ensure-DrisaAudioTunnel
    }

    Ensure-DrisaProcess $gatewayScript $gatewayPidFile 'gateway'
    $voiceScript = if ($gamingMode) { $gamingVoiceScript } else { $normalVoiceScript }
    Ensure-DrisaProcess $voiceScript $voicePidFile 'voice listener'
} catch {
    Write-DrisaWatchdogLog "error: $($_.Exception.Message)"
}

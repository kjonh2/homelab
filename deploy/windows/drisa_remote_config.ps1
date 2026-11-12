function Set-DrisaGamingEnvironment {
    $env:DRISA_STT_ENGINE = 'api'
    $env:DRISA_STT_MODEL = 'moss'
    $env:DRISA_STT_FALLBACK_MODEL = 'parakeet'
    $env:DRISA_STT_URL = $env:DRISA_AUDIO_URL
    $env:DRISA_TTS_ENGINE = 'api'
    $env:DRISA_TTS_MODEL = 'kokoro'
    $env:DRISA_TTS_URL = $env:DRISA_AUDIO_URL
    $env:DRISA_TTS_VOICE = 'pf_dora'
    $env:DRISA_LLM_URL = 'https://vps-4e5174e4.tail2931da.ts.net:8445/v1'
    $env:DRISA_LLM_HOST = 'vps'
    # Gaming mode changes where inference runs, not which text model is selected.
    Remove-Item Env:DRISA_LLM_MODEL -ErrorAction SilentlyContinue
}

function Get-DrisaGamingModelServerProcesses {
    $unslothRoot = Join-Path $env:USERPROFILE '.unsloth'
    $processes = @(Get-CimInstance Win32_Process)
    $serverIds = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($process in $processes) {
        $path = [string]$process.ExecutablePath
        $insideUnsloth = $path.StartsWith($unslothRoot + '\', [StringComparison]::OrdinalIgnoreCase)
        if ($insideUnsloth -and ([string]$process.Name) -match '^(?i:unsloth|llama-server|python)\.exe$') {
            [void]$serverIds.Add([int]$process.ProcessId)
        }
    }
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($process in $processes) {
            if ($serverIds.Contains([int]$process.ParentProcessId) -and
                $serverIds.Add([int]$process.ProcessId)) {
                $changed = $true
            }
        }
    }
    $processes | Where-Object { $serverIds.Contains([int]$_.ProcessId) }
}

function Stop-DrisaGamingModelServer {
    Get-DrisaGamingModelServerProcesses | ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
    }
    Start-Sleep -Milliseconds 500
    Get-DrisaGamingModelServerProcesses | ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
    }
}

function Stop-DrisaGamingWorld {
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match '(?i)drisa_main\.py|drisa_world\.exe'
    } | ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
    }
}

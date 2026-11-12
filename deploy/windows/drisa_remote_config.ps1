function Set-DrisaGamingEnvironment {
    $env:DRISA_STT_ENGINE = 'local'
    $env:DRISA_STT_FALLBACK = 'local'
    $env:DRISA_TTS_ENGINE = 'sapi'
    $env:DRISA_LLM_URL = 'https://vps-4e5174e4.tail2931da.ts.net:8445/v1'
    $env:DRISA_LLM_HOST = 'vps'
    # Gaming mode changes where inference runs, not which text model is selected.
    Remove-Item Env:DRISA_LLM_MODEL -ErrorAction SilentlyContinue
}

function Get-DrisaGamingModelServerProcesses {
    $unslothRoot = Join-Path $env:USERPROFILE '.unsloth'
    Get-CimInstance Win32_Process | Where-Object {
        $name = [string]$_.Name
        $path = [string]$_.ExecutablePath
        $insideUnsloth = $path.StartsWith($unslothRoot + '\', [StringComparison]::OrdinalIgnoreCase)
        $insideUnsloth -and $name -match '^(?i:unsloth|llama-server)\.exe$'
    }
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

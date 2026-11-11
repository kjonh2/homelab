function Set-DrisaGamingEnvironment {
    $env:DRISA_STT_ENGINE = 'local'
    $env:DRISA_STT_FALLBACK = 'local'
    $env:DRISA_TTS_ENGINE = 'sapi'
    $env:DRISA_LLM_URL = 'https://vps-4e5174e4.tail2931da.ts.net:8445/v1'
    $env:DRISA_LLM_HOST = 'vps'
    # The llama.cpp router exposes model IDs, not the backing GGUF file path.
    $env:DRISA_LLM_MODEL = 'lfm3-omni'
}

function Stop-DrisaGamingModelServer {
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match '(?i)unsloth.*studio|studio.*8888'
    } | ForEach-Object {
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

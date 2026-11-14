$ErrorActionPreference = 'Stop'

$variables = @(
    'DRISA_LLM_MODEL', 'DRISA_AUDIO_URL', 'DRISA_STT_ENGINE', 'DRISA_STT_MODEL',
    'DRISA_STT_FALLBACK_MODEL', 'DRISA_STT_URL', 'DRISA_TTS_ENGINE', 'DRISA_TTS_MODEL',
    'DRISA_TTS_URL', 'DRISA_TTS_VOICE', 'DRISA_LLM_URL', 'DRISA_LLM_HOST'
)
$original = @{}
foreach ($name in $variables) {
    $original[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    $env:DRISA_LLM_MODEL = 'lfm3-uncensored'
    $env:DRISA_AUDIO_URL = 'http://127.0.0.1:8766/v1'
    . (Join-Path $PSScriptRoot 'drisa_remote_config.ps1')
    Set-DrisaGamingEnvironment

    $expected = @{
        DRISA_LLM_MODEL = 'lfm3-uncensored'
        DRISA_STT_ENGINE = 'api'
        DRISA_STT_MODEL = 'moss'
        DRISA_STT_FALLBACK_MODEL = 'parakeet'
        DRISA_STT_URL = 'http://127.0.0.1:8766/v1'
        DRISA_TTS_ENGINE = 'api'
        DRISA_TTS_MODEL = 'kokoro'
        DRISA_TTS_URL = 'http://127.0.0.1:8766/v1'
        DRISA_TTS_VOICE = 'pf_dora'
        DRISA_LLM_URL = 'https://vps-4e5174e4.tail2931da.ts.net:8445/v1'
        DRISA_LLM_HOST = 'vps'
    }
    foreach ($name in $expected.Keys) {
        $actual = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ($actual -cne $expected[$name]) {
            throw "Gaming environment assertion failed for $name."
        }
    }
    Write-Output 'Gaming environment routing: PASS'
} finally {
    foreach ($name in $variables) {
        [Environment]::SetEnvironmentVariable($name, $original[$name], 'Process')
    }
}

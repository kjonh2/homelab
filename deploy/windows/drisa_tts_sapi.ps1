param(
    [Parameter(Mandatory = $true)][string]$TextFile,
    [string]$WaveFile
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voice = $synth.GetInstalledVoices() |
        Where-Object { $_.VoiceInfo.Culture.Name -eq 'pt-PT' } |
        Select-Object -First 1
    if ($voice) { $synth.SelectVoice($voice.VoiceInfo.Name) }
    $text = [System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8)
    if ([string]::IsNullOrWhiteSpace($text)) { exit 0 }
    if ($WaveFile) {
        $synth.SetOutputToWaveFile($WaveFile)
        $synth.Speak($text)
        $synth.SetOutputToNull()
    } else {
        $synth.SetOutputToDefaultAudioDevice()
        $synth.Speak($text)
    }
} finally {
    $synth.Dispose()
}

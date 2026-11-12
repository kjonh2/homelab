$ErrorActionPreference = 'Stop'
$drisaDir = Join-Path $env:USERPROFILE 'workspace\drisa'
$modeFile = Join-Path $drisaDir 'drisa_mode.txt'
$configScript = Join-Path $drisaDir 'drisa_remote_config.ps1'
$logFile = Join-Path $drisaDir 'startup.log'
$gamingMode = (Test-Path -LiteralPath $modeFile) -and
    ((Get-Content -LiteralPath $modeFile -Raw).Trim().ToLowerInvariant() -eq 'gaming')

if (Test-Path -LiteralPath $configScript) { . $configScript }

function Write-DrisaLog([string]$Message) {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" |
        Out-File -LiteralPath $logFile -Encoding utf8 -Append
}

# Stop only Drisa-owned listeners and the optional world before changing modes.
Get-CimInstance Win32_Process | Where-Object {
    $command = [string]$_.CommandLine
    $command -match '(?i)drisa_voice_gateway\.py|drisa_main\.py|voice_loop_local\.py' -or
        ([string]$_.Name -ieq 'drisa_world.exe' -and $command.Contains($drisaDir))
} | ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
}

if ($gamingMode) {
    if (Get-Command Stop-DrisaGamingModelServer -ErrorAction SilentlyContinue) {
        Stop-DrisaGamingModelServer
    }
    if (Get-Command Stop-DrisaGamingWorld -ErrorAction SilentlyContinue) {
        Stop-DrisaGamingWorld
    }
    Write-DrisaLog 'Gaming mode selected; local model server and world stopped.'
} else {
    $modelProcesses = @()
    if (Get-Command Get-DrisaGamingModelServerProcesses -ErrorAction SilentlyContinue) {
        $modelProcesses = @(Get-DrisaGamingModelServerProcesses)
    }
    if ($modelProcesses.Count -gt 0) {
        Write-DrisaLog 'Normal mode selected; existing local model server left running.'
    } else {
        $unsloth = Get-Command unsloth -ErrorAction SilentlyContinue
        if (-not $unsloth) { $unsloth = Get-Command unsloth.cmd -ErrorAction SilentlyContinue }
        if ($unsloth) {
            Start-Process -FilePath $unsloth.Source -ArgumentList @('studio', '-p', '8888') -WindowStyle Hidden
            Write-DrisaLog 'Normal mode selected; Unsloth model server launch requested.'
        } else {
            Write-DrisaLog 'Normal mode selected; Unsloth command not found, model server was not started.'
        }
    }

    $world = Join-Path $drisaDir 'cpp_src\build\drisa_world.exe'
    if (Test-Path -LiteralPath $world) {
        Start-Process -FilePath $world -WorkingDirectory $drisaDir
        Write-DrisaLog 'Drisa world started.'
    }
}

Start-Sleep -Seconds 2
& (Join-Path $drisaDir 'drisa_watchdog.ps1')

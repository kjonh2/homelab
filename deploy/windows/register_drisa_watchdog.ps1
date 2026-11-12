$ErrorActionPreference = 'Stop'
$taskName = 'Drisa Watchdog'
$drisaDir = Join-Path $env:USERPROFILE 'workspace\drisa'
$script = Join-Path $drisaDir 'drisa_watchdog.ps1'

if (-not (Test-Path -LiteralPath $script)) {
    throw "Drisa watchdog script not found: $script"
}

$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$repeatTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$repeatTrigger.Repetition.StopAtDurationEnd = $false
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
    '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $script + '"'
) -WorkingDirectory $drisaDir
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($logonTrigger, $repeatTrigger) `
    -Settings $settings -Principal $principal -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State, @{n='Execute';e={$_.Actions.Execute}},
    @{n='Arguments';e={$_.Actions.Arguments}} | ConvertTo-Json -Compress

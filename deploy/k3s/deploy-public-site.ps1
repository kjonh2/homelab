param(
    [string]$VpsHost = 'ubuntu@vps-4e5174e4',
    [string]$TunnelTokenFile,
    [switch]$BuildOnly
)

$ErrorActionPreference = 'Stop'
if ($VpsHost -notmatch '^[A-Za-z0-9@._:-]+$') {
    throw 'VpsHost must be a plain Tailscale SSH destination such as ubuntu@vps-4e5174e4.'
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$siteDir = Join-Path $repoRoot 'public-site'
$distDir = Join-Path $siteDir 'dist'
$tailscaleExe = (Get-Command tailscale.exe -ErrorAction Stop).Source

Push-Location $siteDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Public site build failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$distFiles = @(Get-ChildItem -LiteralPath $distDir -File -Recurse)
if ($distFiles.Count -eq 0) { throw 'Vite produced no files in public-site/dist.' }
if (@(Get-ChildItem -LiteralPath $distDir -Directory -Recurse).Count -ne 0) {
    throw 'The public site deployment expects flat dist output; check vite.config.ts assetsDir.'
}

$data = [ordered]@{}
$byteCount = 0
foreach ($file in $distFiles) {
    $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
    $data[$file.Name] = $content
    $byteCount += [System.Text.Encoding]::UTF8.GetByteCount($content)
}
if ($byteCount -gt 900000) { throw "Static output is $byteCount bytes; it is too large for a Kubernetes ConfigMap." }

$configMap = @{
    apiVersion = 'v1'
    kind = 'ConfigMap'
    metadata = @{
        name = 'iku-public-site'
        namespace = 'iku'
        labels = @{
            'app.kubernetes.io/name' = 'iku-public-site'
            'app.kubernetes.io/part-of' = 'iku'
        }
    }
    data = $data
} | ConvertTo-Json -Depth 8 -Compress

function Get-TunnelToken {
    $tokenPath = $TunnelTokenFile
    if ([string]::IsNullOrWhiteSpace($tokenPath)) {
        $tokenPath = Join-Path $env:USERPROFILE 'workspace\drisa\cloudflare_tunnel_token_vps.txt'
    }
    $resolvedTokenPath = (Resolve-Path -LiteralPath $tokenPath -ErrorAction Stop).Path
    return ([System.IO.File]::ReadAllText($resolvedTokenPath, [System.Text.Encoding]::UTF8)).Trim()
}

function Invoke-RemoteKubectlApplyText {
    param([Parameter(Mandatory)][string]$Content)

    $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $tailscaleExe
    # Use Arguments instead of ArgumentList so this also works in Windows PowerShell 5.1.
    $processInfo.Arguments = 'ssh "{0}" "{1}"' -f $VpsHost, 'sudo -n k3s kubectl apply -f -'
    $processInfo.RedirectStandardInput = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    foreach ($encodingSetting in @(
        @{ Name = 'StandardOutputEncoding'; Value = $utf8 },
        @{ Name = 'StandardErrorEncoding'; Value = $utf8 }
    )) {
        $property = $processInfo.GetType().GetProperty($encodingSetting.Name)
        if ($property) { $property.SetValue($processInfo, $encodingSetting.Value, $null) }
    }
    $processInfo.UseShellExecute = $false

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $processInfo
    [void]$process.Start()
    $stdoutReader = $process.StandardOutput
    $stderrReader = $process.StandardError
    $stdoutTask = $stdoutReader.ReadLineAsync()
    $stderrTask = $stderrReader.ReadLineAsync()
    $inputBytes = $utf8.GetBytes($Content)
    $inputStream = $process.StandardInput.BaseStream
    $inputTask = $inputStream.WriteAsync($inputBytes, 0, $inputBytes.Length)
    $inputClosed = $false

    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    while (-not $process.HasExited) {
        if (-not $inputClosed -and $inputTask.IsCompleted) {
            try { $inputTask.GetAwaiter().GetResult() } catch {}
            $process.StandardInput.Close()
            $inputClosed = $true
        }
        if ($stdoutTask.IsCompleted) {
            $line = $stdoutTask.GetAwaiter().GetResult()
            if ($null -ne $line) {
                Write-Output $line
                $stdoutTask = $stdoutReader.ReadLineAsync()
            }
        }
        if ($stderrTask.IsCompleted) {
            $line = $stderrTask.GetAwaiter().GetResult()
            if ($null -ne $line) {
                [Console]::Error.WriteLine($line)
                $stderrTask = $stderrReader.ReadLineAsync()
            }
        }
        if ([DateTime]::UtcNow -ge $deadline) {
            try { $process.Kill() } catch {}
            throw 'Remote kubectl apply timed out after five minutes.'
        }
        Start-Sleep -Milliseconds 100
    }

    $process.WaitForExit()
    if (-not $inputClosed) {
        try { $inputTask.GetAwaiter().GetResult() } catch {}
        try { $process.StandardInput.Close() } catch {}
    }
    foreach ($readerState in @(
        @{ Reader = $stdoutReader; Task = $stdoutTask; IsError = $false },
        @{ Reader = $stderrReader; Task = $stderrTask; IsError = $true }
    )) {
        $line = $readerState.Task.GetAwaiter().GetResult()
        while ($null -ne $line) {
            if ($readerState.IsError) { [Console]::Error.WriteLine($line) }
            else { Write-Output $line }
            $line = $readerState.Reader.ReadLineAsync().GetAwaiter().GetResult()
        }
    }
    if ($process.ExitCode -ne 0) { throw "Remote kubectl apply failed with exit code $($process.ExitCode)." }
}

if ($BuildOnly) {
    Write-Output "Built $($distFiles.Count) static files ($byteCount UTF-8 bytes)."
    return
}

$tunnelToken = Get-TunnelToken
if ([string]::IsNullOrWhiteSpace($tunnelToken)) { throw 'The Cloudflare Tunnel token file is empty.' }

$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ('iku-public-site-' + [guid]::NewGuid().ToString('N'))
[System.IO.Directory]::CreateDirectory($workDir) | Out-Null
$configMapPath = Join-Path $workDir 'configmap.json'
$deploymentPath = Join-Path $workDir 'deployment.yaml'
[System.IO.File]::WriteAllText($configMapPath, $configMap, [System.Text.UTF8Encoding]::new($false))
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'public-site.yaml') -Destination $deploymentPath

function Invoke-RemoteKubectlApply {
    param([Parameter(Mandatory)][string]$ManifestPath)
    $content = [System.IO.File]::ReadAllText($ManifestPath, [System.Text.Encoding]::UTF8)
    Invoke-RemoteKubectlApplyText -Content $content
}

try {
    Invoke-RemoteKubectlApply -ManifestPath $configMapPath
    $secretJson = @{
        apiVersion = 'v1'
        kind = 'Secret'
        metadata = @{
            name = 'iku-public-site-tunnel-token'
            namespace = 'iku'
            labels = @{
                'app.kubernetes.io/name' = 'iku-public-site'
                'app.kubernetes.io/part-of' = 'iku'
            }
        }
        type = 'Opaque'
        data = @{ token = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($tunnelToken)) }
    } | ConvertTo-Json -Depth 8 -Compress
    Invoke-RemoteKubectlApplyText -Content $secretJson
    Remove-Variable secretJson -ErrorAction SilentlyContinue
    Invoke-RemoteKubectlApply -ManifestPath $deploymentPath
    $verifyCommand = "sudo -n k3s kubectl -n iku rollout status deployment/iku-public-site --timeout=180s && pod_ip=`$(sudo -n k3s kubectl -n iku get pod -l app.kubernetes.io/name=iku-public-site -o jsonpath='{.items[0].status.podIP}') && curl -fsS -H 'Host: iknowu.org' http://`$pod_ip:80/ | head -c 200"
    & $tailscaleExe ssh $VpsHost $verifyCommand
    if ($LASTEXITCODE -ne 0) { throw "VPS rollout or loopback HTTP verification failed with exit code $LASTEXITCODE." }
} finally {
    Remove-Variable tunnelToken,secretJson -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
}

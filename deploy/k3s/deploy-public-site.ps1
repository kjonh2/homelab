param(
    [string]$VpsHost = 'ubuntu@vps-4e5174e4',
    [string]$TunnelTokenFile,
    [switch]$BuildOnly
)

$ErrorActionPreference = 'Stop'
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
    if (-not $TunnelTokenFile) { throw 'Pass -TunnelTokenFile with the existing Cloudflare Tunnel connector token.' }
    $resolvedTokenPath = (Resolve-Path -LiteralPath $TunnelTokenFile -ErrorAction Stop).Path
    return ([System.IO.File]::ReadAllText($resolvedTokenPath, [System.Text.Encoding]::UTF8)).Trim()
}

function Invoke-RemoteKubectlApplyText {
    param([Parameter(Mandatory)][string]$Content)

    $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $tailscaleExe
    [void]$processInfo.ArgumentList.Add('ssh')
    [void]$processInfo.ArgumentList.Add($VpsHost)
    [void]$processInfo.ArgumentList.Add('sudo -n k3s kubectl apply -f -')
    $processInfo.RedirectStandardInput = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.StandardInputEncoding = [System.Text.UTF8Encoding]::new($false)
    $processInfo.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $processInfo.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)
    $processInfo.UseShellExecute = $false

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $processInfo
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.Write($Content)
    $process.StandardInput.Close()
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    if ($stdout) { Write-Output $stdout.TrimEnd() }
    if ($stderr) { Write-Error $stderr.TrimEnd() -ErrorAction Continue }
    if ($process.ExitCode -ne 0) { throw "Remote kubectl apply failed with exit code $($process.ExitCode)." }
}

if ($BuildOnly) {
    Write-Output "Built $($distFiles.Count) static files ($byteCount UTF-8 bytes)."
    return
}

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
    $tunnelToken = Get-TunnelToken
    if ([string]::IsNullOrWhiteSpace($tunnelToken)) { throw 'The Cloudflared tunnel token is empty.' }
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
    Remove-Variable tunnelToken,secretJson -ErrorAction SilentlyContinue
    Invoke-RemoteKubectlApply -ManifestPath $deploymentPath
    $verifyCommand = "sudo -n k3s kubectl -n iku rollout status deployment/iku-public-site --timeout=180s && pod_ip=`$(sudo -n k3s kubectl -n iku get pod -l app.kubernetes.io/name=iku-public-site -o jsonpath='{.items[0].status.podIP}') && curl -fsS -H 'Host: iknowu.org' http://`$pod_ip:80/ | head -c 200"
    & $tailscaleExe ssh $VpsHost $verifyCommand
    if ($LASTEXITCODE -ne 0) { throw "VPS rollout or loopback HTTP verification failed with exit code $LASTEXITCODE." }
} finally {
    Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
}

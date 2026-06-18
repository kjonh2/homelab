# ============================================================================
# HOMELAB — Windows Installer (PowerShell)
# Run in PowerShell as Administrator:
#
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   iwr https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/windows-install.ps1 | iex
# ============================================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         HOMELAB — Windows Installer            ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Check Docker ─────────────────────────────────────────────────────────────

Write-Host "[i] Checking Docker..." -ForegroundColor Cyan

try {
    $dockerVersion = docker --version 2>$null
    Write-Host "[✓] Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "[!] Docker not found." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Please install Docker Desktop first:"
    Write-Host "    https://www.docker.com/products/docker-desktop/"
    Write-Host ""
    Write-Host "  After installing, restart this script."
    Start-Process "https://www.docker.com/products/docker-desktop/"
    exit 1
}

try {
    $composeVersion = docker compose version 2>$null
    Write-Host "[✓] Docker Compose found" -ForegroundColor Green
} catch {
    Write-Host "[✗] Docker Compose plugin not found. Update Docker Desktop." -ForegroundColor Red
    exit 1
}

# ── Clone repo ───────────────────────────────────────────────────────────────

$installDir = "$env:USERPROFILE\homelab"

if (Test-Path "$installDir\.git") {
    Write-Host "[i] Updating existing installation..." -ForegroundColor Cyan
    Set-Location $installDir
    git pull origin main 2>$null
    Write-Host "[✓] Repo updated" -ForegroundColor Green
} else {
    Write-Host "[i] Cloning repo to $installDir..." -ForegroundColor Cyan
    if (Get-Command git -ErrorAction SilentlyContinue) {
        git clone https://github.com/kjonh2/homelab.git $installDir
    } else {
        Write-Host "[!] Git not found, downloading zip..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri "https://github.com/kjonh2/homelab/archive/refs/heads/main.zip" -OutFile "$env:TEMP\homelab.zip"
        Expand-Archive -Path "$env:TEMP\homelab.zip" -DestinationPath "$env:TEMP\" -Force
        Move-Item "$env:TEMP\homelab-main" $installDir
        Remove-Item "$env:TEMP\homelab.zip" -Force
    }
    Write-Host "[✓] Repo ready" -ForegroundColor Green
}

Set-Location $installDir

# ── Ask for domain ───────────────────────────────────────────────────────────

Write-Host ""
Write-Host "━━━ Configuration ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

$domain = Read-Host "  → Domain name [example.com]"
if ([string]::IsNullOrWhiteSpace($domain)) { $domain = "example.com" }

# ── Generate .env ────────────────────────────────────────────────────────────

if (-not (Test-Path ".env")) {
    $postgresPass = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $mongoPass = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $redisPass = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $grafanaPass = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })

    Copy-Item .env.example .env
    (Get-Content .env) -replace "DOMAIN=.*", "DOMAIN=$domain" | Set-Content .env
    (Get-Content .env) -replace "POSTGRES_PASSWORD=.*", "POS...}" | Set-Content .env
    (Get-Content .env) -replace "MONGO_PASSWORD=*** .env
    (Get-Content .env) -replace "REDIS_PASSWORD=*** .env
    (Get-Content .env) -replace "GRAFANA_ADMIN_PASSWORD=*** .env

    Write-Host "[✓] .env created with random passwords" -ForegroundColor Green
} else {
    Write-Host "[✓] .env already exists — keeping your settings" -ForegroundColor Green
}

# ── Create network and start ─────────────────────────────────────────────────

docker network create homelab 2>$null | Out-Null

Write-Host "[i] Starting services..." -ForegroundColor Cyan
docker compose -f docker-compose.homelab.yml up -d

# ── Summary ──────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║              INSTALLATION COMPLETE               ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Services running:" -ForegroundColor Green
Write-Host "    Hermes AI      → http://localhost:8787"
Write-Host "    Grafana        → http://localhost:3000"
Write-Host "    Prometheus     → http://localhost:9090"
Write-Host "    N8N            → http://localhost:5678"
Write-Host ""
Write-Host "  To stop:" -ForegroundColor Yellow
Write-Host "    docker compose -f $installDir\docker-compose.homelab.yml down"
Write-Host ""
Write-Host "  To start:" -ForegroundColor Yellow
Write-Host "    docker compose -f $installDir\docker-compose.homelab.yml up -d"
Write-Host ""

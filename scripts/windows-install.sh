#!/bin/bash
# ============================================================================
# HOMELAB — Windows Install (Docker Desktop)
# Run in PowerShell as Administrator:
#
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   iwr https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/windows-install.ps1 | iex
# ============================================================================

# This script is designed to be piped from curl into bash via Git Bash or WSL
# on Windows. It installs Docker Desktop if needed, then runs the standard setup.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         HOMELAB — Windows Installer            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Detect environment ──────────────────────────────────────────────────────

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    PLATFORM="windows"
elif [[ -f /proc/version && $(cat /proc/version) == *"Microsoft"* ]]; then
    PLATFORM="wsl"
else
    PLATFORM="linux"
fi

log "Detected platform: $PLATFORM"

# ── Check Docker ─────────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    warn "Docker not found."
    echo ""
    echo "  Please install Docker Desktop first:"
    echo "    https://www.docker.com/products/docker-desktop/"
    echo ""
    echo "  After installing, restart this script."
    echo ""

    if [[ "$PLATFORM" == "windows" ]]; then
        # Try to open Docker download page
        start https://www.docker.com/products/docker-desktop/ 2>/dev/null || true
    fi

    exit 1
fi

log "Docker found: $(docker --version)"

if ! docker compose version &>/dev/null 2>&1; then
    err "Docker Compose plugin not found."
    echo "  Update Docker Desktop to the latest version."
    exit 1
fi

log "Docker Compose found: $(docker compose version)"

# ── Clone repo ───────────────────────────────────────────────────────────────

INSTALL_DIR="$HOME/homelab"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || warn "Could not update (offline?)"
    log "Repo updated"
else
    info "Cloning repo..."
    git clone https://github.com/klonaw/homelab.git "$INSTALL_DIR" 2>/dev/null || {
        # Fallback: download zip
        warn "Git clone failed, downloading zip..."
        curl -fsSL "https://github.com/kjonh2/homelab/archive/refs/heads/main.zip" -o /tmp/homelab.zip
        unzip -q /tmp/homelab.zip -d /tmp/
        mv /tmp/homelab-main "$INSTALL_DIR"
        rm -f /tmp/homelab.zip
    }
    log "Repo ready at $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Ask for domain ───────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}━━━ Configuration ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

read -rp "  → Domain name [example.com]: " DOMAIN
DOMAIN="${DOMAIN:-example.com}"

# ── Generate .env ─────────────────────────────────────────────────────────────

if [[ ! -f .env ]]; then
    POSTGRES_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)
    MONGO_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)
    REDIS_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)
    GRAFANA_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)

    cp .env.example .env
    sed -i "s|DOMAIN=.*|DOMAIN=${DOMAIN}|" .env
    sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASS}|" .env
    sed -i "s|MONGO_PASSWORD=.*|MONGO_PASSWORD=${MONGO_PASS}|" .env
    sed -i "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASS}|" .env
    sed -i "s|GRAFANA_ADMIN_PASSWORD=.*|GRAFANA_ADMIN_PASSWORD=${GRAFANA_PASS}|" .env

    log ".env created with random passwords"
else
    log ".env already exists — keeping your settings"
fi

# ── Create network and start ─────────────────────────────────────────────────

docker network create homelab &>/dev/null || true

info "Starting services..."
docker compose -f docker-compose.homelab.yml up -d

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              INSTALLATION COMPLETE               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}Services running:${NC}"
echo -e "    Hermes AI      → http://localhost:8787"
echo -e "    Grafana        → http://localhost:3000"
echo -e "    Prometheus     → http://localhost:9090"
echo -e "    N8N            → http://localhost:5678"
echo ""
echo -e "  ${YELLOW}To stop:${NC}  docker compose -f $INSTALL_DIR/docker-compose.homelab.yml down"
echo -e "  ${YELLOW}To start:${NC} docker compose -f $INSTALL_DIR/docker-compose.homelab.yml up -d"
echo ""

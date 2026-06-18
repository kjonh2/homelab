#!/bin/bash
# ============================================================================
# HOMELAB — Proxmox LXC Install
# Run this inside a Debian/Ubuntu LXC container on Proxmox:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/proxmox-install.sh)
#
# Or manually:
#   git clone https://github.com/kjonh2/homelab.git /opt/homelab
#   cd /opt/homelab
#   bash scripts/proxmox-install.sh
# ============================================================================

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
echo -e "${CYAN}║       HOMELAB — Proxmox LXC Installer          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Check root ───────────────────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash $0"
    exit 1
fi

# ── Check if running inside LXC ──────────────────────────────────────────────

if [[ -f /proc/1/environ ]] && grep -q "container=lxc" /proc/1/environ 2>/dev/null; then
    log "Running inside LXC container"
else
    warn "Not detected as LXC — continuing anyway"
fi

# ── Install Docker ───────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    info "Installing Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    log "Docker installed: $(docker --version)"
else
    log "Docker already installed: $(docker --version)"
fi

if ! docker compose version &>/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin
    log "Docker Compose installed"
fi

# ── Clone repo ───────────────────────────────────────────────────────────────

INSTALL_DIR="/opt/homelab"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main
    log "Repo updated"
else
    info "Cloning repo to $INSTALL_DIR..."
    apt-get install -y -qq git
    git clone https://github.com/kjonh2/homelab.git "$INSTALL_DIR"
    log "Repo cloned"
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
    sed -i "s|POSTGRES_PASSWORD=.*|POS...}|" .env
    sed -i "s|MONGO_PASSWORD=.*|MON...}|" .env
    sed -i "s|REDIS_PASSWORD=.*|RED...}|" .env
    sed -i "s|GRAFANA_ADMIN_PASSWORD=.*|GRA...}|" .env

    log ".env created with random passwords"
    warn "Passwords saved in .env — keep it safe!"
else
    log ".env already exists — keeping your settings"
fi

# ── Create network and start ─────────────────────────────────────────────────

docker network create homelab &>/dev/null || true

info "Starting services..."
docker compose -f docker-compose.homelab.yml up -d

# ── Wait for healthchecks ────────────────────────────────────────────────────

echo ""
info "Waiting for services to become healthy..."

for svc in postgresql mongodb redis hermes-agent grafana prometheus n8n; do
    CONTAINER="homelab-${svc}"
    WAITED=0
    while [[ $WAITED -lt 60 ]]; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "starting")
        if [[ "$STATUS" == "healthy" ]]; then
            log "$svc is healthy"
            break
        fi
        sleep 5
        WAITED=$((WAITED + 5))
    done
    if [[ $WAITED -ge 60 ]]; then
        warn "$svc did not become healthy — check: docker logs $CONTAINER"
    fi
done

# ── Get IP ───────────────────────────────────────────────────────────────────

IP=$(ip route get 1 | awk '{print $7; exit}')

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              INSTALLATION COMPLETE               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}Services running on this LXC (${IP}):${NC}"
echo -e "    Hermes AI      → http://${IP}:8787"
echo -e "    Grafana        → http://${IP}:3000"
echo -e "    Prometheus     → http://${IP}:9090"
echo -e "    N8N            → http://${IP}:5678"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "    1. Add proxy hosts in NPM → point to ${IP}"
echo -e "    2. View logs: docker compose -f /opt/homelab/docker-compose.homelab.yml logs -f"
echo -e "    3. Edit config: nano /opt/homelab/.env"
echo ""

#!/bin/bash
# ============================================================================
# HOMELAB — One-command installer
# Run this on a fresh Debian/Ubuntu VM or LXC on Proxmox:
#
#   curl -fsSL https://raw.githubusercontent.com/kjonh2/homelab/main/install.sh | bash
#
# Or manually:
#   git clone https://github.com/kjonh2/homelab.git /opt/homelab
#   cd /opt/homelab
#   bash install.sh
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
echo -e "${CYAN}║         HOMELAB — One-command Installer          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Check prerequisites ──────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash install.sh"
    exit 1
fi

if ! command -v docker &>/dev/null; then
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    log "Docker installed: $(docker --version)"
else
    log "Docker already installed: $(docker --version)"
fi

if ! docker compose version &>/dev/null 2>&1; then
    info "Installing Docker Compose plugin..."
    apt-get update -qq
    apt-get install -y -qq docker-compose-plugin
    log "Docker Compose installed: $(docker compose version)"
else
    log "Docker Compose already installed: $(docker compose version)"
fi

# ── 2. Clone or update repo ─────────────────────────────────────────────────

INSTALL_DIR="/opt/homelab"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main
    log "Repo updated"
else
    info "Cloning repo to $INSTALL_DIR..."
    git clone https://github.com/kjonh2/homelab.git "$INSTALL_DIR"
    log "Repo cloned"
fi

cd "$INSTALL_DIR"

# ── 3. Environment file ─────────────────────────────────────────────────────

if [[ ! -f .env ]]; then
    info "Creating .env from template..."
    cp .env.example .env

    # Generate random passwords
    POSTGRES_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)
    MONGO_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)
    REDIS_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)
    GRAFANA_PASS=$(openssl rand -base64 24 | tr -d '=+/' | head -c 24)

    # Detect primary IP
    DEFAULT_IP=$(ip route get 1 | awk '{print $7; exit}')
    DOMAIN="example.com"

    sed -i "s|DOMAIN=.*|DOMAIN=${DOMAIN}|" .env
    sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASS}|" .env
    sed -i "s|MONGO_PASSWORD=.*|MONGO_PASSWORD=${MONGO_PASS}|" .env
    sed -i "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASS}|" .env
    sed -i "s|GRAFANA_ADMIN_PASSWORD=.*|GRAFANA_ADMIN_PASSWORD=${GRAFANA_PASS}|" .env
    sed -i "s|TZ=.*|TZ=Europe/London|" .env

    log ".env created with random passwords"
    warn "Edit .env to add your API keys (optional):"
    warn "  GITHUB_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc."
else
    log ".env already exists — keeping your settings"
fi

# ── 4. Create Docker network ────────────────────────────────────────────────

docker network create homelab &>/dev/null || true
log "Docker network 'homelab' ready"

# ── 5. Start services ───────────────────────────────────────────────────────

info "Starting all services..."
docker compose -f docker-compose.homelab.yml up -d

# ── 6. Wait for healthchecks ────────────────────────────────────────────────

echo ""
info "Waiting for services to become healthy..."

SERVICES=("postgresql" "mongodb" "redis" "hermes-agent" "grafana" "prometheus" "n8n")
MAX_WAIT=120
ELAPSED=0

for svc in "${SERVICES[@]}"; do
    CONTAINER="homelab-${svc}"
    WAITED=0
    while [[ $WAITED -lt $MAX_WAIT ]]; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "starting")
        if [[ "$STATUS" == "healthy" ]]; then
            log "$svc is healthy"
            break
        fi
        sleep 5
        WAITED=$((WAITED + 5))
        ELAPSED=$((ELAPSED + 5))
    done
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        warn "$svc did not become healthy within ${MAX_WAIT}s — check logs: docker logs $CONTAINER"
    fi
done

# ── 7. Summary ──────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              INSTALLATION COMPLETE               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}Services running:${NC}"
echo -e "    PostgreSQL     → localhost:5432"
echo -e "    MongoDB        → localhost:27017"
echo -e "    Redis          → localhost:6379"
echo -e "    Hermes WebUI   → http://localhost:8787"
echo -e "    Grafana        → http://localhost:3000"
echo -e "    Prometheus     → http://localhost:9090"
echo -e "    N8N            → http://localhost:5678"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "    1. Add proxy hosts in NPM GUI pointing to this machine's IP"
echo -e "    2. Check .env for passwords: cat /opt/homelab/.env"
echo -e "    3. View logs: docker compose -f /opt/homelab/docker-compose.homelab.yml logs -f"
echo ""
echo -e "  ${YELLOW}Data persistence:${NC}"
echo -e "    All data in Docker volumes at /opt/homelab/volumes/"
echo -e "    Hermes data: docker volume inspect homelab-hermes-home"
echo ""

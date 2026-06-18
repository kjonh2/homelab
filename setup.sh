#!/bin/bash
# ============================================================================
# HOMELAB — Interactive Setup Wizard
# Run: bash setup.sh
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

# ── Helpers ─────────────────────────────────────────────────────────────────

ask() {
    local prompt="$1"
    local default="${2:-}"
    local required="${3:-true}"
    local input=""

    while true; do
        if [[ -n "$default" ]]; then
            echo -en "${CYAN}  → ${prompt} [${default}]: ${NC}"
        else
            echo -en "${CYAN}  → ${prompt}: ${NC}"
        fi
        read -r input

        # Use default if empty
        if [[ -z "$input" && -n "$default" ]]; then
            input="$default"
        fi

        # Validate required
        if [[ "$required" == "true" && -z "$input" ]]; then
            err "This field is required."
            continue
        fi

        echo "$input"
        return
    done
}

ask_password() {
    local prompt="$1"
    local pass1 pass2

    while true; do
        echo -en "${CYAN}  → ${prompt}: ${NC}"
        read -rs pass1
        echo ""
        echo -en "${CYAN}  → Confirm ${prompt}: ${NC}"
        read -rs pass2
        echo ""

        if [[ -z "$pass1" ]]; then
            err "Password cannot be empty."
            continue
        fi

        if [[ "$pass1" != "$pass2" ]]; then
            err "Passwords don't match. Try again."
            continue
        fi

        echo "$pass1"
        return
    done
}

ask_yesno() {
    local prompt="$1"
    local default="${2:-y}"
    local input=""

    while true; do
        echo -en "${CYAN}  → ${prompt} [Y/n]: ${NC}"
        read -r input
        input="${input:-$default}"
        case "${input,,}" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            *)     err "Please answer y or n." ;;
        esac
    done
}

generate_password() {
    openssl rand -base64 24 | tr -d '=+/' | head -c 24
}

# ── Banner ──────────────────────────────────────────────────────────────────

clear
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                      ║${NC}"
echo -e "${CYAN}║   🏠  HOMELAB — Interactive Setup Wizard            ║${NC}"
echo -e "${CYAN}║       Self-hosted infrastructure                     ║${NC}"
echo -e "${CYAN}║                                                      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  This wizard will guide you through setting up your"
echo -e "  homelab. Answer the questions and everything will be"
echo -e "  configured automatically."
echo ""
echo -e "  ${YELLOW}Press Enter to start...${NC}"
read -r

# ── Step 1: Domain ──────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Step 1: Domain Configuration ━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

DOMAIN=$(ask "Domain name" "example.com")
TRAEFIK_DOMAIN=$(ask "Traefik dashboard subdomain" "traefik.example.com")

# ── Step 2: Database Passwords ──────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Step 2: Database Passwords ━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if ask_yesno "Generate random passwords automatically?" "y"; then
    POSTGRES_PASS=$(generate_password)
    MONGO_PASS=$(generate_password)
    REDIS_PASS=$(generate_password)
    GRAFANA_PASS=$(generate_password)
    log "Passwords generated automatically"
else
    echo ""
    echo -e "  ${YELLOW}Set passwords for each service:${NC}"
    echo ""
    POSTGRES_PASS=$(ask_password "PostgreSQL password")
    MONGO_PASS=$(ask_password "MongoDB password")
    REDIS_PASS=$(ask_password "Redis password")
    GRAFANA_PASS=$(ask_password "Grafana admin password")
fi

# ── Step 3: API Keys (optional) ─────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Step 3: API Keys (optional) ━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${YELLOW}Press Enter to skip any key you don't have yet.${NC}"
echo ""

GITHUB_TOKEN=$(ask "GitHub Token" "" "false")
OPENAI_API_KEY=$(ask "OpenAI API Key" "" "false")
ANTHROPIC_API_KEY=$(ask "Anthropic API Key" "" "false")

# ── Step 4: Services to deploy ──────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Step 4: Services to Deploy ━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

DEPLOY_POSTGRES="n"
DEPLOY_MONGO="n"
DEPLOY_REDIS="n"
DEPLOY_HERMES="n"
DEPLOY_GRAFANA="n"
DEPLOY_PROMETHEUS="n"
DEPLOY_N8N="n"

if ask_yesno "Deploy PostgreSQL?" "y"; then DEPLOY_POSTGRES="y"; fi
if ask_yesno "Deploy MongoDB?" "y"; then DEPLOY_MONGO="y"; fi
if ask_yesno "Deploy Redis?" "y"; then DEPLOY_REDIS="y"; fi
if ask_yesno "Deploy Hermes Agent?" "y"; then DEPLOY_HERMES="y"; fi
if ask_yesno "Deploy Grafana?" "y"; then DEPLOY_GRAFANA="y"; fi
if ask_yesno "Deploy Prometheus?" "y"; then DEPLOY_PROMETHEUS="y"; fi
if ask_yesno "Deploy N8N?" "y"; then DEPLOY_N8N="y"; fi

# ── Step 5: Summary ─────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Summary ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Domain:           ${GREEN}${DOMAIN}${NC}"
echo -e "  Traefik Domain:   ${GREEN}${TRAEFIK_DOMAIN}${NC}"
echo ""
echo -e "  Services to deploy:"
[[ "$DEPLOY_POSTGRES" == "y" ]] && echo -e "    ${GREEN}✓${NC} PostgreSQL"
[[ "$DEPLOY_MONGO" == "y" ]] && echo -e "    ${GREEN}✓${NC} MongoDB"
[[ "$DEPLOY_REDIS" == "y" ]] && echo -e "    ${GREEN}✓${NC} Redis"
[[ "$DEPLOY_HERMES" == "y" ]] && echo -e "    ${GREEN}✓${NC} Hermes Agent"
[[ "$DEPLOY_GRAFANA" == "y" ]] && echo -e "    ${GREEN}✓${NC} Grafana"
[[ "$DEPLOY_PROMETHEUS" == "y" ]] && echo -e "    ${GREEN}✓${NC} Prometheus"
[[ "$DEPLOY_N8N" == "y" ]] && echo -e "    ${GREEN}✓${NC} N8N"
echo ""

if ! ask_yesno "Proceed with installation?" "y"; then
    warn "Installation cancelled."
    exit 0
fi

# ── Step 6: Install Docker ──────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Installing Docker ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

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
    log "Docker Compose installed"
else
    log "Docker Compose already installed"
fi

# ── Step 7: Clone repo ──────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Repository ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

INSTALL_DIR="/opt/homelab"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main
    log "Repo updated"
else
    info "Cloning repo..."
    git clone https://github.com/kjonh2/homelab.git "$INSTALL_DIR"
    log "Repo cloned to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Step 8: Generate .env ───────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Generating .env ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cat > .env << EOF
# Homelab Environment Variables
# Generated by setup.sh on $(date '+%Y-%m-%d %H:%M:%S')

# Domain
DOMAIN=${DOMAIN}
TRAEFIK_DOMAIN=${TRAEFIK_DOMAIN}

# PostgreSQL
POSTGRES_DB=homelab
POSTGRES_USER=homelab_user
POSTGRES_PASSWORD=${POSTGRES_PASS}

# MongoDB
MONGO_USER=homelab_user
MONGO_PASSWORD=${MONGO_PASS}
MONGO_DB=homelab

# Redis
REDIS_PASSWORD=${REDIS_PASS}

# Grafana
GRAFANA_ADMIN_PASSWORD=${GRAFANA_PASS}

# Timezone
TZ=Europe/London

# API Keys (optional)
GITHUB_TOKEN=${GITHUB_TOKEN}
OPENAI_API_KEY=${OPENAI_API_KEY}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
EOF

log ".env created"

# ── Step 9: Create Docker network ───────────────────────────────────────────

docker network create homelab &>/dev/null || true
log "Docker network 'homelab' ready"

# ── Step 10: Deploy selected services ───────────────────────────────────────

echo ""
echo -e "${BOLD}━━━ Deploying Services ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Build list of services to start
SERVICES=()
[[ "$DEPLOY_POSTGRES" == "y" ]] && SERVICES+=("postgresql")
[[ "$DEPLOY_MONGO" == "y" ]] && SERVICES+=("mongodb")
[[ "$DEPLOY_REDIS" == "y" ]] && SERVICES+=("redis")
[[ "$DEPLOY_HERMES" == "y" ]] && SERVICES+=("hermes-agent")
[[ "$DEPLOY_GRAFANA" == "y" ]] && SERVICES+=("grafana")
[[ "$DEPLOY_PROMETHEUS" == "y" ]] && SERVICES+=("prometheus")
[[ "$DEPLOY_N8N" == "y" ]] && SERVICES+=("n8n")

if [[ ${#SERVICES[@]} -eq 0 ]]; then
    warn "No services selected to deploy."
else
    # Start all selected services
    SERVICE_LIST=$(IFS=,; echo "${SERVICES[*]}")
    info "Starting: ${SERVICE_LIST}"

    # Use docker compose to start specific services
    for svc in "${SERVICES[@]}"; do
        docker compose -f docker-compose.homelab.yml up -d "$svc"
        log "$svc started"
    done

    # Wait for healthchecks
    echo ""
    info "Waiting for services to become healthy..."

    for svc in "${SERVICES[@]}"; do
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
fi

# ── Step 11: Final summary ──────────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                      ║${NC}"
echo -e "${CYAN}║   ✅  HOMELAB — Installation Complete!              ║${NC}"
echo -e "${CYAN}║                                                      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Domain:${NC}           ${DOMAIN}"
echo -e "  ${BOLD}Config file:${NC}      /opt/homelab/.env"
echo ""

if [[ ${#SERVICES[@]} -gt 0 ]]; then
    echo -e "  ${BOLD}Services:${NC}"
    [[ "$DEPLOY_POSTGRES" == "y" ]] && echo -e "    PostgreSQL     → localhost:5432"
    [[ "$DEPLOY_MONGO" == "y" ]] && echo -e "    MongoDB        → localhost:27017"
    [[ "$DEPLOY_REDIS" == "y" ]] && echo -e "    Redis          → localhost:6379"
    [[ "$DEPLOY_HERMES" == "y" ]] && echo -e "    Hermes WebUI   → http://localhost:8787"
    [[ "$DEPLOY_GRAFANA" == "y" ]] && echo -e "    Grafana        → http://localhost:3000"
    [[ "$DEPLOY_PROMETHEUS" == "y" ]] && echo -e "    Prometheus     → http://localhost:9090"
    [[ "$DEPLOY_N8N" == "y" ]] && echo -e "    N8N            → http://localhost:5678"
    echo ""
fi

echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "    1. Add proxy hosts in NPM GUI → point to this machine's IP"
echo -e "    2. View logs:  docker compose -f /opt/homelab/docker-compose.homelab.yml logs -f"
echo -e "    3. Edit .env:  nano /opt/homelab/.env"
echo -e "    4. Re-run setup: bash /opt/homelab/setup.sh"
echo ""

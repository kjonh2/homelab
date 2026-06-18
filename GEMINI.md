# GEMINI.md — Homelab Project Context

## What This Project Is

This is the infrastructure-as-code repository for **iknowu.org**, a self-hosted homelab running on **Proxmox** with LXC containers and Docker services.

## Architecture Overview

```
Internet → Traefik (LXC 101, SSL) → Nginx Proxy Manager (LXC 100, GUI routing) → Services
```

### Current LXC Containers

| LXC | Name | Purpose |
|-----|------|---------|
| 100 | nginx-proxy-manager | Internal reverse proxy with web GUI (NPM) |
| 101 | traefik | Entry point, SSL termination (Let's Encrypt) |
| 102 | nodejs-app | Main website (Node.js) serving iknowu.org |

### Docker Services (this repo)

Defined in `docker-compose.homelab.yml`:

| Service | Purpose | Image |
|---------|---------|-------|
| PostgreSQL | Relational database | `postgres:16-alpine` |
| MongoDB | Document database | `mongo:7` |
| Redis | Cache & sessions | `redis:7-alpine` |
| Hermes Agent | AI agent gateway + WebUI | `nousresearch/hermes-agent` |
| Grafana | Monitoring dashboards | `grafana/grafana-oss` |
| Prometheus | Metrics collection | `prom/prometheus` |
| N8N | Workflow automation | `n8nio/n8n` |

## Deployment Recommendations

### Recommended: Single VM with Docker Compose

**Create a dedicated LXC or VM on Proxmox for all Docker services.**

Why a VM instead of LXC for Docker:
- Docker runs better in a VM (full kernel, no nesting issues)
- Easy snapshot/backup of the entire VM
- Can migrate between Proxmox hosts
- Resource isolation from other containers
- If Docker breaks, the rest of the homelab keeps running

**VM specs (minimum):**
- 2 vCPU
- 4GB RAM (8GB recommended)
- 40GB disk (SSD preferred)
- Ubuntu 22.04 or Debian 12

**Setup:**
```bash
# On the new VM
apt update && apt install docker.io docker-compose-plugin -y
git clone https://github.com/kjonh/homelab.git /opt/homelab
cd /opt/homelab
cp .env.example .env
nano .env  # Fill in your values
docker compose -f docker-compose.homelab.yml up -d
```

Then add proxy hosts in NPM GUI pointing to the VM IP.

### Alternative: Separate LXC per service

Only recommended if:
- You have plenty of RAM on Proxmox (16GB+)
- You need strict isolation between services
- You plan to scale individual services independently

Downsides:
- More complex to manage
- More overhead (each LXC needs its own OS)
- Harder to backup/restore
- Network configuration is more complex

### NOT recommended: Running Docker on the Proxmox host directly

- Docker on Proxmox host can cause kernel conflicts
- Updates to Proxmox may break Docker
- No isolation between hypervisor and containers
- If Docker fills the disk, Proxmox host is affected

## Data Persistence

### Where user data lives

All persistent data is stored in Docker named volumes on the VM:

| Volume | Service | Contents | Path inside container |
|--------|---------|----------|-----------------------|
| `homelab-hermes-home` | Hermes | Agent config, sessions, skills, memories, auth | `/home/hermeswebui/.hermes/` |
| `homelab-postgres-data` | PostgreSQL | All databases, users, tables | `/var/lib/postgresql/data` |
| `homelab-mongodb-data` | MongoDB | All databases, collections, users | `/data/db` |
| `homelab-redis-data` | Redis | Cache, sessions | `/data` |
| `homelab-grafana-data` | Grafana | Dashboards, users, settings | `/var/lib/grafana` |
| `homelab-prometheus-data` | Prometheus | Metrics history (30 days) | `/prometheus` |
| `homelab-n8n-data` | N8N | Workflows, credentials, executions | `/home/node/.n8n` |

### Hermes user data (IMPORTANT)

When the user asks "where is my Hermes data?", the answer is:

**Volume:** `homelab-hermes-home`
**Inside container:** `/home/hermeswebui/.hermes/`
**Key subdirectories:**
- `sessions/` — All chat sessions (JSON files)
- `webui/` — WebUI state, attachments
- `skills/` — Custom skills
- `memories/` — AI memory files
- `cache/` — Cached data
- `config.yaml` — Main Hermes configuration
- `auth.json` — Authentication tokens
- `SOUL.md` — Agent personality definition

**To access from the VM host:**
```bash
# Find the volume path
docker volume inspect homelab-hermes-home

# Or exec into the container
docker exec -it homelab-hermes-agent ls -la /home/hermeswebui/.hermes/

# Backup Hermes data
docker run --rm \
  -v homelab-hermes-home:/data \
  -v /backup:/backup \
  alpine tar czf /backup/hermes-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### Backup strategy

**Full backup (recommended daily):**
```bash
cd /opt/homelab

# Stop services
docker compose -f docker-compose.homelab.yml down

# Backup all volumes
docker run --rm \
  -v homelab-hermes-home:/data/hermes \
  -v homelab-postgres-data:/data/postgres \
  -v homelab-mongodb-data:/data/mongo \
  -v homelab-redis-data:/data/redis \
  -v homelab-grafana-data:/data/grafana \
  -v homelab-prometheus-data:/data/prometheus \
  -v homelab-n8n-data:/data/n8n \
  -v /backup:/backup \
  alpine tar czf /backup/homelab-full-$(date +%Y%m%d).tar.gz -C /data .

# Restart services
docker compose -f docker-compose.homelab.yml up -d
```

**Quick backup (Hermes only, can run while services are up):**
```bash
docker exec homelab-hermes-agent tar czf /tmp/hermes-backup.tar.gz -C /home/hermeswebui .hermes
docker cp homelab-hermes-agent:/tmp/hermes-backup.tar.gz /backup/hermes-$(date +%Y%m%d).tar.gz
```

## Key Design Decisions

1. **Traefik handles SSL** — automatic Let's Encrypt certificates, HTTP→HTTPS redirect
2. **NPM handles routing** — GUI-based, easier to manage than Traefik labels
3. **Docker for services** — databases, AI, monitoring run in Docker containers
4. **LXC for infrastructure** — Traefik, NPM, and Node.js app run in separate LXC containers
5. **Proxmox as host** — all of this runs on a Proxmox server

## When Adding Services

1. Add the service to `docker-compose.homelab.yml`
2. Deploy: `docker compose -f docker-compose.homelab.yml up -d <service>`
3. Add a Proxy Host in NPM GUI pointing to the VM IP:port
4. SSL is automatic (Traefik → NPM chain)

## Security Notes

- `.env` is gitignored — never commit secrets
- Change all default passwords before production use
- The Hermes WebUI should be accessible via HTTPS through the Traefik→NPM chain
- Consider adding authentication to services that don't have it (Grafana, Prometheus)

## User Preferences

- Prefers GUI tools (NPM) over CLI configuration for routing
- Wants clean, minimal repos — no temporary files or generated documentation
- Plans to add services incrementally as Proxmox resources allow
- May run additional services on a laptop with port forwarding if Proxmox is full
- Wants to be able to migrate the entire setup to another machine easily

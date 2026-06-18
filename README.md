# 🏠 Homelab — Self-Hosted Infrastructure

Self-hosted infrastructure on Proxmox with LXC containers, Traefik SSL termination, Nginx Proxy Manager for routing, and Docker services for databases, AI, and monitoring.

## Architecture

```
                         Internet
                            │
                            ▼
              ┌─────────────────────────┐
              │   DNS (your provider)   │
              │   (example.com)         │
              └────────────┬────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │   LXC 101 — Traefik     │
              │   Ports: 80, 443        │
              │   SSL termination       │
              │   Auto-renew (Let's     │
              │   Encrypt)              │
              └────────────┬────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │   LXC 100 — Nginx       │
              │   Proxy Manager         │
              │   Port: 81 (admin)      │
              │   GUI-based routing     │
              └────────────┬────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
   ┌────────────┐  ┌────────────┐  ┌────────────┐
   │ LXC 102    │  │ Docker     │  │ Future     │
   │ Node.js    │  │ Services   │  │ services   │
   │ App        │  │ (this repo)│  │            │
   │ example.com│  │            │  │            │
   └────────────┘  └────────────┘  └────────────┘
```

## Infrastructure

### Proxmox Host

| LXC | Name | IP | Purpose |
|-----|------|----|---------|
| 100 | nginx-proxy-manager | 192.168.1.100 | Reverse proxy with GUI |
| 101 | traefik | 192.168.1.101 | SSL termination & entry point |
| 102 | nodejs-app | 192.168.1.102 | Main website (Node.js) |

### Planned Docker Services

These will be added to the Proxmox host (or a dedicated LXC) as Docker containers:

| Service | Purpose | Image |
|---------|---------|-------|
| PostgreSQL | Relational database | `postgres:16-alpine` |
| MongoDB | Document database | `mongo:7` |
| Redis | Cache & sessions | `redis:7-alpine` |
| Hermes Agent | AI agent gateway | `nousresearch/hermes-agent` |
| Grafana | Monitoring dashboards | `grafana/grafana-oss` |
| Prometheus | Metrics collection | `prom/prometheus` |
| N8N | Workflow automation | `n8nio/n8n` |

## Traefik (LXC 101) — Entry Point

Traefik receives all traffic on ports 80/443, handles SSL, and forwards to Nginx Proxy Manager.

### Setup

```bash
# On LXC 101
apt update && apt install docker.io docker-compose -y

# Create directories
mkdir -p /opt/traefik

# Start
docker compose -f /opt/traefik/docker-compose.yml up -d
```

### Configuration

**`/opt/traefik/docker-compose.yml`:**

```yaml
version: "3.9"

services:
  traefik:
    image: traefik:v3.7
    container_name: traefik
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
      - ./traefik.yml:/traefik.yml:ro
      - ./dynamic.yml:/dynamic.yml:ro
    networks:
      - proxy

networks:
  proxy:
    external: true
```

**`/opt/traefik/traefik.yml`:**

```yaml
global:
  checkNewVersion: false
  sendAnonymousUsage: false

api:
  insecure: true
  dashboard: true

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

providers:
  file:
    filename: /dynamic.yml
    watch: true

certificatesResolvers:
  letsencrypt:
    acme:
      email: admin@example.com
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web

log:
  level: INFO
```

**`/opt/traefik/dynamic.yml`:**

```yaml
http:
  routers:
    # Forward everything to Nginx Proxy Manager
    to-npm:
      rule: "HostRegexp(`{host:.+}`)"
      service: npm
      entryPoints: [web, websecure]
      tls:
        certResolver: letsencrypt
      priority: 1

  services:
    npm:
      loadBalancer:
        servers:
          - url: "http://192.168.1.100:80"
```

### Create Docker Network

```bash
docker network create proxy
```

## Nginx Proxy Manager (LXC 100) — Internal Routing

NPM handles all internal routing via its web GUI. Access at `http://192.168.1.100:81`.

### Setup

```bash
# On LXC 100
apt update && apt install docker.io docker-compose -y
mkdir -p /opt/npm
```

**`/opt/npm/docker-compose.yml`:**

```yaml
version: "3.9"

services:
  npm:
    image: jc21/nginx-proxy-manager:latest
    container_name: npm
    restart: unless-stopped
    ports:
      - "80:80"
      - "81:81"     # Admin GUI
      - "443:443"
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
    environment:
      - DB_SQLITE_FILE=/data/database.sqlite
```

### NPM Proxy Hosts

Configure these in the NPM GUI (`http://192.168.1.100:81`):

| Domain | Forward To | Port | Scheme |
|--------|-----------|------|--------|
| `example.com` | 192.168.1.102 | 3000 | http |
| `www.example.com` | 192.168.1.102 | 3000 | http |
| `traefik.example.com` | 192.168.1.101 | 8080 | http |

Default login: `admin@example.com` / `changeme`

## Node.js App (LXC 102) — Main Website

Your Node.js application serving `example.com`.

### Setup

```bash
# On LXC 102
apt update && apt install nodejs npm -y
mkdir -p /opt/app
```

**`/opt/app/docker-compose.yml`:**

```yaml
version: "3.9"

services:
  app:
    build: .
    container_name: nodejs-app
    restart: unless-stopped
    expose:
      - "3000"
    environment:
      - NODE_ENV=production
      - PORT=3000
```

## Docker Services

Deploy databases, AI, and monitoring on the Proxmox host or a dedicated VM:

### Quick install (interactive)

```bash
git clone https://github.com/kjonh2/homelab.git /opt/homelab
cd /opt/homelab
bash setup.sh
```

The wizard will ask you for domain, passwords, API keys, and which services to deploy.

### Automated (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/kjonh2/homelab/main/install.sh | bash
```

### Manual

```bash
git clone https://github.com/kjonh2/homelab.git /opt/homelab
cd /opt/homelab
cp .env.example .env
nano .env
docker compose -f docker-compose.homelab.yml up -d
```

## DNS Configuration

Point your domain to the server:

| Type | Name | Value |
|------|------|-------|
| A | `example.com` | `<your-server-ip>` |
| A | `www` | `<your-server-ip>` |
| A | `traefik` | `<your-server-ip>` |

## Adding New Services

1. Deploy the service (Docker container on Proxmox or new LXC)
2. Add a Proxy Host in NPM GUI pointing to the service IP:port
3. SSL is handled automatically by Traefik → NPM

## Troubleshooting

```bash
# Check Traefik
docker logs -f traefik

# Check NPM
docker logs -f npm

# Check Node.js app
docker logs -f nodejs-app

# Test routing
curl -H "Host: example.com" http://192.168.1.101
```

## License

MIT

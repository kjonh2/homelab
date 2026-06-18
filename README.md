<!-- README.md — HOMELAB -->
<!-- Designed to be welcoming to everyone, from beginners to advanced users. -->

<h1 align="center">
  <br>
  <img src="https://img.icons8.com/fluency/96/house.png" alt="Homelab" width="80">
  <br>
  🏠 Homelab — One Click Deploy
  <br>
</h1>

<h4 align="center">
  Self-hosted infrastructure for everyone. No tech skills required.
</h4>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#what-you-get">What You Get</a> •
  <a href="#platforms">Platforms</a> •
  <a href="#why">Why?</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#technical">Technical Details</a> •
  <a href="#contribute">Contribute</a>
</p>

---

## 🌟 What Is This?

**Homelab in one click.**

This project exists to simplify the life of anyone who wants to evolve with AI but is afraid of touching a computer. With one simple install, you will have your own **private homelab** — no need to pay any company for cloud services, no data leaving your home, no monthly fees.

> **Your data. Your rules. Your AI. At home.**

This project is designed to be accessible to **everyone**. Your mom, your kids, your grandma — anyone should be able to set up their own homelab. If you can tap a button, you can run this.

---

## 🚀 What You Get

After one simple install, you have your own private cloud running at home:

| Service | What It Does | Access |
|---------|-------------|--------|
| 🤖 **Hermes AI** | Your personal AI assistant — private, always available, remembers everything | Web browser |
| 📊 **Grafana** | Beautiful dashboards to monitor everything | Web browser |
| 📈 **Prometheus** | Collects metrics so you know how healthy your system is | Web browser |
| ⚡ **N8N** | Automate tasks between apps — no coding needed | Web browser |
| 🐘 **PostgreSQL** | Relational database for your apps | Internal |
| 🍃 **MongoDB** | Document database for flexible data | Internal |
| 🔴 **Redis** | Fast cache and session storage | Internal |

All of this runs on **your hardware**. In your home. Under your control.

---

## 📱 Choose Your Platform

Homelab is designed to work everywhere. Pick your device:

| Platform | Status | Install Method |
|----------|--------|----------------|
| **Proxmox LXC** | ✅ Ready | One-command script |
| **Linux (Docker)** | ✅ Ready | One-command script |
| **Windows (Docker Desktop)** | ✅ Ready | One-command script |
| **macOS (Docker Desktop)** | ✅ Ready | One-command script |
| **Android** | 🔜 Coming | App in development |
| **iOS / iPadOS** | 🔜 Coming | App in development |

---

## 💻 Quick Start

### 🖥️ Proxmox LXC (Recommended)

Create a new LXC container on Proxmox (Debian 12 or Ubuntu 22.04), then run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/proxmox-install.sh)
```

This will:
1. Install Docker + Docker Compose
2. Clone the repo to `/opt/homelab`
3. Ask you for your domain name
4. Generate secure random passwords
5. Start all services
6. Show you the URLs to access everything

**Requirements:** LXC with at least 2 vCPU, 4GB RAM, 40GB disk

---

### 🐧 Linux (Docker)

On any Linux machine with Docker:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/proxmox-install.sh)
```

Or for the interactive wizard:

```bash
git clone https://github.com/kjonh2/homelab.git /opt/homelab
cd /opt/homelab
bash setup.sh
```

---

### 🪟 Windows (Docker Desktop)

**Prerequisite:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) first.

Then in **PowerShell** or **Git Bash**:

```powershell
# Using PowerShell
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/windows-install.ps1 | iex
```

Or in **Git Bash**:

```bash
curl -fsSL https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/windows-install.sh | bash
```

Or manually:

```powershell
git clone https://github.com/kjonh2/homelab.git $env:USERPROFILE\homelab
cd $env:USERPROFILE\homelab
copy .env.example .env
notepad .env
docker compose -f docker-compose.homelab.yml up -d
```

---

### 🍎 macOS (Docker Desktop)

**Prerequisite:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) first.

```bash
curl -fsSL https://raw.githubusercontent.com/kjonh2/homelab/main/scripts/windows-install.sh | bash
```

Or manually:

```bash
git clone https://github.com/kjonh2/homelab.git ~/homelab
cd ~/homelab
cp .env.example .env
nano .env
docker compose -f docker-compose.homelab.yml up -d
```

---

### 📱 Mobile (Coming Soon)

When the mobile apps are ready, you will be able to set up and manage your entire homelab from your phone — no typing commands, no technical knowledge needed. Just tap, tap, done.

> **The goal:** Your mom can have an app on her iPhone that connects to her homelab at home, giving her access to all these powerful tools from the palm of her hand.

---

### After Install

Once running, open your browser:

| Service | Local URL | Via Domain |
|---------|-----------|------------|
| 🤖 Hermes AI | `http://localhost:8787` | `https://yourdomain.com/hermes` |
| 📊 Grafana | `http://localhost:3000` | `https://yourdomain.com/grafana` |
| 📈 Prometheus | `http://localhost:9090` | `https://yourdomain.com/prometheus` |
| ⚡ N8N | `http://localhost:5678` | `https://yourdomain.com/n8n` |

To access via your domain, add proxy hosts in Nginx Proxy Manager pointing to your server's IP.

### The Problem

Today, if you want to use AI, you have two options:

1. **Pay a company** (OpenAI, Google, etc.) — they store your data, they control what you can do, and you pay monthly forever.
2. **Learn to code and set up servers yourself** — takes months, requires deep technical knowledge, and one mistake can break everything.

### The Solution

**Homelab gives you option 3:** Your own private AI and services, running at home, on your terms.

- 🔒 **100% Private** — Your data never leaves your home
- 💰 **No monthly fees** — Run it on hardware you already own
- 🧠 **AI that knows you** — Hermes remembers your preferences, your projects, your life
- 📱 **Access anywhere** — From your phone, tablet, laptop — anything with a browser
- 🔧 **Grow as you learn** — Start basic, add more as you're ready

### Who Is This For?

- **Beginners** who want AI without complexity
- **Families** who want a private AI at home
- **Students** who want to learn with real tools
- **Developers** who want full control
- **Privacy-conscious people** who don't trust big tech
- **Tinkerers** who love building things at home

---

## 🏠 How It Works — The Simple Version

Here's what happens when you install:

```
1. You run one command
         │
         ▼
2. The wizard asks you 3 simple questions
   → What's your domain? (or use free one we provide)
   → What password do you want?
   → Which services do you want? (all recommended)
         │
         ▼
3. Everything installs automatically
   → Docker sets up the containers
   → Services connect to each other
   → Health checks confirm everything works
         │
         ▼
4. ✅ Done! Open your browser and use it.
```

No coding. No Linux knowledge. No frustration.

---

## 🏗️ How It Works — Architecture

For those who want to understand the full setup:

```
                         Internet
                            │
                            ▼
              ┌─────────────────────────┐
              │   Your DNS Provider     │
              │   (example.com)         │
              └────────────┬────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │   Traefik (LXC 101)     │
              │   SSL termination       │
              │   Ports: 80, 443        │
              └────────────┬────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │   Nginx Proxy Manager   │
              │   (LXC 100)             │
              │   GUI-based routing     │
              │   Admin: :81            │
              └────────────┬────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
   ┌────────────┐  ┌────────────┐  ┌────────────┐
   │ Node.js    │  │ Docker     │  │ Future     │
   │ App        │  │ Services   │  │ services   │
   │ (LXC 102)  │  │ (this repo)│  │            │
   └────────────┘  └────────────┘  └────────────┘
```

### LXC Containers

| ID | Container | Purpose |
|----|-----------|---------|
| 100 | Nginx Proxy Manager | Internal GUI-based routing — point and click |
| 101 | Traefik | Entry point — handles SSL certificates automatically |
| 102 | Node.js App | Your main website/application |

### Docker Services

Managed via Docker Compose on the Proxmox host or a dedicated VM:

| Service | Image | Purpose |
|---------|-------|---------|
| Hermes Agent | `nousresearch/hermes-agent` | AI assistant + WebUI |
| PostgreSQL | `postgres:16-alpine` | Relational database |
| MongoDB | `mongo:7` | Document database |
| Redis | `redis:7-alpine` | Cache |
| Grafana | `grafana/grafana-oss` | Monitoring dashboards |
| Prometheus | `prom/prometheus` | Metrics collection |
| N8N | `n8nio/n8n` | Workflow automation |

---

## 🔒 Your Data — Where It Lives

Everything is stored in Docker volumes on your machine:

| Volume | What's Stored |
|--------|--------------|
| `homelab-hermes-home` | AI sessions, memories, skills, config |
| `homelab-postgres-data` | All PostgreSQL databases |
| `homelab-mongodb-data` | All MongoDB databases |
| `homelab-redis-data` | Cached data |
| `homelab-grafana-data` | Dashboards and settings |
| `homelab-prometheus-data` | Metrics history (30 days) |
| `homelab-n8n-data` | Workflows and credentials |

All data survives container restarts. For backups, see the [backup section](#backup) below.

---

## 🌐 Access From Your Phone (and Anywhere)

Once your homelab is running, you can access it from **any device**:

1. **Same network:** Just open `http://<your-server-ip>:8787` in any browser
2. **From anywhere:** Set up port forwarding on your router, or use a VPN
3. **With your domain:** Point your DNS to your server's IP — Traefik handles the rest with automatic SSL

Coming soon: **mobile apps** for Android and iOS that give you a native experience without needing to type URLs.

---

## 📸 Demos

<details>
<summary>🖼️ Click to see screenshots</summary>

*(Screenshots and demo images will be added here — send them to the maintainer and they'll get updated)*

### Hermes AI WebUI
> Your personal AI, always available, completely private.

### Grafana Dashboard
> Beautiful monitoring for your entire homelab.

### N8N Workflows
> Automate anything — no coding required.

</details>

---

## 🔧 Technical Details

<details>
<summary>For developers and contributors — click to expand</summary>

### Project Structure

```
homelab/
├── docker-compose.homelab.yml    # Main Docker Compose file
├── setup.sh                      # Interactive setup wizard
├── install.sh                    # One-command automated installer
├── .env.example                  # Environment variable template
├── .gitignore
├── README.md                     # This file
├── GEMINI.md                     # AI context for contributors
├── traefik/
│   ├── traefik.yml               # Traefik static config (for LXC 101)
│   └── traefik-dynamic.yml       # Traefik routing rules
└── prometheus/
    └── prometheus.yml            # Prometheus scrape config
```

### Requirements

- Docker 20.10+
- Docker Compose v2+
- Minimum 4GB RAM (8GB recommended)
- 40GB disk space
- Ports 80 and 443 open (for SSL)

### Adding New Services

1. Add the service definition to `docker-compose.homelab.yml`
2. Add environment variables to `.env.example`
3. Add a Proxy Host in Nginx Proxy Manager GUI
4. Submit a pull request!

### Backup

```bash
# Backup everything
cd /opt/homelab
docker compose -f docker-compose.homelab.yml down
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
docker compose -f docker-compose.homelab.yml up -d
```

### Updating

```bash
cd /opt/homelab
git pull origin main
docker compose -f docker-compose.homelab.yml up -d --force-recreate
```

### Contributing

This project welcomes contributions of all kinds:

- 🐛 Report bugs via Issues
- 💡 Suggest features
- 🌐 Translate documentation
- 📱 Help build mobile apps
- 🔧 Add new services to the Docker Compose
- 📖 Improve this README

See [GEMINI.md](GEMINI.md) for detailed technical context.

</details>

---

## 🤝 Contribute

This project is open source and welcomes everyone:

- **Not technical?** Report bugs, suggest features, help with documentation
- **Developer?** Add services, improve scripts, build integrations
- **Designer?** Create UI mockups, improve the mobile app experience
- **Translator?** Help translate this README into your language

Every contribution matters. The goal is to make this accessible to **everyone**.

---

## ❤️ Philosophy

> Technology should serve people, not the other way around.

This project was born from the belief that AI and powerful tools should not be locked behind monthly subscriptions, complex setups, or corporate gatekeeping. Every person deserves to have their own AI assistant, their own automation tools, and their own data — without needing a computer science degree.

If your mom can use an iPhone, she deserves to have an AI that helps her. This project is built to make that possible.

---

## 📄 License

MIT — Use it, modify it, share it. Just be kind.

---

<p align="center">
  <strong>🌟 Star this repo if it helped you!</strong><br>
  <a href="https://github.com/kjonh2/homelab">github.com/kjonh2/homelab</a>
</p>

---

<sub>Built with ❤️ for everyone — from beginners to experts.</sub>

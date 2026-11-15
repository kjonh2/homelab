# Iku multi-file Docker Compose layout

## Goal
Split the current monolithic `iku-compose.yml` into service-isolated Compose files so updates can target a single app, while matching the DNS policy:
- public apps: `iknowu.org/<service>` when the app can really run behind a subpath
- admin/internal apps: subdomains
- no full-stack restarts for a single app update

## Proposed file plan

### 1) `compose/iku-proxy.yml`
Proxy-only stack.
- Traefik container
- ACME / cert storage
- Docker socket mount
- shared network
- redirect middleware for `iknowu.org/<service>` -> subdomain when an app cannot handle a subpath

### 2) `compose/iku-core.yml`
Public user-facing apps and shared data services.
- PostgreSQL
- MongoDB
- Nextcloud
- n8n
- Confy
- Open WebUI
- shared volumes for app data

### 3) `compose/iku-admin.yml`
Admin/internal apps.
- Grafana
- llama.cpp server / AI backend
- GitLab if/when added
- any other private ops tools

### 4) `compose/iku-portal.yml`
Root portal and path router helpers.
- `iknowu.org` landing page
- lightweight redirect service or proxy middleware for `/n8n`, `/confy`, `/webui`, `/cloud`
- optional auth gate or session bootstrap

### 5) `compose/iku.env`
Single env file for shared secrets and hostnames.
- DB credentials
- ACME email
- canonical hostname values
- app-specific base-path/base-url vars

### 6) `compose/README.md`
Operational notes.
- service update commands
- which services can be restarted independently
- which apps need subpath config vs redirect

## Service split recommendation

- `traefik` stays alone in `iku-proxy.yml`
- `postgres` and `mongo` stay in `iku-core.yml` but are not coupled to app restarts
- `nextcloud`, `n8n`, `confy`, `webui` stay in `iku-core.yml` so public apps stay together logically, but each gets its own router and independent update command
- `grafana` and `ai` move to `iku-admin.yml` to keep admin paths isolated from public traffic

## Update rule
Use targeted compose commands only:
- `docker compose -f compose/iku-core.yml up -d --no-deps --force-recreate n8n`
- `docker compose -f compose/iku-core.yml up -d --no-deps --force-recreate nextcloud`
- `docker compose -f compose/iku-admin.yml up -d --no-deps --force-recreate grafana`
- `docker compose -f compose/iku-proxy.yml up -d --no-deps --force-recreate traefik`

## Practical routing rule
- default public route: `iknowu.org/<service>`
- if the app does not support base-path cleanly, keep the public path as a redirect-only alias and send users to the subdomain
- admin apps never live on a public path; they stay on subdomains

## Notes for the current stack
The existing single-file compose already hints at the split:
- proxy: `iku-proxy`
- data: `iku-db`, `iku-memory`
- public apps: `iku-nextcloud`, `iku-n8n`, `iku-confy`, `iku-webui`
- admin apps: `iku-grafana`, `iku-ai`

The next practical step is to move those service blocks into the files above without changing the router names or the DNS hostnames.
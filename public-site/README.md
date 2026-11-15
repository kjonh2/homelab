# Iku public website

The public landing page is a separate React/Vite app. Keep the authenticated Iku portal and personal service endpoints on protected routes; this site must not render private health data, model controls, credentials, or internal addresses.

## Development

```powershell
npm install
npm run dev
```

## Production build

```powershell
npm run build
```

Vite writes a static site to `dist/`. The build keeps generated assets at the top level so a deployment ConfigMap can mount the complete site without exposing a service port. The public entry route is `/`; the app login link points to the existing `app.iknowu.org` hostname.

## VPS / Cloudflare Tunnel

The Kubernetes Deployment serves only inside the cluster. Nginx listens on port 80 inside its pod; the Cloudflared sidecar shares that pod network and uses a dedicated VPS tunnel whose routes send `iknowu.org` and `app.iknowu.org` to `http://localhost:80`. No public VPS ports are opened. The tunnel secret is read from a local file at deployment time and is never committed:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/k3s/deploy-public-site.ps1 `
  -TunnelTokenFile C:\Users\kjonh\workspace\drisa\cloudflare_tunnel_token_vps.txt
```

The Nginx virtual host serves the public landing page at `iknowu.org` and forwards `app.iknowu.org` to the authenticated Iku portal. Unknown hostnames return 404. The portal still enforces its own login; the public site does not expose service status or credentials. The existing laptop tunnel remains responsible for `pc.iknowu.org` and `netbird.iknowu.org`; `www.iknowu.org` remains pointed at Squarespace.

Cloudflared uses HTTP/2 because outbound UDP port 7844 is blocked from the VPS. The Windows Cloudflared connector can remain running for its other hostnames; the public site and app no longer depend on the laptop being available.

# Iku Portal

Private Next.js portal deployed to the VPS and served only inside the Tailscale tailnet. Login and the initial administrator bootstrap are connected to the `iku-auth` FastAPI service through the server-side API proxy. The portal fails closed when auth is unavailable. The landing and Services pages perform unauthenticated health checks for Nextcloud, n8n, and LFM3; they do not expose user files, workflows, or model prompts.

User/device management and a shared auth gateway (SSO) are not implemented. Nextcloud, n8n, and LFM3 keep their own authentication. Do not describe the current setup as SSO.

## Development

```powershell
npm install
npm run dev
```

## Container

The Dockerfile builds a standalone Next.js image on port 3000. Keep the ClusterIP service private and publish access only through the VPS's tailnet-only Tailscale Serve route.

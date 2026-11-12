# Iku Portal

Private Next.js portal deployed to the VPS and served only inside the Tailscale tailnet. Login and the initial administrator bootstrap are connected to the `iku-auth` FastAPI service through the server-side API proxy. The portal fails closed when auth is unavailable. The landing and Services pages perform unauthenticated health checks for Nextcloud, n8n, and LFM3; they do not expose user files, workflows, or model prompts.

The **Administração** page is restricted to authenticated administrator sessions with TOTP. Administrators can invite normal users with single-use 72-hour tokens, list and disable or re-enable accounts, revoke pending invitations, and invalidate a disabled user's sessions, Android refresh-token families, and API tokens. Invitation hashes are stored in SQLite; the raw code is shown once and is entered in `/invite`, never placed in a URL. Invites cannot assign the administrator role. Nextcloud, n8n, and LFM3 keep their own authentication; shared auth gateway and SSO are not implemented. Do not describe the current setup as SSO.

## Development

```powershell
npm install
npm run dev
```

## Container

The Dockerfile builds a standalone Next.js image on port 3000. Keep the ClusterIP service private and publish access only through the VPS's tailnet-only Tailscale Serve route.

# Iku Portal

Private Next.js portal deployed to the VPS. The public `app.iknowu.org` route exposes the landing page and login; authenticated account and service pages require an Iku session. The portal communicates with the private `iku-auth` FastAPI service through its server-side API proxy and fails closed when Auth is unavailable.

The login supports local email/password and Google Identity Services. Google sign-in exchanges the Google credential through Firebase Identity Toolkit, then Iku Auth validates the Firebase ID token and issues the Iku session. Google sign-in is restricted to an existing, enabled Iku account; administrator accounts still require TOTP. The public Google configuration endpoint exposes only the Firebase web API key, OAuth client ID, and project ID. Do not put service-account credentials or other private keys in the portal bundle or ConfigMap.

The **Administração** page is restricted to authenticated administrator sessions with TOTP. Administrators can invite normal users with single-use 72-hour tokens, list and disable or re-enable accounts, revoke pending invitations, and invalidate a disabled user's sessions, Android refresh-token families, and API tokens. Invitation hashes are stored in SQLite; the raw code is shown once and is entered in `/invite`, never placed in a URL. Invites cannot assign the administrator role.

Nextcloud's `user_oidc` provider is configured for Iku Auth. The existing Nextcloud administrator must be explicitly mapped to the matching Iku identity before SSO access to existing files is considered verified; keep local Nextcloud login available until an end-to-end login and file-access check succeeds. n8n and LFM3 keep their own authentication. Do not describe them as using shared SSO.

`GET /api/homelab/status` is the Android Início status endpoint. It requires an Iku bearer token, validates the token with the internal Auth service, and returns only service health summaries. It omits internal probe URLs and does not proxy service data.

Portal `0.1.11` and Auth `0.2.0` were observed deployed on the VPS on 2026-11-14. The portal's Google configuration endpoint returned `configured: true`, and the rendered login page displayed the Google sign-in button after client hydration. The Redmi was offline on Tailscale and absent from ADB during the same check, so current Android playback and session state still need device-side verification.

## Development

```powershell
npm install
npm run dev
```

## Container

The Dockerfile builds a standalone Next.js image on port 3000. Keep the ClusterIP service private; public access to the portal is through the configured Cloudflare Tunnel and authenticated portal routes.

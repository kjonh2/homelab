# Iku Portal UI

Frontend shell based on the portal and authentication notes in `../iku-portal-shell-implementation.md` and `../iku-auth-blueprint.md`.

This is a UI preview. Login, sessions, profile data, device management, service checks, and admin actions are not connected to a backend. The login controls are intentionally inactive and the sections display no personal data. Do not publish this as a working portal until the local auth service, authorization checks, and private gateway are implemented.

## Development

```powershell
npm install
npm run dev
```

## Container

The Dockerfile builds a standalone Next.js image on port 3000. Keep it behind an authenticated private gateway; do not publish the container port directly.

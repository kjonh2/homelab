# Iku Portal Shell — implementation step

## Goal
Build a single reusable portal shell that looks like the Android UI: dark by default, purple accents, rounded cards, consistent labels, and responsive layout that changes density, not identity.

## Shell architecture
- `IkuAppShell`: root frame with app bar, sidebar/drawer, content region, and optional right rail.
- `IkuHeader`: top bar with logo, current section, quick actions, session/avatar menu.
- `IkuSidebar`: same section names everywhere; collapses to drawer on mobile.
- `IkuCard`: standard dark card container for every page section.
- `IkuSectionTitle`: title + subtitle + optional action.
- `IkuButton`: primary, secondary, destructive, ghost variants.
- `IkuStatusChip`: online/offline, verified, warning, admin, sync states.
- `IkuTile`: reusable tile row for devices, downloads, services, and sessions.
- `IkuEmptyState`: consistent empty/loading/error states.
- `IkuMetric`: compact stat block for counts and last-seen data.
- `IkuPageGrid`: responsive grid wrapper that switches 1/2/3/4 columns by breakpoint.

## Route structure
- `/` — Home / landing / authenticated entry
- `/login` — login + MFA
- `/dashboard` — authenticated overview
- `/profile` — personal data, avatar, linked emails, preferences
- `/devices` — registered devices and browser sessions
- `/downloads` — APK / EXE / DEB / AppImage artefacts
- `/services` — cloud, n8n, confy, webui, admin services
- `/sessions` — active sessions and revocation
- `/security` — 2FA, recovery codes, passwords, API tokens
- `/settings` — UI theme, language, notifications, sync
- `/admin` — role-gated admin hub

## Responsive rules
- Mobile: 1 column, drawer or bottom nav, card-first, primary actions visible.
- Tablet: 2 columns, condensed sidebar, smaller card density.
- Desktop: persistent sidebar, 2–3 columns, lists can become tables.
- Widescreen: 3–4 columns and side panels for observability/admin.

## Page composition
### Home
- hero/branding card
- quick status card
- public service shortcuts
- login CTA / session entry card

### Profile
- profile summary card
- avatar + personal info card
- linked accounts/emails card
- preferences card

### Devices
- device list table on desktop, stacked tiles on mobile
- last seen, platform, trust state, revoke action
- browser sessions folded into the same model

### Downloads
- version summary card
- platform tiles with name, version, hash, changelog, download button
- release history / latest build card

### Services
- grid of service cards with status chips
- each service card has name, description, access mode, and open action
- public path-based routes shown alongside subdomain-only admin services

### Sessions
- active session table with device, IP, time, trust, revoke
- current session highlight
- bulk sign-out action in the section header

### Security
- 2FA status card
- recovery codes card
- password change card
- API tokens card with scopes and revoke actions

## Concrete file plan for the next implementation step
1. Create the shared shell and components first.
2. Wire the route layout around the shell.
3. Add one page file per section using the same card primitives.
4. Only after shell parity, connect real auth/session/data sources.

## Suggested file tree to create
- `src/app/layout.tsx`
- `src/app/page.tsx`
- `src/app/login/page.tsx`
- `src/app/dashboard/page.tsx`
- `src/app/profile/page.tsx`
- `src/app/devices/page.tsx`
- `src/app/downloads/page.tsx`
- `src/app/services/page.tsx`
- `src/app/sessions/page.tsx`
- `src/app/security/page.tsx`
- `src/app/settings/page.tsx`
- `src/app/admin/page.tsx`
- `src/app/(portal)/layout.tsx`
- `src/components/iku/IkuAppShell.tsx`
- `src/components/iku/IkuHeader.tsx`
- `src/components/iku/IkuSidebar.tsx`
- `src/components/iku/IkuCard.tsx`
- `src/components/iku/IkuSectionTitle.tsx`
- `src/components/iku/IkuButton.tsx`
- `src/components/iku/IkuStatusChip.tsx`
- `src/components/iku/IkuTile.tsx`
- `src/components/iku/IkuMetric.tsx`
- `src/components/iku/IkuEmptyState.tsx`
- `src/components/iku/IkuPageGrid.tsx`
- `src/styles/iku-theme.css` or `src/app/globals.css`
- `src/lib/navigation.ts`
- `src/lib/portal-sections.ts`
- `src/lib/route-access.ts`

## What should be patched if the shell already exists
- patch the current app entry to use `IkuAppShell`
- patch global styles for dark/purple tokens and card spacing
- patch navigation labels to match the portal structure above
- patch page stubs to use the same card primitives instead of custom layouts
- patch responsive breakpoints to the Iku policy from the docs

# Frontend

> **Status:** Planned · Sprint 8 build target

This directory is a scaffold. The folders exist; the code doesn't yet.

The Next.js 15 rebuild lands in Sprint 8. The legacy React app that lived
here before was a Create React App scaffold from the Windows v1 era and
got removed during the pre-public cleanup. Empty folders + `.gitkeep`
files show the planned architecture so the repo reads as designed, not
abandoned.

## Stack (planned)

| Layer | Tool |
|---|---|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript strict |
| Styling | Tailwind 4 + shadcn/ui |
| Server state | TanStack Query |
| Real-time | WebSocket client with auto-reconnect |
| Charts | Recharts |
| Forms | React Hook Form + Zod |
| Auth | HttpOnly cookie + CSRF token |
| i18n | next-intl (French / Arabic / English with RTL) |
| Testing | Vitest + Testing Library + Playwright |
| Monitoring | Sentry + Web Vitals + OpenTelemetry |
| PWA | Service worker + installable manifest |

## Folder map
```
app/          App Router routes only (page.tsx, layout.tsx, route.ts)
(auth)/     Public route group: login
(dashboard)/  Protected route group: alerts, cameras, analytics, history, settings
api/        Route handlers (healthz, etc.)
components/
ui/         shadcn/ui primitives
features/   Domain components (alerts, cameras, analytics, auth)
layout/     Shell: sidebar, header, language switcher
lib/          Business logic
api/        Typed HTTP client → FastAPI backend
websocket/  Real-time connection manager
auth/       HttpOnly cookie + CSRF helpers
validations/  Zod schemas
i18n/       next-intl config
monitoring/  Sentry + Web Vitals + OTel
security/   CSP builder + DOMPurify wrapper
utils/      Pure helpers (cn, format, env)
hooks/        Client-only React hooks
stores/       Zustand stores
providers/    Context providers (Query, Theme, WebSocket)
types/        Global TypeScript types
messages/     i18n translation files (en.json, fr.json, ar.json)
public/       Static assets (icons, images, fonts, manifest)
tests/        Playwright E2E + MSW mocks (unit tests co-located)
```
## Why the scaffold exists before the code

A reviewer landing on this repo deserves to see what the frontend will
become without digging through a backlog. Empty folders with intent beat
a single "frontend TBD" placeholder. When the build phase starts,
`create-next-app` fills the bootstrap files alongside this structure, and
the `.gitkeep` placeholders disappear folder-by-folder as real code lands.

## Build

Not buildable yet. The Docker Compose `frontend` service is commented out
in `docker-compose.yml` with the same explanation. Both come back online
when the Sprint 8 work begins.

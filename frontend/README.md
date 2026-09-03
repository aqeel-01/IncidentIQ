# IncidentIQ Frontend

React + Vite dashboard for IncidentIQ.

## What’s included

**Foundation (Step 46)**

- App routing (`/` → `/incidents`, `/incidents/:id`, `/system`, `/login`)
- Typed FastAPI client with Bearer auth header support
- Auth session layer (`AuthProvider`, JWT login, token storage, `RequireAuth`)
- Shared loading / error UI and an error boundary
- Dev proxy to the FastAPI backend

**Incident dashboard (Step 47)** — `/incidents`

- Stat cards: active, critical (active), recent (last 24h), total —
  backed by `GET /api/v1/incidents/summary`
- Status and severity breakdowns (click a row to filter)
- Filterable, paginated incident table: title, severity, status,
  occurrence count, started/ended time, environment
- Filters, page, page size, and project ID are kept in the URL
  (`?project=1&status=OPEN&severity=CRITICAL&page=2`), so views are
  shareable and survive refresh
- Project ID is remembered in `localStorage` between visits

**Incident investigation (Step 48)** — `/incidents/:id`

- Summary and key timeline markers
- Chronological timeline plus dedicated errors, metrics, and deployments views
- Structured evidence, evidence quality, and evidence chain
- Persisted RCA, ranked hypotheses, and verification steps
- Real investigation lifecycle: start/re-run, progress polling, failure state,
  and automatic result refresh on completion
- Uses the incident, timeline, evidence, investigation, and RCA APIs directly;
  unavailable backend results render explicit empty/pending states

**Evidence visualization (Step 49)**

- Renders the backend evidence graph in readable lanes:
  deployment → anomaly → error → service → incident
- Shows all available graph nodes even when a complex incident branches
- Click any node to inspect its type, confidence, timestamp, underlying event
  reference, and linked evidence source details
- Click any relationship to inspect its direction, confidence, and backend
  reasoning
- The raw evidence cards, stance, source, confidence, evidence chain, and
  quality score remain available alongside the graph

**Connector management (Step 50)** — `/connectors`

- Create, update, delete, enable, and disable configured connectors
- Test connection against the existing connector abstraction
- Credentials are write-only: encrypted at rest and never returned by the API
- Supports Prometheus, OpenSearch, Elasticsearch, GitHub, Azure DevOps, and
  database connectors

## Prerequisites

- Node.js 20+
- Backend API running at `http://127.0.0.1:8000` (default)

## Quick start

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:5173

In development, Vite proxies `/api` and `/health` to
`VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8000`).

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Local development server |
| `npm run build` | Typecheck + production build |
| `npm run preview` | Preview the production build |
| `npm run typecheck` | TypeScript only |

## Architecture notes

- `src/api` — HTTP client, typed resources, `ApiError`
- `src/auth` — JWT session context, `/auth/me` restore, and token storage
- `src/routes` — path helpers and router
- `src/hooks/useAsync.ts` — loading/error state helper for fetches
  (`keepPreviousData` avoids table flicker while paging)
- `src/features/incidents` — dashboard constants and the URL-synced
  filter hook (`useIncidentFilters`)
- `src/components/incidents` — stat cards, badges, filter bar, table,
  pagination, breakdown bars
- `src/components/investigation` — timeline, signals, evidence, RCA,
  hypotheses, verification, and investigation progress
- `src/pages` — route pages including connectors management

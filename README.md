# IncidentIQ

AI-powered production incident investigation and Root Cause Analysis (RCA) platform.

IncidentIQ collects data from multiple sources, performs deterministic
preprocessing and correlation, builds a structured **evidence package**, and
uses an AI model to produce a ranked, evidence-backed root-cause analysis.

> The differentiator is not "an LLM reads logs." IncidentIQ does the expensive
> deterministic investigation first, then gives the AI a high-quality structured
> representation so it can *reason* rather than blindly search raw logs.

## Architecture (target)

```text
Sources → Connectors → Canonical Events → Normalization → Deduplication
→ Error Grouping → Anomaly Detection → Correlation → Evidence Engine
→ Evidence Package → AI Router → RCA Engine → Investigation Report
```

## Repository layout

```text
backend/          FastAPI backend application
  app/
    core/         Configuration, logging, health checks
    api/          HTTP API layer (routers + routes)
    domain/       Provider-independent domain schemas and services
      events.py   Canonical event models (LogEvent, MetricEvent, …)
      ingestion.py Event ingestion service (validate → persist)
      uploads.py  Log upload validation and streaming persistence
    parsing/      Log format detection, incremental parsers, manual field mapping
    normalization/ Log field + message pattern normalization
    fingerprinting.py Deterministic SHA-256 event fingerprints
    db/           Declarative base, async engine, session management
      models/     Core ORM models (organizations, users, projects, …)
  alembic/        Database migrations (async Alembic environment)
frontend/         React + Vite web dashboard
infrastructure/   Docker Compose and deployment assets
docs/             Project documentation
tests/            Test suite (pytest)
```

## Prerequisites

- Python 3.11+ (developed against 3.12)
- Docker (optional, for containerized runs)

## Quick start (local)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 2. Install the backend with dev tooling
pip install -e ".[dev]"

# 3. Configure the environment
cp .env.example .env   # Windows: copy .env.example .env

# 4. Apply database migrations (PostgreSQL must be running)
alembic upgrade head

# 5. Run the API
uvicorn app.main:app --reload --app-dir backend
```

The API is then available at http://localhost:8000
(interactive docs at http://localhost:8000/docs).

### Frontend (dashboard)

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The dashboard runs at http://localhost:5173 and proxies `/api` + `/health` to
the FastAPI backend. The incident dashboard (`/incidents`) shows active,
critical, and recent counts, status/severity breakdowns, and a filterable,
paginated incident table. Incident detail pages show the live investigation
timeline, errors, metrics, deployments, evidence, RCA, hypotheses, and
verification steps. Evidence is visualized as a readable deployment → anomaly
→ error → service → incident graph with inspectable source details. See
[`frontend/README.md`](frontend/README.md).

- `GET /api/v1/incidents/summary?project_id=…` — dashboard aggregate counts
  (active, critical-active, recent within `recent_hours`, by status/severity).
- `GET /api/v1/investigations/by-incident/{id}/latest` — latest investigation
  job and progress for an incident.
- `GET /api/v1/rca/incidents/{id}/latest` — latest persisted RCA result,
  including hypotheses and verification steps.
- Connector management (`/connectors` UI and `/api/v1/connectors`): create,
  update, delete, enable, disable, and test connections. Stored credentials are
  encrypted and never returned by the API.
- Authentication (`POST /api/v1/auth/login`, `GET /api/v1/auth/me`) issues JWT
  access tokens. Project access is authorized with roles `ADMIN`, `ENGINEER`,
  and `VIEWER`. First-time setup is `POST /api/v1/auth/bootstrap`.

Health, login, and bootstrap stay unauthenticated (bootstrap is disabled by
default in production). Auth and upload endpoints are rate-limited per client
IP. All other `/api/v1` routes require a Bearer token and a project membership
at the required role. Logs and connector probe details are scrubbed so
credentials and production secrets are not emitted.

### Health endpoints

- `GET /health` — liveness; confirms the API process is up.
- `GET /health/ready` — readiness; verifies required infrastructure
  (PostgreSQL, Redis). Returns `503` when a required dependency is unavailable.
- `GET /metrics` — Prometheus metrics (API latency/errors, investigation
  duration, AI latency, Celery queue size, connector/RCA failures). Scrapable
  without running an external Prometheus server; Prometheus is not required
  for local startup.
- `POST /api/v1/logs/upload` — stream a log file upload (`.log`, `.txt`,
  `.json`, `.jsonl`, `.csv`); returns a `job_id` for ingestion tracking.

## Running with Docker

Compose profiles live in [`infrastructure/docker-compose.yml`](infrastructure/docker-compose.yml).
See [`infrastructure/README.md`](infrastructure/README.md) for ports and first-run steps.

```bash
# Minimal: FastAPI + PostgreSQL + Redis + Ollama (+ Celery worker)
# No cloud services required (AI_MODE=local).
docker compose -f infrastructure/docker-compose.yml --profile minimal up --build

# Apply migrations (first run)
docker compose -f infrastructure/docker-compose.yml --profile minimal exec api \
  alembic upgrade head

# Pull the default local model once
docker compose -f infrastructure/docker-compose.yml --profile minimal exec ollama \
  ollama pull llama3.2:1b

# Full: minimal + OpenSearch + Prometheus + Grafana + Alertmanager
docker compose -f infrastructure/docker-compose.yml \
  --env-file infrastructure/full.env --profile full up --build
```

## Database & migrations

PostgreSQL is accessed asynchronously via SQLAlchemy (`asyncpg` driver). The
engine is created once per application in the lifespan and exposed through the
`get_db` dependency (`backend/app/db/session.py`). Sync DSNs (e.g.
`postgresql://…`) are automatically normalized to the async driver.

Migrations are managed with Alembic. The migration environment reads the
database URL and metadata from application settings — no URL/secrets in
`alembic.ini`.

```bash
alembic upgrade head                         # apply migrations
alembic revision --autogenerate -m "message" # create a migration from models
alembic downgrade -1                         # roll back one revision
```

See [`backend/alembic/README.md`](backend/alembic/README.md).

### Core models

Migration `0002_core_models` defines the tenant and investigation entities:
`organizations`, `users`, `projects`, `services`, `incidents`, `events`, and
`error_groups`, with foreign keys, unique constraints, and indexes. Incident
`status` (`OPEN`, `INVESTIGATING`, `IDENTIFIED`, `RESOLVED`, `CLOSED`) and
`severity` (`INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) are string-backed
enums.

Migration `0013_project_memberships` adds per-project RBAC (`ADMIN`,
`ENGINEER`, `VIEWER`) via `project_memberships`.

Migration `0003_log_uploads` adds the `log_uploads` table for tracking uploaded
log files and their ingestion job status (`QUEUED`, `PROCESSING`, `COMPLETED`,
`FAILED`).

## Testing & quality

```bash
pytest            # run the test suite (uses SQLite for DB-layer tests)
ruff check .      # lint
ruff format .     # format
```

## Configuration

All configuration is environment-driven. See [`docs/configuration.md`](docs/configuration.md)
and [`.env.example`](.env.example). Secrets (e.g. `GROQ_API_KEY`) must never be
committed — `.env` is git-ignored.

Log uploads are configured via `LOG_UPLOAD_DIR`, `LOG_UPLOAD_MAX_BYTES`, and
`LOG_UPLOAD_CHUNK_BYTES` (see the **Log uploads** section in
[`docs/configuration.md`](docs/configuration.md)).

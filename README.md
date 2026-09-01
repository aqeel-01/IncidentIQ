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
    db/           Declarative base, async engine, session management
  alembic/        Database migrations (async Alembic environment)
frontend/         Web dashboard (added later)
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
cp .env.example .env   # then edit as needed

# 4. Run the API
uvicorn app.main:app --reload --app-dir backend
```

The API is then available at http://localhost:8000
(interactive docs at http://localhost:8000/docs).

### Health endpoints

- `GET /health` — liveness; confirms the API process is up.
- `GET /health/ready` — readiness; verifies required infrastructure
  (PostgreSQL, Redis). Returns `503` when a required dependency is unavailable.

## Running with Docker

```bash
# Minimal environment: API + PostgreSQL + Redis
docker compose -f infrastructure/docker-compose.yml up --build
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

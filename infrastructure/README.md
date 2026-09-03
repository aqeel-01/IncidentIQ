# Docker environments

IncidentIQ ships two Compose profiles under [`docker-compose.yml`](docker-compose.yml).

| Profile | Services | Cloud required? |
| ------- | -------- | --------------- |
| `minimal` | FastAPI (`api`), Celery `worker`, PostgreSQL, Redis, Ollama | No |
| `full` | Everything in `minimal`, plus OpenSearch, Prometheus, Grafana, Alertmanager | No |

## Minimal (local, offline-capable)

```bash
docker compose -f infrastructure/docker-compose.yml --profile minimal up --build
```

Then:

```bash
# schema
docker compose -f infrastructure/docker-compose.yml --profile minimal exec api alembic upgrade head

# pull a local model once (matches compose defaults)
docker compose -f infrastructure/docker-compose.yml --profile minimal exec ollama ollama pull llama3.2:1b
```

| Service | Host port |
| ------- | --------- |
| API / docs | http://localhost:8000 / http://localhost:8000/docs |
| Metrics | http://localhost:8000/metrics |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| Ollama | http://localhost:11434 |

`AI_MODE=local` and `OLLAMA_BASE_URL=http://ollama:11434` are set in Compose so the stack does not need Groq or other cloud AI.

## Full (observability + search)

```bash
docker compose -f infrastructure/docker-compose.yml \
  --env-file infrastructure/full.env \
  --profile full up --build
```

`full.env` points the API at in-compose OpenSearch and Prometheus:

- `OPENSEARCH_URL=http://opensearch:9200`
- `PROMETHEUS_URL=http://prometheus:9090`

| Extra service | Host port |
| ------------- | --------- |
| OpenSearch | http://localhost:9200 |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |
| Grafana | http://localhost:3000 (admin / incidentiq) |

Prometheus scrapes IncidentIQ at `api:8000/metrics`. Grafana is provisioned with a Prometheus datasource and an overview dashboard.

### Alertmanager → IncidentIQ

Webhook target: `http://api:8000/api/v1/alerts/prometheus?project_id=1`

After auth bootstrap, put a JWT in [`alertmanager/alertmanager.yml`](alertmanager/alertmanager.yml) under `http_config.authorization.credentials`, then reload Alertmanager.

## Config layout

```
infrastructure/
  docker-compose.yml
  full.env
  prometheus/prometheus.yml
  alertmanager/alertmanager.yml
  grafana/provisioning/...
```

## Notes

- Profiles are explicit: a bare `docker compose up` without `--profile` starts **no** app services.
- Redis is used for readiness and as the Celery broker/result backend.
- OpenSearch runs with security disabled for local development only.
- Frontend remains a host-side Vite app (`cd frontend && npm run dev`); it is not part of these profiles.

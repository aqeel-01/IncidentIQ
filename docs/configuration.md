# Configuration

IncidentIQ is configured entirely through environment variables, loaded and
validated by Pydantic Settings (`backend/app/core/config.py`). In development
they may be provided via a local `.env` file (copy from `.env.example`).

Access configuration through `app.core.config.get_settings()` — never read
`os.environ` directly in application code.

## Precedence

1. Explicit values passed to `Settings(...)` (used in tests)
2. Environment variables
3. Values in `.env`
4. Built-in defaults

Invalid values (unknown enum options, out-of-range numbers, blank required
URLs) fail fast at startup with a clear validation error.

## Application

| Variable       | Default                                              | Description                                             |
| -------------- | ---------------------------------------------------- | ------------------------------------------------------- |
| `APP_ENV`      | `development`                                        | One of `development`, `staging`, `production`, `test`.  |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`        | Comma-separated browser origins allowed to call the API.|

## Infrastructure

| Variable         | Default                                                        | Description                                   |
| ---------------- | ------------------------------------------------------------- | --------------------------------------------- |
| `DATABASE_URL`   | `postgresql://incidentiq:incidentiq@localhost:5432/incidentiq`| PostgreSQL connection string (required).      |
| `REDIS_URL`      | `redis://localhost:6379/0`                                    | Redis connection string (required).           |
| `OPENSEARCH_URL` | _(empty)_                                                     | Optional OpenSearch endpoint.                 |
| `PROMETHEUS_URL` | _(empty)_                                                     | Optional external Prometheus for the connector (not required for `/metrics`). |

Required dependencies (PostgreSQL, Redis) are verified by `GET /health/ready`.
Optional services being unavailable must not make the application unusable.

### Observability

IncidentIQ exposes Prometheus metrics at `GET /metrics` (no auth). An external
Prometheus server can scrape this endpoint, but is **not** required for local
startup or readiness.

| Metric | Type | Meaning |
| ------ | ---- | ------- |
| `incidentiq_http_request_duration_seconds` | histogram | API latency |
| `incidentiq_http_requests_total` | counter | API request count (errors via `status`) |
| `incidentiq_investigation_duration_seconds` | histogram | Investigation job duration |
| `incidentiq_investigation_jobs_total` | counter | Completed/failed investigations |
| `incidentiq_ai_request_duration_seconds` | histogram | AI provider latency |
| `incidentiq_ai_requests_total` | counter | AI calls by outcome |
| `incidentiq_celery_queue_length` | gauge | Celery queue depth (best-effort Redis `LLEN`) |
| `incidentiq_connector_test_failures_total` | counter | Failed connector tests |
| `incidentiq_rca_failures_total` | counter | RCA stage failures |

## AI providers

| Variable               | Default                     | Description                                        |
| ---------------------- | --------------------------- | -------------------------------------------------- |
| `AI_MODE`              | `local`                     | `local`, `cloud`, or `hybrid`.                     |
| `OLLAMA_BASE_URL`      | `http://localhost:11434`    | Ollama server base URL.                            |
| `OLLAMA_MODEL_SMALL`   | _(empty)_                   | Name of the small local model (~1.5B).             |
| `OLLAMA_MODEL_LARGE`   | _(empty)_                   | Name of the large local model (~7B).               |
| `RCA_MODEL`            | `large`                     | Which Ollama model the RCA engine uses: `small`/`large`. |
| `GROQ_API_KEY`         | _(empty)_                   | Groq API key (secret — never commit).              |
| `GROQ_MODEL`           | _(empty)_                   | Groq model name.                                   |
| `CONNECTOR_SECRET_KEY` | _(empty)_                   | Fernet key for connector credential encryption. Required in production. |
| `JWT_SECRET_KEY`       | _(empty)_                   | HMAC secret for user access tokens. Required in production. |
| `JWT_ALGORITHM`        | `HS256`                     | JWT signing algorithm.                             |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `720`              | Access token lifetime in minutes.                  |
| `AUTH_BOOTSTRAP_DISABLED` | _(auto)_                 | Override bootstrap; defaults to disabled in production. |
| `AUTH_LOGIN_RATE_LIMIT` | `10`                       | Max login attempts per IP per window.              |
| `AUTH_BOOTSTRAP_RATE_LIMIT` | `5`                    | Max bootstrap attempts per IP per window.          |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `60`              | Auth rate-limit window.                            |
| `UPLOAD_RATE_LIMIT`    | `30`                        | Max log uploads per IP per window.                 |
| `UPLOAD_RATE_LIMIT_WINDOW_SECONDS` | `60`            | Upload rate-limit window.                          |
| `ALERTMANAGER_MAX_ALERTS_PER_WEBHOOK` | `200`        | Max alerts accepted in one webhook payload.        |

## Connector management

Configured connectors are stored per project. Public settings are returned by
the API; credentials are encrypted at rest with `CONNECTOR_SECRET_KEY` and are
never included in API responses (only the configured secret field names are).
| `AI_ENABLE_FALLBACK`   | `false`                     | Enable provider fallback.                          |
| `AI_FALLBACK_PROVIDER` | `groq`                      | `ollama` or `groq`.                                |
| `RCA_TEMPERATURE`      | `0.1`                       | Sampling temperature, `0.0`–`2.0`.                 |
| `RCA_MAX_TOKENS`       | `2048`                      | Max tokens for RCA generation (> 0).               |

## RCA evaluation

The evaluation framework (`app.domain.rca.eval`) scores RCA outputs on a
synthetic benchmark with known root causes. Metrics:

| Metric | Meaning |
| ------ | ------- |
| RCA accuracy | Primary hypothesis matches gold title/aliases (or correctly abstains) |
| Hypothesis ranking | MRR of gold root cause + Kendall tau vs gold order |
| Evidence grounding | Precision/recall/F1 of cited keys vs gold supporting keys |
| Hallucination rate | Fraction of cited keys not present in the evidence package |
| Confidence calibration | Expected calibration error (ECE) over confidence bins |

Backends for comparison:

| Backend | Provider | Settings |
| ------- | -------- | -------- |
| `local_small` | Ollama | `OLLAMA_MODEL_SMALL`, `RCA_MODEL` unused (forced small) |
| `local_7b` | Ollama | `OLLAMA_MODEL_LARGE` (forced large / ~7B) |
| `groq` | Groq | `GROQ_API_KEY`, `GROQ_MODEL` |

```bash
python -m app.domain.rca.eval --backends local_small,local_7b,groq \
  --output data/rca_eval/results.json
```

Unavailable backends are recorded as per-case errors in the JSON report so
comparisons remain machine-readable.

## Log uploads

| Variable                  | Default           | Description                                      |
| ------------------------- | ----------------- | ------------------------------------------------ |
| `LOG_UPLOAD_DIR`          | `data/uploads`    | Directory for streamed upload files on disk.     |
| `LOG_UPLOAD_MAX_BYTES`    | `104857600` (100MB) | Maximum accepted upload size in bytes.       |
| `LOG_UPLOAD_CHUNK_BYTES`  | `1048576` (1MB)   | Read/write chunk size while streaming uploads.   |

> AI providers are configuration-only at this stage; the provider
> implementations are added in a later step.

## Secrets

Secrets such as `GROQ_API_KEY` must be supplied via the environment or a secret
manager. `.env` is git-ignored; only `.env.example` (with empty secret values)
is committed.

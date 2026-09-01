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

| Variable      | Default        | Description                                             |
| ------------- | -------------- | ------------------------------------------------------- |
| `APP_ENV`     | `development`  | One of `development`, `staging`, `production`, `test`.  |

## Infrastructure

| Variable         | Default                                                        | Description                                   |
| ---------------- | ------------------------------------------------------------- | --------------------------------------------- |
| `DATABASE_URL`   | `postgresql://incidentiq:incidentiq@localhost:5432/incidentiq`| PostgreSQL connection string (required).      |
| `REDIS_URL`      | `redis://localhost:6379/0`                                    | Redis connection string (required).           |
| `OPENSEARCH_URL` | _(empty)_                                                     | Optional OpenSearch endpoint.                 |
| `PROMETHEUS_URL` | _(empty)_                                                     | Optional Prometheus endpoint.                 |

Required dependencies (PostgreSQL, Redis) are verified by `GET /health/ready`.
Optional services being unavailable must not make the application unusable.

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
| `AI_ENABLE_FALLBACK`   | `false`                     | Enable provider fallback.                          |
| `AI_FALLBACK_PROVIDER` | `groq`                      | `ollama` or `groq`.                                |
| `RCA_TEMPERATURE`      | `0.1`                       | Sampling temperature, `0.0`–`2.0`.                 |
| `RCA_MAX_TOKENS`       | `2048`                      | Max tokens for RCA generation (> 0).               |

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

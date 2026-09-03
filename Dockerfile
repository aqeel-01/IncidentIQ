# IncidentIQ backend image.
# Build context is the repository root (needs pyproject.toml + backend/).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md alembic.ini ./
COPY backend ./backend
RUN pip install --upgrade pip && pip install .

# Writable upload dir for the Compose volume mount (LOG_UPLOAD_DIR).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

# PYTHONPATH lets `app.main:app` resolve from the backend package directory.
ENV PYTHONPATH=/app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

"""Centralized application configuration.

All runtime configuration is loaded from environment variables (optionally via a
local ``.env`` file) using Pydantic Settings. This keeps configuration in one
place, provides validation with clear errors, and ensures secrets never live in
source code.

Business logic and providers must read configuration from :func:`get_settings`
rather than accessing ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AIMode = Literal["local", "cloud", "hybrid"]
RCAModelSize = Literal["small", "large"]
FallbackProvider = Literal["ollama", "groq"]


class Settings(BaseSettings):
    """Application settings loaded from the environment.

    Field names map to environment variables case-insensitively, e.g. the
    ``database_url`` field is populated from ``DATABASE_URL``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "IncidentIQ"
    app_version: str = "0.1.0"
    # Comma-separated browser origins allowed to call the API (frontend).
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    # --- Infrastructure ------------------------------------------------------
    # Safe local-development defaults; override per environment.
    database_url: str = "postgresql://incidentiq:incidentiq@localhost:5432/incidentiq"
    redis_url: str = "redis://localhost:6379/0"

    # --- Background workers --------------------------------------------------
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_default_queue: str = "investigation"
    celery_task_max_retries: int = Field(default=3, ge=0, le=20)
    celery_task_retry_backoff_seconds: int = Field(default=60, ge=1, le=3600)
    celery_task_retry_backoff_max_seconds: int = Field(default=600, ge=1, le=86400)

    # Optional services: unset by default so the app remains usable without them.
    opensearch_url: str | None = None
    prometheus_url: str | None = None

    # --- AI providers --------------------------------------------------------
    ai_mode: AIMode = "local"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model_small: str = ""
    ollama_model_large: str = ""

    rca_model: RCAModelSize = "large"

    # Secret: must be provided via environment, never committed.
    groq_api_key: str = ""
    groq_model: str = ""

    ai_enable_fallback: bool = False
    ai_fallback_provider: FallbackProvider = "groq"

    rca_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    rca_max_tokens: int = Field(default=2048, gt=0)
    rca_prompt_version: str = "v1"
    rca_engine_version: str = "1.0"
    rca_min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    rca_confident_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    rca_min_evidence_quality: int = Field(default=30, ge=0, le=100)
    ollama_timeout_seconds: float = Field(default=60.0, gt=0)
    groq_timeout_seconds: float = Field(default=60.0, gt=0)

    # --- Log uploads ---------------------------------------------------------
    log_upload_dir: str = "data/uploads"
    log_upload_max_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    log_upload_chunk_bytes: int = Field(default=1024 * 1024, gt=0)

    # Investigation ingestion chunk size for large event batches.
    investigation_ingest_chunk_size: int = Field(default=1000, ge=1, le=100_000)
    # Cap event/group IDs stored in stage artifacts (counts are always stored).
    investigation_artifact_id_limit: int = Field(default=200, ge=0, le=100_000)

    # --- Authentication -------------------------------------------------------
    # HMAC secret for JWT access tokens. Required in production.
    # When empty in non-production, a deterministic development key is derived.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=60 * 12, ge=5, le=60 * 24 * 30)
    # When true, refuse bootstrap even if the user table is empty.
    # Defaults to true in production via ``resolved_auth_bootstrap_disabled``.
    auth_bootstrap_disabled: bool | None = None

    # --- Rate limiting --------------------------------------------------------
    auth_login_rate_limit: int = Field(default=10, ge=1, le=10_000)
    auth_bootstrap_rate_limit: int = Field(default=5, ge=1, le=10_000)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    upload_rate_limit: int = Field(default=30, ge=1, le=10_000)
    upload_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)

    # --- Connector credential encryption --------------------------------------
    # Fernet key (url-safe base64-encoded 32-byte key). Generate with Fernet.
    # When empty in non-production, a deterministic development key is derived.
    connector_secret_key: str = ""

    # --- Alert ingestion ------------------------------------------------------
    alertmanager_max_alerts_per_webhook: int = Field(default=200, ge=1, le=10_000)

    # --- Error-group similarity ------------------------------------------------
    error_similarity_high_confidence_min: float = Field(default=0.92, ge=0.0, le=1.0)
    error_similarity_possible_match_min: float = Field(default=0.75, ge=0.0, le=1.0)

    # --- Similar incident retrieval --------------------------------------------
    incident_similarity_min_score: float = Field(default=0.55, ge=0.0, le=1.0)
    incident_similarity_max_results: int = Field(default=5, ge=1, le=50)

    # --- Metric anomaly detection ----------------------------------------------
    metric_anomaly_window_size: int = Field(default=20, ge=2, le=10_000)
    metric_anomaly_min_points: int = Field(default=5, ge=2, le=10_000)
    metric_anomaly_z_score_threshold: float = Field(default=2.5, gt=0)
    metric_anomaly_percentage_change_threshold: float = Field(default=50.0, ge=0)
    metric_anomaly_percentile_low_threshold: float = Field(default=5.0, ge=0, le=100)
    metric_anomaly_percentile_high_threshold: float = Field(default=95.0, ge=0, le=100)
    metric_anomaly_min_stddev: float = Field(default=1e-9, gt=0)

    # --- Temporal correlation --------------------------------------------------
    correlation_deployment_to_error_max_lag_minutes: int = Field(
        default=120,
        gt=0,
    )
    correlation_metric_anomaly_to_error_max_lag_minutes: int = Field(
        default=30,
        gt=0,
    )
    correlation_error_to_alert_max_lag_minutes: int = Field(
        default=15,
        gt=0,
    )
    correlation_min_score: float = Field(default=0.1, ge=0.0, le=1.0)

    # --- Deployment correlation -----------------------------------------------
    deployment_correlation_lookback_hours: int = Field(default=24, gt=0)
    deployment_correlation_min_relationship_score: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
    )

    # --- Service correlation ---------------------------------------------------
    service_correlation_trace_to_error_max_lag_minutes: int = Field(
        default=5,
        gt=0,
    )
    service_correlation_upstream_max_lag_minutes: int = Field(default=15, gt=0)
    service_correlation_min_score: float = Field(default=0.2, ge=0.0, le=1.0)
    service_correlation_same_service_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
    )
    service_correlation_temporal_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    service_correlation_dependency_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    service_correlation_trace_weight: float = Field(default=0.3, ge=0.0, le=1.0)

    @field_validator("error_similarity_high_confidence_min")
    @classmethod
    def _high_confidence_above_possible(cls, value: float, info) -> float:
        possible = info.data.get("error_similarity_possible_match_min")
        if possible is not None and value <= possible:
            msg = "error_similarity_high_confidence_min must be > possible_match_min"
            raise ValueError(msg)
        return value

    @field_validator("metric_anomaly_min_points")
    @classmethod
    def _metric_anomaly_min_points_within_window(cls, value: int, info) -> int:
        window = info.data.get("metric_anomaly_window_size")
        if window is not None and value > window:
            msg = "metric_anomaly_min_points must be <= metric_anomaly_window_size"
            raise ValueError(msg)
        return value

    @field_validator("metric_anomaly_percentile_high_threshold")
    @classmethod
    def _metric_anomaly_percentile_bounds(cls, value: float, info) -> float:
        low = info.data.get("metric_anomaly_percentile_low_threshold")
        if low is not None and value <= low:
            msg = (
                "metric_anomaly_percentile_high_threshold must be > "
                "metric_anomaly_percentile_low_threshold"
            )
            raise ValueError(msg)
        return value

    @field_validator("database_url", "redis_url")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def resolved_auth_bootstrap_disabled(self) -> bool:
        if self.auth_bootstrap_disabled is not None:
            return self.auth_bootstrap_disabled
        return self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Caching avoids re-parsing the environment on every request. Tests that need
    fresh settings can call ``get_settings.cache_clear()``.
    """

    return Settings()

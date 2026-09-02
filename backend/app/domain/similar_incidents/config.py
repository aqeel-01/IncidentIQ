"""Configuration for similar incident retrieval."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import Settings


class SimilarIncidentRetrievalConfig(BaseModel):
    """Thresholds and limits for historical incident similarity."""

    model_config = ConfigDict(frozen=True)

    min_score: float = Field(default=0.55, ge=0.0, le=1.0)
    max_results: int = Field(default=5, ge=1, le=50)
    title_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    embedding_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    fingerprint_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    service_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    environment_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    error_group_weight: float = Field(default=0.10, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> SimilarIncidentRetrievalConfig:
        total = (
            self.title_weight
            + self.embedding_weight
            + self.fingerprint_weight
            + self.service_weight
            + self.environment_weight
            + self.error_group_weight
        )
        if abs(total - 1.0) > 1e-6:
            msg = "similar incident retrieval weights must sum to 1.0"
            raise ValueError(msg)
        return self


def similar_incident_retrieval_config_from_settings(
    settings: Settings,
) -> SimilarIncidentRetrievalConfig:
    return SimilarIncidentRetrievalConfig(
        min_score=settings.incident_similarity_min_score,
        max_results=settings.incident_similarity_max_results,
    )

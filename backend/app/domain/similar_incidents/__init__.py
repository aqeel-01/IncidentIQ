"""Similar historical incident retrieval."""

from app.domain.similar_incidents.config import (
    SimilarIncidentRetrievalConfig,
    similar_incident_retrieval_config_from_settings,
)
from app.domain.similar_incidents.retrieval import SimilarIncidentRetrievalService
from app.domain.similar_incidents.scoring import HISTORICAL_CONTEXT_DISCLAIMER
from app.domain.similar_incidents.types import (
    IncidentSimilarityProfile,
    SimilarIncidentMatch,
)

__all__ = [
    "HISTORICAL_CONTEXT_DISCLAIMER",
    "IncidentSimilarityProfile",
    "SimilarIncidentMatch",
    "SimilarIncidentRetrievalConfig",
    "SimilarIncidentRetrievalService",
    "similar_incident_retrieval_config_from_settings",
]

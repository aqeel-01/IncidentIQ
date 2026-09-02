"""Provider profiles for search index connectors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchConnectorProfile:
    """Provider-specific labels used by :class:`SearchIndexConnector`."""

    source_prefix: str
    source_type: str
    system_name: str


OPENSEARCH_PROFILE = SearchConnectorProfile(
    source_prefix="opensearch",
    source_type="opensearch",
    system_name="opensearch",
)

ELASTICSEARCH_PROFILE = SearchConnectorProfile(
    source_prefix="elasticsearch",
    source_type="elasticsearch",
    system_name="elasticsearch",
)

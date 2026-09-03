"""Domain service for managing project connector configurations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import (
    ConnectionTestResult,
    ConnectorConnectionError,
    ConnectorType,
    default_connector_registry,
)
from app.core.config import Settings, get_settings
from app.core.metrics import observe_connector_test_failure
from app.core.security import sanitize_error_message, secrets_from_settings
from app.db.models.configured_connector import ConfiguredConnector
from app.db.models.project import Project
from app.domain.connectors.config import (
    ConnectorConfigError,
    build_connector_config,
    configured_credential_keys,
    merge_credentials,
    public_settings,
    secret_fields_for,
)
from app.domain.connectors.secrets import (
    ConnectorCredentialError,
    decrypt_credentials,
    encrypt_credentials,
)


class ConnectorManagementError(ValueError):
    """Raised for invalid connector management operations."""


@dataclass(frozen=True, slots=True)
class ConnectorRecord:
    """Public view of a configured connector (no credential values)."""

    id: int
    project_id: int
    name: str
    connector_type: ConnectorType
    enabled: bool
    settings: dict[str, Any]
    configured_credentials: list[str]
    last_tested_at: datetime | None
    last_test_success: bool | None
    last_test_detail: str | None
    created_at: datetime
    updated_at: datetime


class ConnectorManagementService:
    """Create, update, enable/disable, and test configured connectors."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        registry=None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._registry = registry or default_connector_registry()

    async def list_for_project(self, project_id: int) -> list[ConnectorRecord]:
        await self._require_project(project_id)
        rows = (
            (
                await self._session.execute(
                    select(ConfiguredConnector)
                    .where(ConfiguredConnector.project_id == project_id)
                    .order_by(
                        ConfiguredConnector.name.asc(), ConfiguredConnector.id.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [self._to_record(row) for row in rows]

    async def get(self, connector_id: int) -> ConnectorRecord | None:
        row = await self._session.get(ConfiguredConnector, connector_id)
        if row is None:
            return None
        return self._to_record(row)

    async def create(
        self,
        *,
        project_id: int,
        name: str,
        connector_type: ConnectorType,
        settings: dict[str, Any],
        credentials: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> ConnectorRecord:
        await self._require_project(project_id)
        self._ensure_type_supported(connector_type)
        await self._ensure_unique_name(project_id, name)

        public = public_settings(settings, connector_type)
        secret_values = {
            key: value
            for key, value in (credentials or {}).items()
            if key in secret_fields_for(connector_type)
        }
        # Validate against the typed connector config before persisting.
        build_connector_config(
            connector_type=connector_type,
            name=name.strip(),
            settings=public,
            credentials=secret_values,
        )

        row = ConfiguredConnector(
            project_id=project_id,
            name=name.strip(),
            connector_type=connector_type.value,
            enabled=enabled,
            settings=public,
            credentials_encrypted=encrypt_credentials(self._settings, secret_values),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_record(row)

    async def update(
        self,
        connector_id: int,
        *,
        name: str | None = None,
        settings: dict[str, Any] | None = None,
        credentials: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> ConnectorRecord:
        row = await self._require_connector(connector_id)
        connector_type = ConnectorType(row.connector_type)

        if name is not None and name.strip() != row.name:
            await self._ensure_unique_name(
                row.project_id, name.strip(), exclude_id=row.id
            )
            row.name = name.strip()

        next_settings = (
            public_settings(settings, connector_type)
            if settings is not None
            else dict(row.settings or {})
        )
        existing_credentials = decrypt_credentials(
            self._settings,
            row.credentials_encrypted,
        )
        next_credentials = merge_credentials(existing_credentials, credentials)

        build_connector_config(
            connector_type=connector_type,
            name=row.name,
            settings=next_settings,
            credentials=next_credentials,
        )

        row.settings = next_settings
        row.credentials_encrypted = encrypt_credentials(
            self._settings,
            next_credentials,
        )
        if enabled is not None:
            row.enabled = enabled

        await self._session.flush()
        await self._session.refresh(row)
        return self._to_record(row)

    async def delete(self, connector_id: int) -> None:
        row = await self._require_connector(connector_id)
        await self._session.delete(row)
        await self._session.flush()

    async def set_enabled(self, connector_id: int, *, enabled: bool) -> ConnectorRecord:
        row = await self._require_connector(connector_id)
        row.enabled = enabled
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_record(row)

    async def test_connection(self, connector_id: int) -> ConnectionTestResult:
        row = await self._require_connector(connector_id)
        connector_type = ConnectorType(row.connector_type)
        credentials = decrypt_credentials(self._settings, row.credentials_encrypted)
        config = build_connector_config(
            connector_type=connector_type,
            name=row.name,
            settings=dict(row.settings or {}),
            credentials=credentials,
        )
        connector = self._registry.create(config)
        try:
            result = await connector.test_connection()
        except ConnectorConnectionError as exc:
            result = ConnectionTestResult(
                connector_type=connector_type,
                name=row.name,
                success=False,
                detail=sanitize_error_message(
                    str(exc),
                    secrets=secrets_from_settings(self._settings),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surface probe failures to the API
            result = ConnectionTestResult(
                connector_type=connector_type,
                name=row.name,
                success=False,
                detail=sanitize_error_message(
                    str(exc),
                    secrets=secrets_from_settings(self._settings),
                ),
            )

        safe_detail = sanitize_error_message(
            result.detail,
            secrets=secrets_from_settings(self._settings),
        )
        result = ConnectionTestResult(
            connector_type=result.connector_type,
            name=result.name,
            success=result.success,
            detail=safe_detail,
            tested_at=result.tested_at,
        )
        row.last_tested_at = datetime.now(UTC)
        row.last_test_success = result.success
        row.last_test_detail = result.detail
        await self._session.flush()
        if not result.success:
            observe_connector_test_failure(connector_type.value)
        return result

    def _to_record(self, row: ConfiguredConnector) -> ConnectorRecord:
        connector_type = ConnectorType(row.connector_type)
        try:
            credentials = decrypt_credentials(self._settings, row.credentials_encrypted)
        except ConnectorCredentialError:
            credentials = {}
        return ConnectorRecord(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            connector_type=connector_type,
            enabled=row.enabled,
            settings=public_settings(dict(row.settings or {}), connector_type),
            configured_credentials=configured_credential_keys(credentials),
            last_tested_at=row.last_tested_at,
            last_test_success=row.last_test_success,
            last_test_detail=row.last_test_detail,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _require_project(self, project_id: int) -> Project:
        project = await self._session.get(Project, project_id)
        if project is None:
            msg = f"project {project_id} not found"
            raise LookupError(msg)
        return project

    async def _require_connector(self, connector_id: int) -> ConfiguredConnector:
        row = await self._session.get(ConfiguredConnector, connector_id)
        if row is None:
            msg = f"connector {connector_id} not found"
            raise LookupError(msg)
        return row

    async def _ensure_unique_name(
        self,
        project_id: int,
        name: str,
        *,
        exclude_id: int | None = None,
    ) -> None:
        query = select(ConfiguredConnector.id).where(
            ConfiguredConnector.project_id == project_id,
            ConfiguredConnector.name == name.strip(),
        )
        if exclude_id is not None:
            query = query.where(ConfiguredConnector.id != exclude_id)
        existing = (await self._session.execute(query)).scalar_one_or_none()
        if existing is not None:
            msg = f"connector name {name!r} already exists in project {project_id}"
            raise ConnectorManagementError(msg)

    def _ensure_type_supported(self, connector_type: ConnectorType) -> None:
        if not self._registry.is_registered(connector_type):
            msg = f"connector type {connector_type.value!r} is not supported"
            raise ConnectorManagementError(msg)


__all__ = [
    "ConnectorConfigError",
    "ConnectorCredentialError",
    "ConnectorManagementError",
    "ConnectorManagementService",
    "ConnectorRecord",
]

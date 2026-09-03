"""Configured connector management API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SettingsDep, require_project_role
from app.connectors.types import ConnectionTestResult, ConnectorType
from app.db.models.enums import ProjectRole
from app.db.session import get_db
from app.domain.connectors import (
    ConnectorConfigError,
    ConnectorCredentialError,
    ConnectorManagementError,
    ConnectorManagementService,
    ConnectorRecord,
    secret_fields_for,
)

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]

_MAX_CONNECTOR_MAPPING_KEYS = 40
_MAX_CONNECTOR_FIELD_NAME = 100
_MAX_CONNECTOR_FIELD_VALUE = 8_000


def _validate_bounded_mapping(value: dict[str, Any]) -> dict[str, Any]:
    if len(value) > _MAX_CONNECTOR_MAPPING_KEYS:
        msg = f"at most {_MAX_CONNECTOR_MAPPING_KEYS} fields are allowed"
        raise ValueError(msg)
    for key, item in value.items():
        if len(str(key)) > _MAX_CONNECTOR_FIELD_NAME:
            msg = "field name is too long"
            raise ValueError(msg)
        if isinstance(item, str) and len(item) > _MAX_CONNECTOR_FIELD_VALUE:
            msg = "field value is too long"
            raise ValueError(msg)
    return value


async def _authorize_connector(
    *,
    session: AsyncSession,
    settings,
    user,
    connector_id: int,
    minimum_role: ProjectRole,
) -> ConnectorRecord:
    record = await ConnectorManagementService(session).get(connector_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"connector {connector_id} not found",
        )
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=record.project_id,
        minimum_role=minimum_role,
    )
    return record


class ConnectorResponse(BaseModel):
    id: int
    project_id: int
    name: str
    connector_type: ConnectorType
    enabled: bool
    settings: dict[str, Any]
    configured_credentials: list[str]
    last_tested_at: datetime | None = None
    last_test_success: bool | None = None
    last_test_detail: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


class ConnectorListResponse(BaseModel):
    items: list[ConnectorResponse]
    total: int

    model_config = ConfigDict(frozen=True)


class CreateConnectorRequest(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=255)
    connector_type: ConnectorType
    settings: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("settings", "credentials")
    @classmethod
    def _bounded_maps(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_bounded_mapping(value)


class UpdateConnectorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    settings: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    enabled: bool | None = None

    @field_validator("settings", "credentials")
    @classmethod
    def _bounded_maps(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if value is None:
            return None
        return _validate_bounded_mapping(value)


class ConnectorTypeInfo(BaseModel):
    connector_type: ConnectorType
    label: str
    secret_fields: list[str]
    setting_fields: list[str]

    model_config = ConfigDict(frozen=True)


class ConnectorTypesResponse(BaseModel):
    items: list[ConnectorTypeInfo]

    model_config = ConfigDict(frozen=True)


class ConnectionTestResponse(BaseModel):
    connector_id: int
    connector_type: ConnectorType
    name: str
    success: bool
    detail: str
    tested_at: datetime
    connector: ConnectorResponse

    model_config = ConfigDict(frozen=True)


_TYPE_LABELS: dict[ConnectorType, str] = {
    ConnectorType.PROMETHEUS: "Prometheus",
    ConnectorType.OPENSEARCH: "OpenSearch",
    ConnectorType.ELASTICSEARCH: "Elasticsearch",
    ConnectorType.GITHUB: "GitHub",
    ConnectorType.AZURE_DEVOPS: "Azure DevOps",
    ConnectorType.DATABASE: "Database",
}

_SETTING_HINTS: dict[ConnectorType, list[str]] = {
    ConnectorType.PROMETHEUS: [
        "base_url",
        "timeout_seconds",
        "username",
        "verify_tls",
        "service",
        "environment",
    ],
    ConnectorType.OPENSEARCH: [
        "base_url",
        "index",
        "timeout_seconds",
        "username",
        "verify_tls",
        "timestamp_field",
        "message_field",
        "service_field",
        "environment_field",
        "severity_field",
    ],
    ConnectorType.ELASTICSEARCH: [
        "base_url",
        "index",
        "timeout_seconds",
        "username",
        "verify_tls",
        "timestamp_field",
        "message_field",
        "service_field",
        "environment_field",
        "severity_field",
    ],
    ConnectorType.GITHUB: [
        "base_url",
        "timeout_seconds",
        "auth_scheme",
        "verify_tls",
        "owner",
        "repository",
        "service",
        "environment",
    ],
    ConnectorType.AZURE_DEVOPS: [
        "organization",
        "base_url",
        "api_version",
        "timeout_seconds",
        "verify_tls",
        "project",
        "repository",
        "service",
        "environment",
    ],
    ConnectorType.DATABASE: [
        "dialect",
        "table",
        "query_timeout_seconds",
        "timestamp_column",
        "message_column",
        "service_column",
        "severity_column",
        "environment_column",
        "default_service",
        "default_environment",
    ],
}


def _to_response(record: ConnectorRecord) -> ConnectorResponse:
    return ConnectorResponse(
        id=record.id,
        project_id=record.project_id,
        name=record.name,
        connector_type=record.connector_type,
        enabled=record.enabled,
        settings=record.settings,
        configured_credentials=record.configured_credentials,
        last_tested_at=record.last_tested_at,
        last_test_success=record.last_test_success,
        last_test_detail=record.last_test_detail,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _raise_management_error(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(
        exc,
        (
            ConnectorManagementError,
            ConnectorConfigError,
            ConnectorCredentialError,
            ValueError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    raise exc


@router.get("/types", response_model=ConnectorTypesResponse)
async def list_connector_types(_user: CurrentUserDep) -> ConnectorTypesResponse:
    items = [
        ConnectorTypeInfo(
            connector_type=connector_type,
            label=_TYPE_LABELS[connector_type],
            secret_fields=sorted(secret_fields_for(connector_type)),
            setting_fields=_SETTING_HINTS[connector_type],
        )
        for connector_type in ConnectorType
    ]
    return ConnectorTypesResponse(items=items)


@router.get("", response_model=ConnectorListResponse)
async def list_connectors(
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    project_id: Annotated[int, Query(description="Project that owns the connectors")],
) -> ConnectorListResponse:
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=project_id,
        minimum_role=ProjectRole.VIEWER,
    )
    service = ConnectorManagementService(session)
    try:
        records = await service.list_for_project(project_id)
    except Exception as exc:  # noqa: BLE001
        _raise_management_error(exc)
        raise
    return ConnectorListResponse(
        items=[_to_response(item) for item in records],
        total=len(records),
    )


@router.post(
    "",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_connector(
    body: CreateConnectorRequest,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> ConnectorResponse:
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=body.project_id,
        minimum_role=ProjectRole.ADMIN,
    )
    service = ConnectorManagementService(session)
    try:
        record = await service.create(
            project_id=body.project_id,
            name=body.name,
            connector_type=body.connector_type,
            settings=body.settings,
            credentials=body.credentials,
            enabled=body.enabled,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        _raise_management_error(exc)
        raise
    return _to_response(record)


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> ConnectorResponse:
    record = await _authorize_connector(
        session=session,
        settings=settings,
        user=user,
        connector_id=connector_id,
        minimum_role=ProjectRole.VIEWER,
    )
    return _to_response(record)


@router.patch("/{connector_id}", response_model=ConnectorResponse)
async def update_connector(
    connector_id: int,
    body: UpdateConnectorRequest,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> ConnectorResponse:
    await _authorize_connector(
        session=session,
        settings=settings,
        user=user,
        connector_id=connector_id,
        minimum_role=ProjectRole.ADMIN,
    )
    service = ConnectorManagementService(session)
    try:
        record = await service.update(
            connector_id,
            name=body.name,
            settings=body.settings,
            credentials=body.credentials,
            enabled=body.enabled,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        _raise_management_error(exc)
        raise
    return _to_response(record)


@router.delete(
    "/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connector(
    connector_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> None:
    await _authorize_connector(
        session=session,
        settings=settings,
        user=user,
        connector_id=connector_id,
        minimum_role=ProjectRole.ADMIN,
    )
    service = ConnectorManagementService(session)
    try:
        await service.delete(connector_id)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        _raise_management_error(exc)
        raise


@router.post("/{connector_id}/enable", response_model=ConnectorResponse)
async def enable_connector(
    connector_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> ConnectorResponse:
    await _authorize_connector(
        session=session,
        settings=settings,
        user=user,
        connector_id=connector_id,
        minimum_role=ProjectRole.ADMIN,
    )
    service = ConnectorManagementService(session)
    try:
        record = await service.set_enabled(connector_id, enabled=True)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        _raise_management_error(exc)
        raise
    return _to_response(record)


@router.post("/{connector_id}/disable", response_model=ConnectorResponse)
async def disable_connector(
    connector_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> ConnectorResponse:
    await _authorize_connector(
        session=session,
        settings=settings,
        user=user,
        connector_id=connector_id,
        minimum_role=ProjectRole.ADMIN,
    )
    service = ConnectorManagementService(session)
    try:
        record = await service.set_enabled(connector_id, enabled=False)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        _raise_management_error(exc)
        raise
    return _to_response(record)


@router.post("/{connector_id}/test", response_model=ConnectionTestResponse)
async def test_connector(
    connector_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> ConnectionTestResponse:
    await _authorize_connector(
        session=session,
        settings=settings,
        user=user,
        connector_id=connector_id,
        minimum_role=ProjectRole.ADMIN,
    )
    service = ConnectorManagementService(session)
    try:
        result: ConnectionTestResult = await service.test_connection(connector_id)
        record = await service.get(connector_id)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        _raise_management_error(exc)
        raise

    assert record is not None
    return ConnectionTestResponse(
        connector_id=connector_id,
        connector_type=result.connector_type,
        name=result.name,
        success=result.success,
        detail=result.detail,
        tested_at=result.tested_at,
        connector=_to_response(record),
    )

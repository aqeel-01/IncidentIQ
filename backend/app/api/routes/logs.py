"""Log upload API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SettingsDep, require_project_role
from app.db.models.enums import ProjectRole
from app.db.models.log_upload import LogUploadStatus
from app.db.session import get_db
from app.domain.uploads import (
    FileTooLargeError,
    LogUploadService,
    UploadValidationError,
)

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class LogUploadResponse(BaseModel):
    job_id: str = Field(description="Ingestion job identifier for this upload")
    status: LogUploadStatus
    project_id: int
    filename: str
    file_extension: str
    file_size_bytes: int
    content_type: str | None = None


@router.post(
    "/upload",
    response_model=LogUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_log(
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    project_id: Annotated[int, Form(description="Project that owns this upload")],
    file: Annotated[UploadFile, File(description="Log file to ingest")],
) -> LogUploadResponse:
    """Accept a log file upload and queue it for ingestion.

    The file body is streamed to disk in chunks — it is never fully buffered in
    memory. Parsing and event ingestion are handled asynchronously in later
    pipeline steps.
    """

    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=project_id,
        minimum_role=ProjectRole.ENGINEER,
    )

    service = LogUploadService(session, settings)
    try:
        record = await service.create_upload(project_id=project_id, upload=file)
        await session.commit()
    except UploadValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return LogUploadResponse(
        job_id=record.id,
        status=record.status,
        project_id=record.project_id,
        filename=record.original_filename,
        file_extension=record.file_extension,
        file_size_bytes=record.file_size_bytes,
        content_type=record.content_type,
    )

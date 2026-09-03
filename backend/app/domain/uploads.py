"""Safe log file upload handling (validation + streaming persistence)."""

from __future__ import annotations

import uuid
from pathlib import Path, PurePosixPath

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.log_upload import LogUpload, LogUploadStatus
from app.db.models.project import Project

ALLOWED_EXTENSIONS = frozenset({".log", ".txt", ".json", ".jsonl", ".csv"})
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "text/csv",
        "application/json",
        "application/x-ndjson",
        "application/octet-stream",
    }
)


class UploadValidationError(ValueError):
    """Raised when filename or file type validation fails."""


class FileTooLargeError(ValueError):
    """Raised when an upload exceeds the configured size limit."""


def validate_upload_filename(filename: str | None) -> tuple[str, str]:
    """Return a safe basename and lowercase extension.

    Rejects path traversal, null bytes, missing names, and unsupported types.
    """

    if filename is None or not filename.strip():
        raise UploadValidationError("filename is required")

    # Normalize separators and keep only the final path segment.
    basename = PurePosixPath(filename.replace("\\", "/")).name
    if not basename or basename in {".", ".."}:
        raise UploadValidationError("invalid filename")
    if "\x00" in basename:
        raise UploadValidationError("invalid filename")

    suffix = Path(basename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(f"unsupported file type: {suffix or '(none)'}")

    return basename, suffix


def validate_upload_content_type(content_type: str | None) -> str | None:
    """Reject unexpected Content-Type values when a client supplies one."""

    if content_type is None or not content_type.strip():
        return None
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_CONTENT_TYPES:
        raise UploadValidationError(f"unsupported content type: {media_type}")
    return media_type


def resolve_upload_destination(
    upload_root: str | Path,
    project_id: int,
    stored_filename: str,
) -> Path:
    """Build a destination path and ensure it stays under the upload root."""

    if (
        not stored_filename
        or stored_filename in {".", ".."}
        or "/" in stored_filename
        or "\\" in stored_filename
        or Path(stored_filename).name != stored_filename
    ):
        msg = "invalid stored filename"
        raise UploadValidationError(msg)

    root = Path(upload_root).expanduser().resolve(strict=False)
    destination = (root / str(project_id) / stored_filename).resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError as exc:
        msg = "upload destination escapes upload root"
        raise UploadValidationError(msg) from exc
    return destination


async def stream_save_upload(
    upload: UploadFile,
    destination: Path,
    *,
    max_bytes: int,
    chunk_bytes: int,
) -> int:
    """Stream ``upload`` to ``destination`` in chunks without loading it all."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(chunk_bytes)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise FileTooLargeError(
                        f"file exceeds maximum size of {max_bytes} bytes"
                    )
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return total


class LogUploadService:
    """Accept uploads, persist files on disk, and record ingestion jobs."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def create_upload(
        self,
        *,
        project_id: int,
        upload: UploadFile,
    ) -> LogUpload:
        if not await self._project_exists(project_id):
            raise LookupError(f"project {project_id} not found")

        original_filename, extension = validate_upload_filename(upload.filename)
        content_type = validate_upload_content_type(upload.content_type)
        job_id = str(uuid.uuid4())
        stored_filename = f"{job_id}{extension}"
        destination = resolve_upload_destination(
            self._settings.log_upload_dir,
            project_id,
            stored_filename,
        )

        size = await stream_save_upload(
            upload,
            destination,
            max_bytes=self._settings.log_upload_max_bytes,
            chunk_bytes=self._settings.log_upload_chunk_bytes,
        )

        record = LogUpload(
            id=job_id,
            project_id=project_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_extension=extension,
            content_type=content_type,
            file_size_bytes=size,
            status=LogUploadStatus.QUEUED,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def _project_exists(self, project_id: int) -> bool:
        result = await self._session.execute(
            select(Project.id).where(Project.id == project_id)
        )
        return result.scalar_one_or_none() is not None

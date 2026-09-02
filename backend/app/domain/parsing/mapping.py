"""Manual field mapping for uploaded logs when automatic detection fails."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

# Canonical fields users may map onto source column names.
MAPPABLE_FIELDS = frozenset(
    {
        "timestamp",
        "severity",
        "message",
        "service",
        "host",
        "request_id",
        "trace_id",
    }
)


class FieldMappingValidationError(ValueError):
    """Raised when a manual field mapping fails validation."""


class ManualFieldMapping(BaseModel):
    """Map canonical log fields to source column names.

    Example::

        ManualFieldMapping(
            timestamp="timestamp_column",
            severity="level_column",
            message="message_column",
            service="service_column",
        )
    """

    model_config = ConfigDict(extra="forbid")

    timestamp: str | None = None
    severity: str | None = None
    message: str | None = None
    service: str | None = None
    host: str | None = None
    request_id: str | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def _columns_non_blank(self) -> ManualFieldMapping:
        for field in MAPPABLE_FIELDS:
            value = getattr(self, field)
            if value is not None and not value.strip():
                raise ValueError(f"{field} column name must not be blank")
        return self

    def defined_mappings(self) -> dict[str, str]:
        """Return canonical field -> source column for every mapping provided."""

        return {
            field: column
            for field in MAPPABLE_FIELDS
            if (column := getattr(self, field)) is not None
        }

    def is_empty(self) -> bool:
        return not self.defined_mappings()


def resolve_column(data: dict[str, Any], column: str) -> Any | None:
    """Look up ``column`` in ``data`` with case-insensitive fallback."""

    if column in data:
        return data[column]
    lowered = column.lower()
    for key, value in data.items():
        if key is not None and key.lower() == lowered:
            return value
    return None


def _convert_mapped_value(field: str, value: Any) -> Any:
    from app.domain.parsing.fields import parse_severity, parse_timestamp

    if field == "timestamp":
        return parse_timestamp(value)
    if field == "severity":
        return parse_severity(value)
    if value is None:
        return None
    return str(value)


def extract_manual_fields(
    data: dict[str, Any], mapping: ManualFieldMapping
) -> dict[str, Any]:
    """Extract only the fields explicitly defined in ``mapping``."""

    result: dict[str, Any] = {}
    for field, column in mapping.defined_mappings().items():
        raw = resolve_column(data, column)
        if raw is None:
            continue
        converted = _convert_mapped_value(field, raw)
        if converted is not None:
            result[field] = converted
    return result


def validate_field_mapping(
    mapping: ManualFieldMapping,
    sample_rows: list[dict[str, Any]],
    *,
    require_message: bool = False,
) -> None:
    """Validate ``mapping`` against representative source rows before processing.

    Raises :class:`FieldMappingValidationError` when the mapping is unusable.
    """

    if mapping.is_empty():
        raise FieldMappingValidationError("at least one field mapping is required")

    if not sample_rows:
        raise FieldMappingValidationError(
            "cannot validate mapping without sample rows"
        )

    defined = mapping.defined_mappings()
    errors: list[str] = []

    from app.domain.parsing.fields import parse_severity, parse_timestamp

    for field, column in defined.items():
        if not any(resolve_column(row, column) is not None for row in sample_rows):
            errors.append(f"column {column!r} for {field!r} not found in sample data")

    for field, column in defined.items():
        if field not in {"timestamp", "severity"}:
            continue
        for row in sample_rows:
            raw = resolve_column(row, column)
            if raw is None:
                continue
            if field == "timestamp" and parse_timestamp(raw) is None:
                errors.append(
                    f"column {column!r} contains unparseable timestamp: {raw!r}"
                )
                break
            if field == "severity" and parse_severity(raw) is None:
                errors.append(
                    f"column {column!r} contains unparseable severity: {raw!r}"
                )
                break

    if require_message and "message" in defined:
        column = defined["message"]
        if not any(
            resolve_column(row, column) not in (None, "")
            for row in sample_rows
        ):
            errors.append(f"column {column!r} for message is empty in sample data")

    if errors:
        raise FieldMappingValidationError("; ".join(errors))

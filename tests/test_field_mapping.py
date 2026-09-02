"""Tests for manual field mapping of uploaded logs."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db.models.enums import Severity
from app.domain.parsing import (
    FieldMappingValidationError,
    LogFormat,
    LogParsingPipeline,
    ManualFieldMapping,
    validate_field_mapping,
)
from app.domain.parsing.fields import build_record
from app.domain.parsing.parsers.csv import CsvLogParser


def test_manual_mapping_model_rejects_blank_column() -> None:
    with pytest.raises(ValidationError):
        ManualFieldMapping(message="   ")


def test_validate_rejects_empty_mapping() -> None:
    with pytest.raises(FieldMappingValidationError, match="at least one"):
        validate_field_mapping(ManualFieldMapping(), [{"a": "1"}])


def test_validate_rejects_missing_column() -> None:
    mapping = ManualFieldMapping(message="missing_column")
    with pytest.raises(FieldMappingValidationError, match="not found"):
        validate_field_mapping(mapping, [{"other": "x"}])


def test_validate_rejects_unparseable_timestamp() -> None:
    mapping = ManualFieldMapping(timestamp="ts_col")
    with pytest.raises(FieldMappingValidationError, match="unparseable timestamp"):
        validate_field_mapping(mapping, [{"ts_col": "not-a-date"}])


def test_validate_accepts_valid_mapping() -> None:
    mapping = ManualFieldMapping(
        timestamp="timestamp_column",
        severity="level_column",
        message="message_column",
        service="service_column",
    )
    rows = [
        {
            "timestamp_column": "2026-09-01T12:00:00Z",
            "level_column": "ERROR",
            "message_column": "failed",
            "service_column": "payments-api",
        }
    ]
    validate_field_mapping(mapping, rows)  # must not raise


def test_csv_manual_mapping_extracts_custom_columns() -> None:
    content = (
        "timestamp_column,level_column,message_column,service_column\n"
        "2026-09-01T12:00:00Z,ERROR,connection refused,payments-api\n"
    )
    mapping = ManualFieldMapping(
        timestamp="timestamp_column",
        severity="level_column",
        message="message_column",
        service="service_column",
    )
    record = next(
        CsvLogParser().iter_records(StringIO(content), field_mapping=mapping)
    )

    assert record.severity is Severity.HIGH
    assert record.message == "connection refused"
    assert record.service == "payments-api"
    assert record.timestamp is not None


def test_automatic_parsing_unchanged_without_mapping() -> None:
    data = {
        "timestamp": "2026-09-01T12:00:00Z",
        "level": "INFO",
        "message": "ok",
        "service": "api",
    }
    with_mapping = build_record(
        line_number=1,
        fmt=LogFormat.JSONL,
        data=data,
        raw_data=data,
        field_mapping=None,
    )
    without = build_record(
        line_number=1,
        fmt=LogFormat.JSONL,
        data=data,
        raw_data=data,
    )
    assert with_mapping == without


def test_manual_mapping_overrides_automatic_for_mapped_fields() -> None:
    data = {
        "timestamp": "2026-09-01T12:00:00Z",
        "level": "INFO",
        "message": "ignored",
        "body": "actual message",
    }
    mapping = ManualFieldMapping(message="body")
    record = build_record(
        line_number=1,
        fmt=LogFormat.JSONL,
        data=data,
        raw_data=data,
        field_mapping=mapping,
    )
    assert record.message == "actual message"
    assert record.severity is Severity.INFO


def test_pipeline_validates_mapping_before_processing(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text(
        "timestamp_column,level_column,message_column\n"
        "2026-09-01T12:00:00Z,INFO,ok\n",
        encoding="utf-8",
    )
    pipeline = LogParsingPipeline()
    bad_mapping = ManualFieldMapping(message="does_not_exist")

    with pytest.raises(FieldMappingValidationError):
        list(
            pipeline.iter_parse(
                path, fmt=LogFormat.CSV, field_mapping=bad_mapping
            )
        )


def test_pipeline_parses_with_valid_manual_mapping(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text(
        "timestamp_column,level_column,message_column,service_column\n"
        "2026-09-01T12:00:00Z,CRITICAL,disk full,worker\n",
        encoding="utf-8",
    )
    mapping = ManualFieldMapping(
        timestamp="timestamp_column",
        severity="level_column",
        message="message_column",
        service="service_column",
    )
    records, stats = LogParsingPipeline().parse_file(
        path, fmt=LogFormat.CSV, field_mapping=mapping
    )

    assert stats.records_parsed == 1
    assert records[0].severity is Severity.CRITICAL
    assert records[0].message == "disk full"
    assert records[0].service == "worker"

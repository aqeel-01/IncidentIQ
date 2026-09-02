"""Tests for log format detection and parsing."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC
from io import StringIO
from pathlib import Path
from typing import TextIO

import pytest

from app.db.models.enums import Severity
from app.domain.parsing import (
    LogFormat,
    LogFormatDetector,
    LogParsingPipeline,
    ParserRegistry,
    extract_common_fields,
)
from app.domain.parsing.mapping import ManualFieldMapping
from app.domain.parsing.parsers.csv import CsvLogParser
from app.domain.parsing.parsers.json_format import JsonLogParser
from app.domain.parsing.parsers.jsonl import JsonlLogParser
from app.domain.parsing.parsers.plain_text import PlainTextLogParser
from app.domain.parsing.parsers.structured_text import StructuredTextLogParser
from app.domain.parsing.types import ParsedLogRecord


@pytest.fixture
def pipeline() -> LogParsingPipeline:
    return LogParsingPipeline()


def test_plain_text_parser_extracts_timestamp_severity_message() -> None:
    line = "2026-09-01T12:00:00Z ERROR payments-api connection refused\n"
    parser = PlainTextLogParser()
    record = next(parser.iter_records(StringIO(line)))

    assert record.format is LogFormat.PLAIN_TEXT
    assert record.timestamp is not None
    assert record.timestamp.tzinfo is UTC
    assert record.severity is Severity.HIGH
    assert "connection refused" in (record.message or "")
    assert record.raw_data["line"].startswith("2026-09-01")


def test_structured_text_parser_extracts_fields() -> None:
    line = (
        "timestamp=2026-09-01T12:00:00Z level=INFO service=payments-api "
        "host=node-1 request_id=req-99 message='payment ok'\n"
    )
    record = next(StructuredTextLogParser().iter_records(StringIO(line)))

    assert record.format is LogFormat.STRUCTURED_TEXT
    assert record.severity is Severity.INFO
    assert record.service == "payments-api"
    assert record.host == "node-1"
    assert record.request_id == "req-99"
    assert record.message == "payment ok"


def test_jsonl_parser_maps_aliases() -> None:
    content = (
        '{"@timestamp":"2026-09-01T12:00:01Z","level":"error",'
        '"msg":"timeout","trace_id":"abc","service":"api"}\n'
        '{"time":"2026-09-01T12:00:02Z","severity":"low","message":"ok"}\n'
    )
    records = list(JsonlLogParser().iter_records(StringIO(content)))

    assert len(records) == 2
    assert records[0].severity is Severity.HIGH
    assert records[0].message == "timeout"
    assert records[0].trace_id == "abc"
    assert records[0].service == "api"
    assert records[1].severity is Severity.LOW


def test_json_parser_single_object_and_array() -> None:
    single = '{"timestamp":"2026-09-01T12:00:00Z","message":"one"}'
    record = next(JsonLogParser().iter_records(StringIO(single)))
    assert record.message == "one"

    array = '[{"message":"a"},{"message":"b"}]'
    records = list(JsonLogParser().iter_records(StringIO(array)))
    assert [r.message for r in records] == ["a", "b"]


def test_csv_parser_reads_header_and_rows() -> None:
    content = (
        "timestamp,level,message,service,host,request_id,trace_id\n"
        "2026-09-01T12:00:00Z,INFO,started,payments-api,h1,req-1,tr-1\n"
    )
    records = list(CsvLogParser().iter_records(StringIO(content)))

    assert len(records) == 1
    assert records[0].format is LogFormat.CSV
    assert records[0].severity is Severity.INFO
    assert records[0].message == "started"
    assert records[0].service == "payments-api"
    assert records[0].host == "h1"
    assert records[0].request_id == "req-1"
    assert records[0].trace_id == "tr-1"


def test_detector_identifies_jsonl_from_content(tmp_path: Path) -> None:
    path = tmp_path / "events.log"
    path.write_text(
        '{"message":"a"}\n{"message":"b"}\n',
        encoding="utf-8",
    )
    result = LogFormatDetector().detect("events.log", path.read_text().splitlines())
    assert result.format is LogFormat.JSONL


def test_detector_identifies_csv(tmp_path: Path) -> None:
    result = LogFormatDetector().detect(
        "data.csv",
        ["timestamp,level,message", "2026-09-01T12:00:00Z,INFO,ok"],
    )
    assert result.format is LogFormat.CSV


def test_detector_identifies_structured_text() -> None:
    sample = [
        "level=INFO service=api message=hello host=h1",
        "level=ERROR service=api message=fail host=h2",
    ]
    result = LogFormatDetector().detect("app.log", sample)
    assert result.format is LogFormat.STRUCTURED_TEXT


def test_pipeline_detect_and_parse_file(
    tmp_path: Path, pipeline: LogParsingPipeline
) -> None:
    path = tmp_path / "app.jsonl"
    path.write_text(
        '{"timestamp":"2026-09-01T12:00:00Z","level":"INFO","message":"ok"}\n',
        encoding="utf-8",
    )

    detection = pipeline.detect_file(path)
    assert detection.format is LogFormat.JSONL

    records, stats = pipeline.parse_file(path)
    assert stats.records_parsed == 1
    assert records[0].message == "ok"


def test_extract_common_fields_normalizes_keys() -> None:
    fields = extract_common_fields(
        {
            "@timestamp": "2026-09-01T12:00:00Z",
            "log_level": "CRITICAL",
            "msg": "disk full",
            "application": "worker",
            "hostname": "w-1",
            "correlation_id": "c-9",
            "traceId": "t-9",
        }
    )
    assert fields["severity"] is Severity.CRITICAL
    assert fields["message"] == "disk full"
    assert fields["service"] == "worker"
    assert fields["host"] == "w-1"
    assert fields["request_id"] == "c-9"
    assert fields["trace_id"] == "t-9"
    assert fields["timestamp"] is not None


class _UppercasePlainParser:
    format = LogFormat.PLAIN_TEXT

    def iter_records(
        self,
        handle: TextIO,
        *,
        field_mapping: ManualFieldMapping | None = None,
    ) -> Iterator[ParsedLogRecord]:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip().upper()
            if not text:
                continue
            yield ParsedLogRecord(
                line_number=line_number,
                format=self.format,
                message=text,
                raw_data={"line": text},
            )


def test_registry_allows_custom_parser_without_pipeline_changes(
    tmp_path: Path,
) -> None:
    registry = ParserRegistry()
    registry.register(_UppercasePlainParser())
    pipeline = LogParsingPipeline(registry=registry)

    path = tmp_path / "custom.log"
    path.write_text("hello\n", encoding="utf-8")
    records = list(pipeline.iter_parse(path, fmt=LogFormat.PLAIN_TEXT))
    assert records[0].message == "HELLO"

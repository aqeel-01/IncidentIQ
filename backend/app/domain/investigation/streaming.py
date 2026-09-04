"""Streaming helpers for large-file investigation processing."""

from __future__ import annotations

import io
from collections.abc import Iterable, Iterator
from pathlib import Path

from app.db.models.enums import EventType
from app.domain.fingerprinting import compute_logical_error_fingerprint
from app.domain.normalization import (
    iter_normalize_parsed_records,
    normalize_parsed_record,
)
from app.domain.normalization.types import NormalizedLogRecord
from app.domain.parsing.parsers.plain_text import PlainTextLogParser
from app.domain.parsing.pipeline import LogParsingPipeline
from app.domain.parsing.types import ParsedLogRecord


def iter_parsed_log_sources(
    *,
    log_file_paths: Iterable[str | Path] = (),
    raw_log_lines: Iterable[str] = (),
    parser: LogParsingPipeline | None = None,
    plain_text_parser: PlainTextLogParser | None = None,
) -> Iterator[ParsedLogRecord]:
    """Yield parsed records from files and inline lines without buffering all."""

    pipeline = parser or LogParsingPipeline()
    text_parser = plain_text_parser or PlainTextLogParser()

    for line in raw_log_lines:
        handle = io.StringIO(line if line.endswith("\n") else f"{line}\n")
        yield from text_parser.iter_records(handle)

    for path in log_file_paths:
        yield from pipeline.iter_parse(Path(path))


def iter_normalize_and_deduplicate(
    parsed_records: Iterable[ParsedLogRecord],
    *,
    copy_raw_data: bool = False,
) -> tuple[Iterator[NormalizedLogRecord], dict[str, int]]:
    """Return a lazy normalize+dedupe iterator and a shared counters dict.

    Counters are updated while the iterator is consumed:
    ``parsed``, ``normalized``, ``kept``, ``removed``.
    """

    counters = {"parsed": 0, "normalized": 0, "kept": 0, "removed": 0}
    seen: set[str] = set()

    def _generate() -> Iterator[NormalizedLogRecord]:
        for parsed in parsed_records:
            counters["parsed"] += 1
            normalized = normalize_parsed_record(
                parsed,
                copy_raw_data=copy_raw_data,
            )
            counters["normalized"] += 1
            fingerprint = compute_logical_error_fingerprint(
                event_type=EventType.LOG,
                service=normalized.service,
                severity=normalized.severity,
                normalized_message=normalized.normalized_message,
            )
            if fingerprint in seen:
                counters["removed"] += 1
                continue
            seen.add(fingerprint)
            counters["kept"] += 1
            yield normalized

    return _generate(), counters


def deduplicate_normalized_records(
    records: Iterable[NormalizedLogRecord],
) -> tuple[list[NormalizedLogRecord], int]:
    """Deduplicate normalized records by logical error fingerprint."""

    seen: set[str] = set()
    kept: list[NormalizedLogRecord] = []
    removed = 0
    for record in records:
        fingerprint = compute_logical_error_fingerprint(
            event_type=EventType.LOG,
            service=record.service,
            severity=record.severity,
            normalized_message=record.normalized_message,
        )
        if fingerprint in seen:
            removed += 1
            continue
        seen.add(fingerprint)
        kept.append(record)
    return kept, removed


def chunked(
    iterable: Iterable[NormalizedLogRecord],
    size: int,
) -> Iterator[list[NormalizedLogRecord]]:
    """Yield fixed-size chunks from an iterable without reading everything first."""

    if size < 1:
        msg = "chunk size must be >= 1"
        raise ValueError(msg)
    batch: list[NormalizedLogRecord] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# Re-export for callers that want an explicit normalize stream.
iter_normalize = iter_normalize_parsed_records

"""Log parsing pipeline: detect format and stream-parse files."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from app.domain.parsing.detector import LogFormatDetector
from app.domain.parsing.mapping import (
    ManualFieldMapping,
    validate_field_mapping,
)
from app.domain.parsing.registry import ParserRegistry, default_registry
from app.domain.parsing.types import (
    DetectionResult,
    LogFormat,
    ParsedLogRecord,
    ParseStats,
)

_SAMPLE_BYTES = 16_384


class LogParsingPipeline:
    """Detect log format and parse files incrementally via registered parsers.

    The pipeline never loads the full file into memory: detection reads only a
    bounded prefix, and parsers consume the file line-by-line (JSON loads one
    document — suitable for single-object or moderate array files).
    """

    def __init__(
        self,
        registry: ParserRegistry | None = None,
        detector: LogFormatDetector | None = None,
    ) -> None:
        self._registry = registry or default_registry()
        self._detector = detector or LogFormatDetector()

    def detect_file(
        self, path: Path, *, filename: str | None = None
    ) -> DetectionResult:
        sample = self._read_sample_lines(path)
        return self._detector.detect(filename or path.name, sample)

    def iter_parse(
        self,
        path: Path,
        *,
        fmt: LogFormat | None = None,
        filename: str | None = None,
        field_mapping: ManualFieldMapping | None = None,
    ) -> Iterator[ParsedLogRecord]:
        resolved = fmt or self.detect_file(path, filename=filename).format
        if field_mapping is not None and not field_mapping.is_empty():
            sample_rows = self._collect_sample_rows(path, resolved)
            validate_field_mapping(field_mapping, sample_rows)

        parser = self._registry.get(resolved)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            yield from parser.iter_records(handle, field_mapping=field_mapping)

    def parse_file(
        self,
        path: Path,
        *,
        fmt: LogFormat | None = None,
        filename: str | None = None,
        field_mapping: ManualFieldMapping | None = None,
    ) -> tuple[list[ParsedLogRecord], ParseStats]:
        resolved = fmt or self.detect_file(path, filename=filename).format
        records = list(
            self.iter_parse(
                path,
                fmt=resolved,
                filename=filename,
                field_mapping=field_mapping,
            )
        )
        return records, ParseStats(format=resolved, records_parsed=len(records))

    def _collect_sample_rows(
        self, path: Path, fmt: LogFormat, max_rows: int = 5
    ) -> list[dict]:
        parser = self._registry.get(fmt)
        rows: list[dict] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for record in parser.iter_records(handle):
                rows.append(dict(record.raw_data))
                if len(rows) >= max_rows:
                    break
        return rows

    @staticmethod
    def _read_sample_lines(path: Path, max_lines: int = 8) -> list[str]:
        lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            while len(lines) < max_lines:
                chunk = handle.read(_SAMPLE_BYTES)
                if not chunk:
                    break
                lines.extend(chunk.splitlines())
                if len(chunk) < _SAMPLE_BYTES:
                    break
        return lines[:max_lines]

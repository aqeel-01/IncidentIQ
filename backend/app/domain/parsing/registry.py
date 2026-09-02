"""Parser interface and registry.

New formats register a :class:`LogFormatParser` implementation without
modifying the ingestion pipeline.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, TextIO, runtime_checkable

from app.domain.parsing.mapping import ManualFieldMapping
from app.domain.parsing.types import LogFormat, ParsedLogRecord


@runtime_checkable
class LogFormatParser(Protocol):
    """Parse a log file incrementally, yielding one record at a time."""

    format: LogFormat

    def iter_records(
        self,
        handle: TextIO,
        *,
        field_mapping: ManualFieldMapping | None = None,
    ) -> Iterator[ParsedLogRecord]:
        """Yield parsed records from an open text file handle."""
        ...


class ParserRegistry:
    """Maps :class:`LogFormat` values to parser implementations."""

    def __init__(self) -> None:
        self._parsers: dict[LogFormat, LogFormatParser] = {}

    def register(self, parser: LogFormatParser) -> None:
        self._parsers[parser.format] = parser

    def get(self, fmt: LogFormat) -> LogFormatParser:
        try:
            return self._parsers[fmt]
        except KeyError as exc:
            raise KeyError(f"no parser registered for format {fmt!r}") from exc

    def formats(self) -> frozenset[LogFormat]:
        return frozenset(self._parsers)


def default_registry() -> ParserRegistry:
    """Build a registry with all built-in parsers installed."""

    from app.domain.parsing.parsers.csv import CsvLogParser
    from app.domain.parsing.parsers.json_format import JsonLogParser
    from app.domain.parsing.parsers.jsonl import JsonlLogParser
    from app.domain.parsing.parsers.plain_text import PlainTextLogParser
    from app.domain.parsing.parsers.structured_text import StructuredTextLogParser

    registry = ParserRegistry()
    for parser in (
        PlainTextLogParser(),
        StructuredTextLogParser(),
        JsonLogParser(),
        JsonlLogParser(),
        CsvLogParser(),
    ):
        registry.register(parser)
    return registry

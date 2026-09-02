"""Structured key=value text log parser."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TextIO

from app.domain.parsing.fields import build_record, extract_from_structured_line
from app.domain.parsing.mapping import ManualFieldMapping
from app.domain.parsing.types import LogFormat, ParsedLogRecord


class StructuredTextLogParser:
    format = LogFormat.STRUCTURED_TEXT

    def iter_records(
        self,
        handle: TextIO,
        *,
        field_mapping: ManualFieldMapping | None = None,
    ) -> Iterator[ParsedLogRecord]:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.rstrip("\n\r")
            if not stripped.strip():
                continue
            data = extract_from_structured_line(stripped)
            yield build_record(
                line_number=line_number,
                fmt=self.format,
                data=data,
                raw_data={"line": stripped, **data},
                field_mapping=field_mapping,
            )

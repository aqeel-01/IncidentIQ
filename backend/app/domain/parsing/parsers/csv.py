"""CSV log parser with a header row."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from typing import TextIO

from app.domain.parsing.fields import build_record
from app.domain.parsing.mapping import ManualFieldMapping
from app.domain.parsing.types import LogFormat, ParsedLogRecord


class CsvLogParser:
    format = LogFormat.CSV

    def iter_records(
        self,
        handle: TextIO,
        *,
        field_mapping: ManualFieldMapping | None = None,
    ) -> Iterator[ParsedLogRecord]:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return

        for line_number, row in enumerate(reader, start=2):
            # line 1 is the header row.
            if not any(value and value.strip() for value in row.values()):
                continue
            data = {k: v for k, v in row.items() if k is not None}
            yield build_record(
                line_number=line_number,
                fmt=self.format,
                data=data,
                raw_data=data,
                field_mapping=field_mapping,
            )

"""Single JSON document parser (object or array of objects)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, TextIO

from app.domain.parsing.fields import build_record
from app.domain.parsing.mapping import ManualFieldMapping
from app.domain.parsing.types import LogFormat, ParsedLogRecord


class JsonLogParser:
    format = LogFormat.JSON

    def iter_records(
        self,
        handle: TextIO,
        *,
        field_mapping: ManualFieldMapping | None = None,
    ) -> Iterator[ParsedLogRecord]:
        payload: Any = json.load(handle)
        if isinstance(payload, dict):
            records = [payload]
        elif isinstance(payload, list):
            records = payload
        else:
            raise ValueError("JSON log must be an object or array of objects")

        for index, item in enumerate(records, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"JSON record {index} must be an object")
            yield build_record(
                line_number=index,
                fmt=self.format,
                data=item,
                raw_data=item,
                field_mapping=field_mapping,
            )

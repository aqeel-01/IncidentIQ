"""JSON Lines (JSONL) log parser — one JSON object per line."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, TextIO

from app.domain.parsing.fields import build_record
from app.domain.parsing.mapping import ManualFieldMapping
from app.domain.parsing.types import LogFormat, ParsedLogRecord


class JsonlLogParser:
    format = LogFormat.JSONL

    def iter_records(
        self,
        handle: TextIO,
        *,
        field_mapping: ManualFieldMapping | None = None,
    ) -> Iterator[ParsedLogRecord]:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload: dict[str, Any] = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(
                    f"line {line_number}: JSONL record must be a JSON object"
                )
            yield build_record(
                line_number=line_number,
                fmt=self.format,
                data=payload,
                raw_data=payload,
                field_mapping=field_mapping,
            )

"""Automatic log format detection from filename and content samples."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from app.domain.parsing.types import DetectionResult, LogFormat

_EXTENSION_HINTS: dict[str, LogFormat] = {
    ".log": LogFormat.PLAIN_TEXT,
    ".txt": LogFormat.PLAIN_TEXT,
    ".json": LogFormat.JSON,
    ".jsonl": LogFormat.JSONL,
    ".csv": LogFormat.CSV,
}

_SAMPLE_LINE_LIMIT = 8


class LogFormatDetector:
    """Detect the most likely log format without reading the entire file."""

    def detect(self, filename: str | None, sample_lines: list[str]) -> DetectionResult:
        extension = Path(filename).suffix.lower() if filename else ""
        non_empty = [line for line in sample_lines if line.strip()]

        if extension == ".csv":
            return DetectionResult(
                format=LogFormat.CSV, confidence=0.95, reason="csv extension"
            )
        if extension == ".jsonl":
            return DetectionResult(
                format=LogFormat.JSONL, confidence=0.95, reason="jsonl extension"
            )

        if self._looks_like_jsonl(non_empty):
            return DetectionResult(
                format=LogFormat.JSONL,
                confidence=0.9,
                reason="each sample line is a JSON object",
            )

        if extension == ".json" or self._looks_like_json_document(non_empty):
            return DetectionResult(
                format=LogFormat.JSON,
                confidence=0.9,
                reason="json document",
            )

        if self._looks_like_csv(non_empty):
            return DetectionResult(
                format=LogFormat.CSV, confidence=0.85, reason="csv-like header row"
            )

        if self._looks_like_structured(non_empty):
            return DetectionResult(
                format=LogFormat.STRUCTURED_TEXT,
                confidence=0.8,
                reason="key=value structured text",
            )

        hint = _EXTENSION_HINTS.get(extension, LogFormat.PLAIN_TEXT)
        return DetectionResult(
            format=hint,
            confidence=0.6 if extension else 0.5,
            reason=f"extension {extension!r}" if extension else "default plain text",
        )

    @staticmethod
    def _looks_like_jsonl(lines: list[str]) -> bool:
        if len(lines) < 1:
            return False
        checked = lines[:_SAMPLE_LINE_LIMIT]
        if len(checked) < 2:
            return False
        for line in checked:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                return False
            if not isinstance(payload, dict):
                return False
        return True

    @staticmethod
    def _looks_like_json_document(lines: list[str]) -> bool:
        if not lines:
            return False
        joined = "".join(lines).strip()
        if not joined:
            return False
        if joined[0] not in "{[":
            return False
        try:
            payload = json.loads(joined)
        except json.JSONDecodeError:
            return False
        return isinstance(payload, (dict, list))

    @staticmethod
    def _looks_like_csv(lines: list[str]) -> bool:
        if len(lines) < 2:
            return False
        header = lines[0]
        if header.count(",") < 1:
            return False
        try:
            reader = csv.reader(StringIO(header))
            header_cols = next(reader)
        except csv.Error:
            return False
        if len(header_cols) < 2:
            return False
        # Header should look like field names, not a plain sentence.
        return any(col.strip().isidentifier() or "_" in col for col in header_cols)

    @staticmethod
    def _looks_like_structured(lines: list[str]) -> bool:
        if not lines:
            return False
        hits = 0
        for line in lines[:_SAMPLE_LINE_LIMIT]:
            if "=" in line and sum(1 for _ in line.split("=")) >= 2:
                hits += 1
        return hits >= max(1, len(lines[:_SAMPLE_LINE_LIMIT]) // 2)

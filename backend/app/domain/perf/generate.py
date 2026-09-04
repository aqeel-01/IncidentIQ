"""Synthetic JSONL event corpus generator (streaming, no full in-memory copy)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Bounded pattern set keeps dedupe meaningful while still scanning N events.
_MESSAGE_PATTERNS = (
    "connection timeout talking to database id={n}",
    "upstream auth token request failed code={n}",
    "payment capture declined for order={n}",
    "redis pool wait exceeded after {n}ms",
    "kafka consumer lag partition={n}",
    "null pointer while rendering invoice={n}",
    "disk usage critical on volume={n}",
    "grpc deadline exceeded method={n}",
)


def write_synthetic_jsonl(
    path: Path,
    event_count: int,
    *,
    service: str = "payments-api",
    unique_patterns: int = 64,
) -> Path:
    """Write ``event_count`` JSONL log lines incrementally to ``path``."""

    if event_count < 1:
        msg = "event_count must be >= 1"
        raise ValueError(msg)
    if unique_patterns < 1:
        msg = "unique_patterns must be >= 1"
        raise ValueError(msg)

    path.parent.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    pattern_count = min(unique_patterns, len(_MESSAGE_PATTERNS) * 16)

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for index in range(event_count):
            pattern_index = index % pattern_count
            template = _MESSAGE_PATTERNS[pattern_index % len(_MESSAGE_PATTERNS)]
            # Keep a stable normalized form per pattern bucket while varying ids.
            bucket = pattern_index
            message = template.format(n=bucket)
            payload = {
                "timestamp": (base + timedelta(milliseconds=index)).isoformat(),
                "level": "ERROR" if index % 5 else "WARN",
                "service": service,
                "host": f"host-{(index % 8) + 1}",
                "message": message,
                "request_id": f"req-{index}",
                "environment": "production",
                "pattern_id": bucket,
            }
            handle.write(json.dumps(payload, separators=(",", ":")))
            handle.write("\n")
            # Avoid buffering the entire corpus in userspace on huge runs.
            if index % 50_000 == 0 and index > 0:
                handle.flush()

    return path

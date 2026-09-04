"""Tests for streaming investigation helpers and performance harness."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.investigation.streaming import (
    chunked,
    deduplicate_normalized_records,
    iter_normalize_and_deduplicate,
    iter_parsed_log_sources,
)
from app.domain.perf.generate import write_synthetic_jsonl
from app.domain.perf.runner import benchmark_scale, render_markdown_report
from app.domain.perf.types import PerformanceReport


def test_write_synthetic_jsonl_is_incremental(tmp_path: Path) -> None:
    path = write_synthetic_jsonl(tmp_path / "events.jsonl", 250)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 250
    assert lines[0].startswith("{")


def test_streaming_normalize_dedupe_avoids_full_parse_buffer(tmp_path: Path) -> None:
    path = write_synthetic_jsonl(tmp_path / "events.jsonl", 500, unique_patterns=8)
    stream, counters = iter_normalize_and_deduplicate(
        iter_parsed_log_sources(log_file_paths=[path]),
        copy_raw_data=False,
    )
    kept = list(stream)
    assert counters["parsed"] == 500
    assert counters["kept"] == len(kept)
    assert counters["kept"] < counters["parsed"]
    assert counters["removed"] == counters["parsed"] - counters["kept"]


def test_chunked_and_dedupe_helpers(tmp_path: Path) -> None:
    path = write_synthetic_jsonl(tmp_path / "events.jsonl", 40, unique_patterns=5)
    stream, _counters = iter_normalize_and_deduplicate(
        iter_parsed_log_sources(log_file_paths=[path]),
        copy_raw_data=False,
    )
    records = list(stream)
    batches = list(chunked(records, 3))
    assert sum(len(batch) for batch in batches) == len(records)
    deduped, removed = deduplicate_normalized_records(records)
    assert removed == 0
    assert len(deduped) == len(records)


@pytest.mark.asyncio
async def test_benchmark_scale_smoke(tmp_path: Path) -> None:
    result = await benchmark_scale(
        200,
        work_dir=tmp_path,
        chunk_size=50,
        persist=True,
        run_rca=True,
    )
    assert result.event_count == 200
    assert result.ingestion_seconds is not None and result.ingestion_seconds >= 0
    assert result.normalization_seconds is not None
    assert result.deduplication_seconds is not None
    assert result.analysis_seconds is not None
    assert result.rca_seconds is not None
    names = [stage.name for stage in result.stages]
    assert names == [
        "generate",
        "ingestion",
        "normalization",
        "deduplication",
        "analysis",
        "db_ingest",
        "rca",
    ]
    markdown = render_markdown_report(
        PerformanceReport(
            generated_at=datetime.now(tz=UTC),
            host="test",
            python_version="3.12",
            scales=[result],
            notes=["smoke"],
        )
    )
    assert "200" in markdown
    assert "Ingestion" in markdown

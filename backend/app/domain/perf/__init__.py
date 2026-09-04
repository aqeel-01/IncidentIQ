"""Ingestion and investigation performance benchmarks."""

from app.domain.perf.generate import write_synthetic_jsonl
from app.domain.perf.runner import (
    DEFAULT_SCALES,
    benchmark_scale,
    render_markdown_report,
    run_performance_suite,
    write_performance_report,
)
from app.domain.perf.types import (
    PerformanceReport,
    ScaleBenchmarkResult,
    StageTiming,
)

__all__ = [
    "DEFAULT_SCALES",
    "PerformanceReport",
    "ScaleBenchmarkResult",
    "StageTiming",
    "benchmark_scale",
    "render_markdown_report",
    "run_performance_suite",
    "write_performance_report",
    "write_synthetic_jsonl",
]

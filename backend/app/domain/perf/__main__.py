"""CLI for ingestion/investigation performance benchmarks.

Examples:

  python -m app.domain.perf --scales 10000,100000,1000000

  python -m app.domain.perf --scales 10000 --persist-max 10000
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.domain.perf.runner import (
    DEFAULT_SCALES,
    render_markdown_report,
    run_performance_suite,
    write_performance_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domain.perf",
        description=(
            "Benchmark ingestion, normalization, deduplication, analysis, "
            "and RCA at 10K / 100K / 1M event scales."
        ),
    )
    parser.add_argument(
        "--scales",
        default=",".join(str(item) for item in DEFAULT_SCALES),
        help="Comma-separated event counts (default: 10000,100000,1000000)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("data/perf"),
        help="Directory for generated corpora",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/perf/results.json"),
        help="Machine-readable JSON report path",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("docs/performance.md"),
        help="Human-readable markdown report path",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="DB ingest chunk size",
    )
    parser.add_argument(
        "--persist-max",
        type=int,
        default=1_000_000,
        help="Skip DB ingest above this event count (0 disables all DB ingest)",
    )
    return parser


def _parse_scales(raw: str) -> tuple[int, ...]:
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value < 1:
            msg = f"invalid scale {value}"
            raise ValueError(msg)
        values.append(value)
    if not values:
        msg = "at least one scale is required"
        raise ValueError(msg)
    return tuple(values)


async def _async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    scales = _parse_scales(args.scales)
    persist_max = None if args.persist_max < 0 else args.persist_max

    report = await run_performance_suite(
        scales=scales,
        work_dir=args.work_dir,
        chunk_size=args.chunk_size,
        persist_max_events=persist_max,
    )
    write_performance_report(report, args.output)
    markdown = render_markdown_report(report)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown, encoding="utf-8")

    print(f"wrote JSON report to {args.output}")
    print(f"wrote markdown report to {args.markdown}")
    for scale in report.scales:
        print(
            f"  n={scale.event_count}: "
            f"ingest={scale.ingestion_seconds:.3f}s "
            f"norm={scale.normalization_seconds:.3f}s "
            f"dedupe={scale.deduplication_seconds:.3f}s "
            f"analysis={scale.analysis_seconds:.3f}s "
            f"rca={scale.rca_seconds:.3f}s "
            f"rss={scale.peak_rss_mb}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    sys.exit(main())

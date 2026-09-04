"""CLI for the RCA evaluation framework.

Examples:

  python -m app.domain.rca.eval --output data/rca_eval/results.json

  python -m app.domain.rca.eval \\
    --backends local_small,local_7b,groq \\
    --dataset tests/fixtures/rca_benchmark \\
    --output data/rca_eval/results.json

  python -m app.domain.rca.eval --export-dataset tests/fixtures/rca_benchmark
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import get_settings
from app.domain.rca.eval.dataset import (
    export_benchmark_dataset,
    load_benchmark_dataset,
)
from app.domain.rca.eval.runner import run_evaluation_to_file
from app.domain.rca.eval.synthetic import build_synthetic_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domain.rca.eval",
        description=(
            "Evaluate RCA quality on a synthetic benchmark across "
            "local_small, local_7b, and groq backends."
        ),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Benchmark dataset path (directory or JSON). Default: built-in synthetic.",
    )
    parser.add_argument(
        "--backends",
        default="local_small,local_7b,groq",
        help="Comma-separated backends: local_small,local_7b,groq",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/rca_eval/results.json"),
        help="Path for machine-readable JSON results",
    )
    parser.add_argument(
        "--export-dataset",
        type=Path,
        default=None,
        help="Export the built-in synthetic dataset to this directory and exit",
    )
    return parser


async def _async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.export_dataset is not None:
        dataset = (
            load_benchmark_dataset(args.dataset)
            if args.dataset is not None
            else build_synthetic_benchmark()
        )
        manifest = export_benchmark_dataset(dataset, args.export_dataset)
        print(f"exported dataset manifest to {manifest}")
        return 0

    report = await run_evaluation_to_file(
        output_path=args.output,
        settings=get_settings(),
        dataset_path=args.dataset,
        backends=args.backends,
    )
    print(f"wrote evaluation report to {args.output}")
    for backend in report.backends:
        accuracy = (
            f"{backend.rca_accuracy:.3f}" if backend.rca_accuracy is not None else "n/a"
        )
        print(
            f"  {backend.backend}: accuracy={accuracy} "
            f"evaluated={backend.cases_evaluated} failed={backend.cases_failed}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    sys.exit(main())

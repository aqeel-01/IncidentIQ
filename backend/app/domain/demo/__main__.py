"""CLI for the deterministic IncidentIQ end-to-end demo.

Example:

  python -m app.domain.demo

  python -m app.domain.demo --work-dir data/demo --output data/demo/result.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.domain.demo.report import format_demo_report
from app.domain.demo.runner import run_demo, write_demo_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domain.demo",
        description=(
            "Run a reproducible IncidentIQ end-to-end demo: "
            "alert → incident → collection → … → ranked RCA."
        ),
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("data/demo"),
        help="Directory for demo DB, log corpus, and artifacts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/demo/result.json"),
        help="Machine-readable JSON result path",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Optional SQLAlchemy URL. Default: sqlite file under --work-dir "
            "(reset on each run). Point at Postgres to inspect results in the UI."
        ),
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Do not delete the default sqlite demo.db before running",
    )
    return parser


async def _async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.keep_db and args.database_url is None:
        # Preserve file DB: pass an explicit URL so runner skips reset.
        db_path = (args.work_dir / "demo.db").resolve()
        args.work_dir.mkdir(parents=True, exist_ok=True)
        args.database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    result = await run_demo(
        work_dir=args.work_dir,
        database_url=args.database_url,
    )
    write_demo_result(result, args.output)
    print(format_demo_report(result))
    print(f"wrote machine-readable result to {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    sys.exit(main())

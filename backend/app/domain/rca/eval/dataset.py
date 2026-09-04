"""Load and export RCA benchmark datasets."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.rca.eval.synthetic import build_synthetic_benchmark
from app.domain.rca.eval.types import BenchmarkCase, BenchmarkDataset

DEFAULT_FIXTURE_DIR = (
    Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "rca_benchmark"
)


def load_benchmark_dataset(path: Path | None = None) -> BenchmarkDataset:
    """Load a benchmark dataset from disk, or the built-in synthetic set.

    Supported layouts:
    - directory with ``manifest.json`` listing ``cases/*.json``
    - single JSON file containing a full ``BenchmarkDataset``
    - ``None`` → built-in synthetic dataset
    """

    if path is None:
        return build_synthetic_benchmark()

    resolved = path.resolve()
    if resolved.is_file():
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return BenchmarkDataset.model_validate(payload)

    manifest_path = resolved / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        case_files = manifest.get("cases", [])
        cases: list[BenchmarkCase] = []
        for relative in case_files:
            case_path = resolved / relative
            case_payload = json.loads(case_path.read_text(encoding="utf-8"))
            cases.append(BenchmarkCase.model_validate(case_payload))
        return BenchmarkDataset(
            name=manifest.get("name", "incidentiq-rca-benchmark"),
            version=manifest.get("version", "1.0"),
            cases=cases,
        )

    case_dir = resolved / "cases"
    if case_dir.is_dir():
        cases = []
        for case_path in sorted(case_dir.glob("*.json")):
            case_payload = json.loads(case_path.read_text(encoding="utf-8"))
            cases.append(BenchmarkCase.model_validate(case_payload))
        return BenchmarkDataset(cases=cases)

    msg = f"unsupported benchmark dataset path: {resolved}"
    raise FileNotFoundError(msg)


def export_benchmark_dataset(
    dataset: BenchmarkDataset,
    output_dir: Path,
) -> Path:
    """Write dataset cases + manifest for machine-readable reuse."""

    output_dir.mkdir(parents=True, exist_ok=True)
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    relative_cases: list[str] = []
    for case in dataset.cases:
        relative = f"cases/{case.id}.json"
        case_path = output_dir / relative
        case_path.write_text(
            case.model_dump_json(indent=2),
            encoding="utf-8",
        )
        relative_cases.append(relative)

    manifest = {
        "name": dataset.name,
        "version": dataset.version,
        "cases": relative_cases,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def default_fixture_dataset() -> BenchmarkDataset:
    """Prefer on-disk fixtures when present; otherwise use synthetic builder."""

    if (DEFAULT_FIXTURE_DIR / "manifest.json").is_file():
        return load_benchmark_dataset(DEFAULT_FIXTURE_DIR)
    return build_synthetic_benchmark()

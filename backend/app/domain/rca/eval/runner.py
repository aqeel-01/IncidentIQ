"""Run RCA evaluation across backends and emit machine-readable JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.ai.provider import AIProvider
from app.core.config import Settings, get_settings
from app.domain.rca.config import rca_engine_config_from_settings
from app.domain.rca.engine import RCAEngine
from app.domain.rca.eval.backends import (
    BACKEND_ORDER,
    build_eval_provider,
    parse_backends,
)
from app.domain.rca.eval.dataset import load_benchmark_dataset
from app.domain.rca.eval.scorer import aggregate_case_scores, score_case
from app.domain.rca.eval.types import (
    BackendAggregateMetrics,
    BenchmarkDataset,
    CaseMetricScores,
    EvalBackendName,
    EvaluationReport,
)


def _comparison_table(
    backends: list[BackendAggregateMetrics],
) -> dict[str, dict[str, float | None]]:
    metrics = (
        "rca_accuracy",
        "mean_reciprocal_rank",
        "mean_ranking_kendall_tau",
        "mean_grounding_f1",
        "mean_hallucination_rate",
        "expected_calibration_error",
    )
    table: dict[str, dict[str, float | None]] = {}
    for metric in metrics:
        table[metric] = {item.backend: getattr(item, metric) for item in backends}
    return table


async def evaluate_backend(
    *,
    backend: EvalBackendName,
    dataset: BenchmarkDataset,
    provider: AIProvider,
    engine: RCAEngine,
) -> BackendAggregateMetrics:
    """Evaluate every benchmark case with one backend provider."""

    scores: list[CaseMetricScores] = []
    for case in dataset.cases:
        try:
            engine_result = await engine.analyze(case.package, provider)
            scores.append(score_case(case, engine_result, backend=backend))
        except Exception as exc:  # noqa: BLE001 — capture per-case failures
            scores.append(
                CaseMetricScores(
                    case_id=case.id,
                    backend=backend,
                    accurate=False,
                    reciprocal_rank=0.0,
                    hallucination_rate=0.0,
                    confidence=0.0,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return aggregate_case_scores(backend, scores)


async def run_evaluation(
    *,
    settings: Settings | None = None,
    dataset: BenchmarkDataset | None = None,
    dataset_path: Path | None = None,
    backends: list[EvalBackendName] | None = None,
) -> EvaluationReport:
    """Run the benchmark for the requested backends and return a report."""

    resolved_settings = settings or get_settings()
    resolved_dataset = dataset or load_benchmark_dataset(dataset_path)
    resolved_backends = backends or list(BACKEND_ORDER)
    engine = RCAEngine(config=rca_engine_config_from_settings(resolved_settings))

    aggregates: list[BackendAggregateMetrics] = []
    for backend in resolved_backends:
        try:
            provider = build_eval_provider(backend, resolved_settings)
        except Exception as exc:  # noqa: BLE001 — backend unavailable
            aggregates.append(
                BackendAggregateMetrics(
                    backend=backend,
                    cases_evaluated=0,
                    cases_failed=len(resolved_dataset.cases),
                    case_scores=[
                        CaseMetricScores(
                            case_id=case.id,
                            backend=backend,
                            accurate=False,
                            reciprocal_rank=0.0,
                            hallucination_rate=0.0,
                            confidence=0.0,
                            status="error",
                            error=f"{type(exc).__name__}: {exc}",
                        )
                        for case in resolved_dataset.cases
                    ],
                )
            )
            continue

        aggregate = await evaluate_backend(
            backend=backend,
            dataset=resolved_dataset,
            provider=provider,
            engine=engine,
        )
        aggregates.append(aggregate)
        close = getattr(provider, "aclose", None)
        if callable(close):
            await close()

    return EvaluationReport(
        dataset_name=resolved_dataset.name,
        dataset_version=resolved_dataset.version,
        generated_at=datetime.now(tz=UTC),
        backends=aggregates,
        comparison=_comparison_table(aggregates),
    )


def write_evaluation_report(report: EvaluationReport, output_path: Path) -> Path:
    """Write an evaluation report as pretty-printed JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


async def run_evaluation_to_file(
    *,
    output_path: Path,
    settings: Settings | None = None,
    dataset_path: Path | None = None,
    backends: str | None = None,
) -> EvaluationReport:
    """Convenience entry used by the CLI."""

    report = await run_evaluation(
        settings=settings,
        dataset_path=dataset_path,
        backends=parse_backends(backends),
    )
    write_evaluation_report(report, output_path)
    return report


def report_to_dict(report: EvaluationReport) -> dict:
    """Serialize a report to a plain dict (JSON-compatible)."""

    return json.loads(report.model_dump_json())

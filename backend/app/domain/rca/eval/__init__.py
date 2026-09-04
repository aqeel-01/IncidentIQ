"""RCA evaluation framework: benchmark dataset, metrics, and multi-backend runner."""

from app.domain.rca.eval.backends import (
    BACKEND_ORDER,
    build_eval_provider,
    parse_backends,
)
from app.domain.rca.eval.dataset import (
    default_fixture_dataset,
    export_benchmark_dataset,
    load_benchmark_dataset,
)
from app.domain.rca.eval.runner import (
    evaluate_backend,
    report_to_dict,
    run_evaluation,
    run_evaluation_to_file,
    write_evaluation_report,
)
from app.domain.rca.eval.scorer import (
    aggregate_case_scores,
    expected_calibration_error,
    score_case,
)
from app.domain.rca.eval.synthetic import build_synthetic_benchmark
from app.domain.rca.eval.types import (
    BackendAggregateMetrics,
    BenchmarkCase,
    BenchmarkDataset,
    CalibrationBin,
    CaseMetricScores,
    EvalBackendName,
    EvaluationReport,
    GoldLabel,
)

__all__ = [
    "BACKEND_ORDER",
    "BackendAggregateMetrics",
    "BenchmarkCase",
    "BenchmarkDataset",
    "CalibrationBin",
    "CaseMetricScores",
    "EvalBackendName",
    "EvaluationReport",
    "GoldLabel",
    "aggregate_case_scores",
    "build_eval_provider",
    "build_synthetic_benchmark",
    "default_fixture_dataset",
    "evaluate_backend",
    "expected_calibration_error",
    "export_benchmark_dataset",
    "load_benchmark_dataset",
    "parse_backends",
    "report_to_dict",
    "run_evaluation",
    "run_evaluation_to_file",
    "score_case",
    "write_evaluation_report",
]

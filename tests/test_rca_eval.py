"""Tests for the RCA evaluation framework."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.rca.engine import RCAEngineResult
from app.domain.rca.eval import (
    aggregate_case_scores,
    build_synthetic_benchmark,
    export_benchmark_dataset,
    load_benchmark_dataset,
    parse_backends,
    report_to_dict,
    score_case,
)
from app.domain.rca.eval.matching import titles_match
from app.domain.rca.eval.runner import run_evaluation, write_evaluation_report
from app.domain.rca.eval.scorer import expected_calibration_error
from app.domain.rca.eval.types import BackendAggregateMetrics, EvaluationReport
from app.domain.rca.types import (
    Hypothesis,
    RCAHypothesisEvaluationResult,
    RCAResult,
    RCAStatus,
    SupportingEvidence,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rca_benchmark"


def _engine_result(
    *,
    primary_title: str | None,
    confidence: float,
    status: RCAStatus,
    ranked_titles: list[str] | None = None,
    supporting_keys: list[str] | None = None,
) -> RCAEngineResult:
    primary = None
    if primary_title is not None:
        primary = Hypothesis(
            title=primary_title,
            description=f"Synthetic description for {primary_title}",
            confidence=confidence,
            rationale="test",
        )
    supporting = [
        SupportingEvidence(
            key=key,
            description=f"Evidence {key}",
            confidence=0.8,
            source="test",
        )
        for key in (supporting_keys or [])
    ]
    result = RCAResult(
        status=status,
        primary_hypothesis=primary,
        confidence=confidence,
        supporting_evidence=supporting,
        contradicting_evidence=[],
        alternative_hypotheses=[],
        verification_steps=[],
        evidence_quality=80,
    )
    evaluation = None
    if ranked_titles is not None:
        evaluation = RCAHypothesisEvaluationResult(
            evaluations=[],
            ranked_titles=ranked_titles,
            summary="ranked for tests",
        )
    return RCAEngineResult(
        result=result,
        engine_version="1.0",
        prompt_version="v1",
        ai_provider="fake",
        ai_model="fake-model",
        hypothesis_evaluation=evaluation,
    )


def test_synthetic_benchmark_has_known_root_causes() -> None:
    dataset = build_synthetic_benchmark()
    assert len(dataset.cases) >= 6
    ids = {case.id for case in dataset.cases}
    assert "deploy-regression-payments" in ids
    assert "insufficient-evidence-blip" in ids
    for case in dataset.cases:
        assert case.gold.root_cause_title
        assert case.package.incident.title


def test_titles_match_aliases() -> None:
    assert titles_match(
        "Faulty release of payments-api",
        "Deployment regression",
        ["faulty release"],
    )
    assert not titles_match(
        "Network partition",
        "Deployment regression",
        ["bad deploy"],
    )


def test_score_case_accuracy_ranking_grounding_hallucination() -> None:
    dataset = build_synthetic_benchmark()
    case = next(c for c in dataset.cases if c.id == "deploy-regression-payments")
    engine_result = _engine_result(
        primary_title="Deployment regression",
        confidence=0.88,
        status=RCAStatus.CONFIDENT,
        ranked_titles=[
            "Deployment regression",
            "Database saturation",
            "Upstream dependency failure",
        ],
        supporting_keys=[
            "deploy:payments-v122",
            "error_group:db-timeout",
            "invented-hallucination-key",
        ],
    )

    scored = score_case(case, engine_result, backend="local_small")

    assert scored.accurate is True
    assert scored.primary_rank == 1
    assert scored.reciprocal_rank == 1.0
    assert scored.ranking_kendall_tau == 1.0
    assert scored.grounding_recall is not None and scored.grounding_recall > 0
    assert "invented-hallucination-key" in scored.hallucinated_keys
    assert scored.hallucination_rate == pytest.approx(1 / 3)


def test_score_insufficient_evidence_case() -> None:
    dataset = build_synthetic_benchmark()
    case = next(c for c in dataset.cases if c.id == "insufficient-evidence-blip")
    engine_result = _engine_result(
        primary_title=None,
        confidence=0.0,
        status=RCAStatus.NO_CONFIDENT_ROOT_CAUSE,
        ranked_titles=[],
        supporting_keys=[],
    )
    scored = score_case(case, engine_result, backend="local_7b")
    assert scored.accurate is True


def test_expected_calibration_error_and_aggregate() -> None:
    ece, bins = expected_calibration_error(
        [0.9, 0.8, 0.2, 0.1],
        [True, True, False, True],
        n_bins=2,
    )
    assert ece is not None
    assert ece >= 0.0
    assert len(bins) == 2

    dataset = build_synthetic_benchmark()
    case = dataset.cases[0]
    scores = [
        score_case(
            case,
            _engine_result(
                primary_title="Deployment regression",
                confidence=0.9,
                status=RCAStatus.CONFIDENT,
                ranked_titles=["Deployment regression"],
                supporting_keys=["deploy:payments-v122"],
            ),
            backend="groq",
        )
    ]
    aggregate = aggregate_case_scores("groq", scores)
    assert aggregate.rca_accuracy == 1.0
    assert aggregate.cases_evaluated == 1
    assert aggregate.expected_calibration_error is not None


def test_export_and_load_benchmark_dataset(tmp_path: Path) -> None:
    dataset = build_synthetic_benchmark()
    manifest = export_benchmark_dataset(dataset, tmp_path)
    assert manifest.is_file()
    loaded = load_benchmark_dataset(tmp_path)
    assert loaded.name == dataset.name
    assert len(loaded.cases) == len(dataset.cases)
    assert loaded.cases[0].id == dataset.cases[0].id


def test_parse_backends() -> None:
    assert parse_backends("local_small,groq") == ["local_small", "groq"]
    with pytest.raises(ValueError):
        parse_backends("bogus")


@pytest.mark.asyncio
async def test_run_evaluation_records_unavailable_backends() -> None:
    settings = Settings(
        app_env="test",
        ollama_model_small="",
        ollama_model_large="",
        groq_api_key="",
        groq_model="",
    )
    dataset = build_synthetic_benchmark()
    tiny = dataset.model_copy(update={"cases": dataset.cases[:1]})

    report = await run_evaluation(
        settings=settings,
        dataset=tiny,
        backends=["local_small", "local_7b", "groq"],
    )
    assert len(report.backends) == 3
    assert "rca_accuracy" in report.comparison
    payload = report_to_dict(report)
    assert payload["schema_version"] == "1.0"
    assert all(backend["cases_failed"] >= 1 for backend in payload["backends"])


def test_write_evaluation_report_json(tmp_path: Path) -> None:
    report = EvaluationReport(
        dataset_name="test",
        dataset_version="1.0",
        generated_at=datetime(2026, 9, 3, tzinfo=UTC),
        backends=[
            BackendAggregateMetrics(
                backend="local_small",
                cases_evaluated=0,
                cases_failed=0,
                rca_accuracy=0.5,
            )
        ],
        comparison={"rca_accuracy": {"local_small": 0.5}},
    )
    path = write_evaluation_report(report, tmp_path / "results.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["comparison"]["rca_accuracy"]["local_small"] == 0.5


def test_fixture_dir_roundtrip_if_present() -> None:
    if not (FIXTURE_DIR / "manifest.json").is_file():
        pytest.skip("fixture dataset not exported yet")
    loaded = load_benchmark_dataset(FIXTURE_DIR)
    assert len(loaded.cases) >= 6

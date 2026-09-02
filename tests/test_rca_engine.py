"""Tests for the RCA engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ai import (
    AIProvider,
    AIProviderHealthResult,
    AIProviderName,
    AIProviderStructuredOutputError,
    GenerateRequest,
    GenerateResponse,
)
from app.domain.rca import (
    RCAEngine,
    RCAEngineConfig,
    RCAEvidencePackage,
    RCAStatus,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "rca_evidence_package_full.json"


class SequentialFakeAIProvider(AIProvider):
    """Returns structured payloads in call order for staged RCA tests."""

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self._call_index = 0
        self.generate_calls: list[GenerateRequest] = []

    @property
    def name(self) -> AIProviderName:
        return AIProviderName.OLLAMA

    @property
    def model(self) -> str:
        return "fake-rca-model"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.generate_calls.append(request)
        if self._call_index >= len(self._payloads):
            msg = "no more staged payloads configured for fake provider"
            raise RuntimeError(msg)

        payload = self._payloads[self._call_index]
        self._call_index += 1
        content = json.dumps(payload)
        if "Respond with valid JSON only" in request.prompt:
            content = json.dumps(payload)
        return GenerateResponse(
            content=content,
            provider=self.name,
            model=self.model,
            finish_reason="stop",
        )

    async def health_check(self) -> AIProviderHealthResult:
        return AIProviderHealthResult(
            provider=self.name,
            healthy=True,
            detail="ready",
            model=self.model,
            checked_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )


def _load_package_fixture() -> RCAEvidencePackage:
    return RCAEvidencePackage.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def _deployment_hypothesis() -> dict:
    return {
        "title": "Deployment regression",
        "description": "Recent deployment preceded the first error spike.",
        "confidence": 0.82,
        "rationale": "Temporal correlation between deployment and errors.",
    }


def _upstream_hypothesis() -> dict:
    return {
        "title": "Upstream dependency failure",
        "description": "Auth service errors propagated downstream.",
        "confidence": 0.35,
        "rationale": "Lower-confidence alternative.",
    }


def _staged_payloads(*, final_status: str = "confident") -> list[dict]:
    return [
        {
            "symptoms": [
                {
                    "id": "event:3",
                    "title": "HighErrorRate",
                    "kind": "alert",
                    "observation": "High error rate alert fired for payments-api.",
                    "service": "payments-api",
                },
                {
                    "id": "event:4",
                    "title": "connection timeout talking to database",
                    "kind": "log",
                    "observation": "Log signal reports database connection timeouts.",
                    "service": "payments-api",
                },
            ],
            "summary": "Alerts and logs indicate elevated errors.",
        },
        {
            "hypotheses": [_deployment_hypothesis(), _upstream_hypothesis()],
            "summary": "Two candidate hypotheses identified.",
        },
        {
            "evaluations": [
                {
                    "hypothesis": _deployment_hypothesis(),
                    "supporting_evidence": [
                        {
                            "key": "corr-deployment-to-error",
                            "description": (
                                "Deployment preceded database timeout errors."
                            ),
                            "confidence": 0.8,
                            "source": "correlation",
                        }
                    ],
                    "contradicting_evidence": [],
                    "temporal_consistency_score": 0.7,
                    "dependency_consistency_score": 0.75,
                },
                {
                    "hypothesis": _upstream_hypothesis(),
                    "supporting_evidence": [],
                    "contradicting_evidence": [
                        {
                            "key": "corr-deployment-to-error",
                            "description": (
                                "Deployment timing better explains the spike."
                            ),
                            "confidence": 0.6,
                            "source": "correlation",
                        }
                    ],
                    "temporal_consistency_score": 0.4,
                    "dependency_consistency_score": 0.3,
                },
            ],
            "ranked_titles": ["Deployment regression", "Upstream dependency failure"],
            "summary": "Deployment regression is best supported.",
        },
        {
            "status": final_status,
            "primary_hypothesis": _deployment_hypothesis(),
            "confidence": 0.82,
            "supporting_evidence": [
                {
                    "key": "corr-deployment-to-error",
                    "description": "Deployment preceded database timeout errors.",
                    "confidence": 0.8,
                    "source": "correlation",
                }
            ],
            "contradicting_evidence": [],
            "alternative_hypotheses": [_upstream_hypothesis()],
            "verification_steps": [
                {
                    "title": "Compare error rate before and after deployment",
                    "description": (
                        "Check whether error rate increased immediately after deploy."
                    ),
                    "priority": 1,
                }
            ],
            "evidence_quality": 84,
        },
    ]


def _engine_config(**overrides) -> RCAEngineConfig:
    base = {
        "engine_version": "1.0",
        "prompt_version": "v1",
        "temperature": 0.1,
        "max_tokens": 2048,
        "min_confidence": 0.6,
        "confident_threshold": 0.75,
        "min_evidence_quality": 30,
    }
    base.update(overrides)
    return RCAEngineConfig(**base)


@pytest.mark.asyncio
async def test_analyze_rca_runs_full_pipeline() -> None:
    engine = RCAEngine(config=_engine_config())
    provider = SequentialFakeAIProvider(_staged_payloads())

    result = await engine.analyze(_load_package_fixture(), provider)

    assert result.symptom_analysis is not None
    assert len(result.symptom_analysis.symptoms) == 2
    assert result.hypothesis_set is not None
    assert len(result.hypothesis_set.hypotheses) == 2
    assert result.hypothesis_evaluation is not None
    assert result.hypothesis_evaluation.ranked_titles[0] == "Deployment regression"
    assert result.result.status is RCAStatus.CONFIDENT
    assert result.result.primary_hypothesis is not None
    assert result.result.primary_hypothesis.title == "Deployment regression"
    assert result.result.supporting_evidence
    assert result.result.verification_steps
    assert len(provider.generate_calls) == 4


@pytest.mark.asyncio
async def test_analyze_rca_never_sends_raw_logs() -> None:
    engine = RCAEngine(config=_engine_config())
    provider = SequentialFakeAIProvider(_staged_payloads())

    await engine.analyze(_load_package_fixture(), provider)

    for call in provider.generate_calls:
        combined = f"{call.prompt}\n{call.system_prompt or ''}".lower()
        assert "raw_data" not in combined
        assert "raw_logs" not in combined
        assert "fingerprint" not in combined


@pytest.mark.asyncio
async def test_analyze_rca_returns_no_confident_for_insufficient_evidence() -> None:
    package = _load_package_fixture().model_copy(
        update={
            "symptoms": [],
            "error_groups": [],
            "anomalies": [],
            "deployments": [],
            "timeline": [],
            "correlations": [],
            "evidence_graph": None,
            "evidence_quality": None,
        }
    )
    provider = SequentialFakeAIProvider(_staged_payloads())
    engine = RCAEngine(config=_engine_config(min_evidence_quality=30))

    result = await engine.analyze(package, provider)

    assert result.result.status is RCAStatus.NO_CONFIDENT_ROOT_CAUSE
    assert result.result.primary_hypothesis is None
    assert result.result.verification_steps
    assert provider.generate_calls == []


@pytest.mark.asyncio
async def test_analyze_rca_returns_no_confident_when_confidence_too_low() -> None:
    payloads = _staged_payloads()
    payloads[1] = {
        "hypotheses": [
            {
                "title": "Weak guess",
                "description": "No strong evidence supports this.",
                "confidence": 0.2,
            }
        ],
        "summary": "Only a weak hypothesis is available.",
    }
    payloads[2] = {
        "evaluations": [
            {
                "hypothesis": payloads[1]["hypotheses"][0],
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "temporal_consistency_score": 0.1,
                "dependency_consistency_score": 0.1,
            }
        ],
        "ranked_titles": ["Weak guess"],
        "summary": "Evidence is weak.",
    }
    payloads[3] = {
        "status": "low_confidence",
        "primary_hypothesis": payloads[1]["hypotheses"][0],
        "confidence": 0.2,
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "alternative_hypotheses": [],
        "verification_steps": [
            {
                "title": "Collect more evidence",
                "description": "Gather additional traces and metrics.",
                "priority": 1,
            }
        ],
        "evidence_quality": 84,
    }

    engine = RCAEngine(config=_engine_config(min_confidence=0.95))
    provider = SequentialFakeAIProvider(payloads)

    result = await engine.analyze(_load_package_fixture(), provider)

    assert result.result.status is RCAStatus.NO_CONFIDENT_ROOT_CAUSE
    assert result.result.primary_hypothesis is None


@pytest.mark.asyncio
async def test_analyze_rca_validates_ai_response_against_schema() -> None:
    engine = RCAEngine(config=_engine_config())
    provider = SequentialFakeAIProvider(
        [
            {
                "symptoms": [],
                "summary": "No symptoms",
            },
            {
                "hypotheses": [_deployment_hypothesis()],
                "summary": "One hypothesis",
            },
            {
                "evaluations": [
                    {
                        "hypothesis": _deployment_hypothesis(),
                        "supporting_evidence": [],
                        "contradicting_evidence": [],
                        "temporal_consistency_score": 0.5,
                        "dependency_consistency_score": 0.5,
                    }
                ],
                "ranked_titles": ["Deployment regression"],
                "summary": "Evaluated",
            },
            {
                "status": "confident",
                "primary_hypothesis": None,
                "confidence": 0.9,
                "evidence_quality": 84,
            },
        ]
    )

    with pytest.raises(AIProviderStructuredOutputError):
        await engine.analyze(_load_package_fixture(), provider)


@pytest.mark.asyncio
async def test_analyze_rca_merges_temporal_and_dependency_consistency() -> None:
    engine = RCAEngine(config=_engine_config())
    provider = SequentialFakeAIProvider(_staged_payloads())

    result = await engine.analyze(_load_package_fixture(), provider)

    top = result.hypothesis_evaluation.evaluations[0]
    assert top.temporal_consistency_score > 0.0
    assert top.dependency_consistency_score > 0.0
    assert result.result.confidence > 0.0


@pytest.mark.asyncio
async def test_analyze_rca_ranks_hypotheses_by_combined_confidence() -> None:
    engine = RCAEngine(config=_engine_config())
    provider = SequentialFakeAIProvider(_staged_payloads())

    result = await engine.analyze(_load_package_fixture(), provider)

    ranked_titles = [
        evaluation.hypothesis.title
        for evaluation in result.hypothesis_evaluation.evaluations
    ]
    assert ranked_titles[0] == "Deployment regression"
    assert "Upstream dependency failure" in ranked_titles


def test_rca_engine_config_from_settings() -> None:
    from app.core.config import Settings
    from app.domain.rca import rca_engine_config_from_settings

    config = rca_engine_config_from_settings(
        Settings(rca_prompt_version="v1", rca_engine_version="1.0")
    )

    assert config.prompt_version == "v1"
    assert config.engine_version == "1.0"

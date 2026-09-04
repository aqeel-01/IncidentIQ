"""Deterministic fake AI provider for the IncidentIQ demo."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.ai import (
    AIProvider,
    AIProviderHealthResult,
    AIProviderName,
    GenerateRequest,
    GenerateResponse,
)


class SequentialFakeAIProvider(AIProvider):
    """Returns staged structured JSON payloads in call order."""

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self._call_index = 0
        self.generate_calls: list[GenerateRequest] = []

    @property
    def name(self) -> AIProviderName:
        return AIProviderName.OLLAMA

    @property
    def model(self) -> str:
        return "demo-fake-rca-model"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.generate_calls.append(request)
        if self._call_index >= len(self._payloads):
            msg = "no more staged demo AI payloads configured"
            raise RuntimeError(msg)
        payload = self._payloads[self._call_index]
        self._call_index += 1
        return GenerateResponse(
            content=json.dumps(payload),
            provider=self.name,
            model=self.model,
            finish_reason="stop",
        )

    async def health_check(self) -> AIProviderHealthResult:
        return AIProviderHealthResult(
            provider=self.name,
            healthy=True,
            detail="demo fake provider ready",
            model=self.model,
            checked_at=datetime.now(tz=UTC),
        )


def demo_rca_staged_payloads() -> list[dict]:
    """Four RCA stage payloads for the payments deployment-regression demo."""

    primary = {
        "title": "Deployment regression",
        "description": (
            "payments-api v1.2.2 introduced a database connection regression "
            "that caused elevated timeouts and checkout failures."
        ),
        "confidence": 0.86,
        "rationale": (
            "Deploy preceded the error_rate spike, database timeout logs, "
            "and HighErrorRate alert with strong temporal correlation."
        ),
    }
    alternative = {
        "title": "Upstream dependency failure",
        "description": (
            "An upstream auth or database dependency outage propagated into "
            "payments-api."
        ),
        "confidence": 0.34,
        "rationale": (
            "Possible, but no independent upstream alert or deployment signal "
            "was observed in the evidence window."
        ),
    }
    supporting = [
        {
            "key": "deploy:payments-v122",
            "description": "payments-api v1.2.2 deployed 60 minutes before errors.",
            "confidence": 0.9,
            "source": "deployment",
        },
        {
            "key": "metric:error-rate",
            "description": "error_rate rose to 0.9 after the deployment.",
            "confidence": 0.85,
            "source": "metric",
        },
        {
            "key": "log:db-timeout",
            "description": (
                "Repeated database connection timeout errors in payments-api."
            ),
            "confidence": 0.88,
            "source": "log",
        },
        {
            "key": "alert:HighErrorRate",
            "description": "HighErrorRate alert fired for payments-api.",
            "confidence": 0.8,
            "source": "alert",
        },
    ]
    contradicting_for_alt = [
        {
            "key": "deploy:payments-v122",
            "description": (
                "Deployment timing better explains the incident than an "
                "independent upstream outage."
            ),
            "confidence": 0.7,
            "source": "correlation",
        }
    ]

    return [
        {
            "symptoms": [
                {
                    "id": "symptom:alert-high-error",
                    "title": "HighErrorRate",
                    "kind": "alert",
                    "observation": (
                        "High error rate alert fired for payments-api after release."
                    ),
                    "service": "payments-api",
                    "severity": "high",
                },
                {
                    "id": "symptom:log-timeout",
                    "title": "database connection timeout",
                    "kind": "log",
                    "observation": (
                        "Logs show repeated connection timeouts talking to database."
                    ),
                    "service": "payments-api",
                    "severity": "high",
                },
                {
                    "id": "symptom:metric-error-rate",
                    "title": "error_rate spike",
                    "kind": "metric",
                    "observation": "error_rate increased to 0.9.",
                    "service": "payments-api",
                    "severity": "high",
                },
            ],
            "summary": (
                "Checkout failures coincide with a payments-api release, "
                "database timeouts, and an error-rate alert."
            ),
        },
        {
            "hypotheses": [primary, alternative],
            "summary": "Two ranked candidate root causes identified.",
        },
        {
            "evaluations": [
                {
                    "hypothesis": primary,
                    "supporting_evidence": supporting,
                    "contradicting_evidence": [
                        {
                            "key": "metric:error-rate-pre",
                            "description": (
                                "A smaller error_rate elevation (0.12) existed "
                                "before the post-deploy spike to 0.9."
                            ),
                            "confidence": 0.28,
                            "source": "metric",
                        }
                    ],
                    "temporal_consistency_score": 0.88,
                    "dependency_consistency_score": 0.8,
                },
                {
                    "hypothesis": alternative,
                    "supporting_evidence": [],
                    "contradicting_evidence": contradicting_for_alt,
                    "temporal_consistency_score": 0.35,
                    "dependency_consistency_score": 0.3,
                },
            ],
            "ranked_titles": [
                "Deployment regression",
                "Upstream dependency failure",
            ],
            "summary": "Deployment regression is the strongest explanation.",
        },
        {
            "status": "confident",
            "primary_hypothesis": primary,
            "confidence": 0.86,
            "supporting_evidence": supporting,
            "contradicting_evidence": [
                {
                    "key": "note:no-upstream-alert",
                    "description": (
                        "No independent upstream outage alert was present in "
                        "the same window."
                    ),
                    "confidence": 0.55,
                    "source": "absence",
                }
            ],
            "alternative_hypotheses": [alternative],
            "verification_steps": [
                {
                    "title": "Compare error rate before and after v1.2.2",
                    "description": (
                        "Confirm error_rate jumped immediately after the "
                        "payments-api v1.2.2 deployment."
                    ),
                    "priority": 1,
                },
                {
                    "title": "Inspect DB connection pool settings in the release",
                    "description": (
                        "Review connection pool / timeout changes introduced "
                        "in commit deploy123."
                    ),
                    "priority": 2,
                },
                {
                    "title": "Roll back or canary the previous version",
                    "description": (
                        "Validate whether reverting payments-api clears "
                        "timeouts and HighErrorRate."
                    ),
                    "priority": 3,
                },
            ],
            "evidence_quality": 86,
        },
    ]

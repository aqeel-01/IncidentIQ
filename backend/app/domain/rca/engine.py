"""Root cause analysis engine."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from app.ai.provider import AIProvider
from app.ai.types import StructuredGenerateRequest
from app.domain.rca.config import RCAEngineConfig
from app.domain.rca.package import RCAEvidencePackage
from app.domain.rca.prompts import (
    RCAPromptContext,
    RCAPromptStage,
    prompt_context_from_values,
    render_rca_prompt,
)
from app.domain.rca.types import (
    EvaluatedHypothesis,
    Hypothesis,
    RCAHypothesisEvaluationResult,
    RCAHypothesisSet,
    RCAResult,
    RCAStatus,
    RCASymptomAnalysisResult,
    VerificationStep,
)

T = TypeVar("T", bound=BaseModel)

_RAW_LOG_MARKERS = ("raw_data", "raw_logs", "fingerprint")


class RCAEngineResult(BaseModel):
    """Full outcome of an RCA engine run."""

    model_config = ConfigDict(frozen=True)

    result: RCAResult
    engine_version: str
    prompt_version: str
    ai_provider: str
    ai_model: str
    symptom_analysis: RCASymptomAnalysisResult | None = None
    hypothesis_set: RCAHypothesisSet | None = None
    hypothesis_evaluation: RCAHypothesisEvaluationResult | None = None


class RCAEngine:
    """Multi-stage RCA engine backed by the AI provider abstraction."""

    def __init__(self, *, config: RCAEngineConfig) -> None:
        self._config = config

    async def analyze(
        self,
        package: RCAEvidencePackage,
        provider: AIProvider,
    ) -> RCAEngineResult:
        """Run the RCA pipeline against a structured evidence package."""

        evidence_package_json = _package_json(package)
        _assert_no_raw_logs(evidence_package_json)

        if _is_evidence_insufficient(package, self._config):
            return _engine_result(
                provider,
                config=self._config,
                result=_insufficient_evidence_result(package),
            )

        symptom_analysis = await self._run_stage(
            provider,
            stage=RCAPromptStage.SYMPTOM_EXTRACTION,
            context=prompt_context_from_values(
                evidence_package_json=evidence_package_json,
            ),
            response_model=RCASymptomAnalysisResult,
        )
        symptoms_json = symptom_analysis.model_dump_json()

        hypothesis_set = await self._run_stage(
            provider,
            stage=RCAPromptStage.HYPOTHESIS_GENERATION,
            context=prompt_context_from_values(
                evidence_package_json=evidence_package_json,
                symptoms_json=symptoms_json,
            ),
            response_model=RCAHypothesisSet,
        )
        if not hypothesis_set.hypotheses:
            return _engine_result(
                provider,
                config=self._config,
                result=_insufficient_evidence_result(package),
                symptom_analysis=symptom_analysis,
                hypothesis_set=hypothesis_set,
            )

        hypotheses_json = hypothesis_set.model_dump_json()
        ai_evaluation = await self._run_stage(
            provider,
            stage=RCAPromptStage.EVIDENCE_EVALUATION,
            context=prompt_context_from_values(
                evidence_package_json=evidence_package_json,
                hypotheses_json=hypotheses_json,
            ),
            response_model=RCAHypothesisEvaluationResult,
        )
        hypothesis_evaluation = _merge_deterministic_evaluation(
            package,
            ai_evaluation,
            hypothesis_set.hypotheses,
        )
        evaluation_json = hypothesis_evaluation.model_dump_json()

        ai_result = await self._run_stage(
            provider,
            stage=RCAPromptStage.FINAL_RCA,
            context=prompt_context_from_values(
                evidence_package_json=evidence_package_json,
                symptoms_json=symptoms_json,
                hypotheses_json=hypotheses_json,
                evaluation_json=evaluation_json,
            ),
            response_model=RCAResult,
        )
        result = _finalize_result(
            ai_result,
            package=package,
            config=self._config,
            hypothesis_evaluation=hypothesis_evaluation,
        )

        return _engine_result(
            provider,
            config=self._config,
            result=result,
            symptom_analysis=symptom_analysis,
            hypothesis_set=hypothesis_set,
            hypothesis_evaluation=hypothesis_evaluation,
        )

    async def _run_stage(
        self,
        provider: AIProvider,
        *,
        stage: RCAPromptStage,
        context: RCAPromptContext,
        response_model: type[T],
    ) -> T:
        bundle = render_rca_prompt(
            stage,
            version=self._config.prompt_version,
            context=context,
        )
        _assert_no_raw_logs(bundle.user_prompt)
        _assert_no_raw_logs(bundle.system_prompt)

        response = await provider.structured_generate(
            StructuredGenerateRequest(
                prompt=bundle.user_prompt,
                system_prompt=bundle.system_prompt,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            ),
            response_model=response_model,
        )
        return response_model.model_validate(response.data)


def _package_json(package: RCAEvidencePackage) -> str:
    return json.dumps(package.model_dump(mode="json"), indent=2, sort_keys=True)


def _assert_no_raw_logs(text: str) -> None:
    lowered = text.lower()
    for marker in _RAW_LOG_MARKERS:
        if marker in lowered:
            msg = f"RCA engine must not send raw logs to the model; found {marker!r}"
            raise ValueError(msg)


def _is_evidence_insufficient(
    package: RCAEvidencePackage,
    config: RCAEngineConfig,
) -> bool:
    quality = package.evidence_quality.score if package.evidence_quality else 0
    if quality < config.min_evidence_quality:
        return True

    has_signals = any(
        (
            package.symptoms,
            package.error_groups,
            package.anomalies,
            package.deployments,
            package.timeline,
        )
    )
    return not has_signals


def _engine_result(
    provider: AIProvider,
    *,
    config: RCAEngineConfig,
    result: RCAResult,
    symptom_analysis: RCASymptomAnalysisResult | None = None,
    hypothesis_set: RCAHypothesisSet | None = None,
    hypothesis_evaluation: RCAHypothesisEvaluationResult | None = None,
) -> RCAEngineResult:
    return RCAEngineResult(
        result=result,
        engine_version=config.engine_version,
        prompt_version=config.prompt_version,
        ai_provider=provider.name.value,
        ai_model=provider.model,
        symptom_analysis=symptom_analysis,
        hypothesis_set=hypothesis_set,
        hypothesis_evaluation=hypothesis_evaluation,
    )


def _insufficient_evidence_result(package: RCAEvidencePackage) -> RCAResult:
    quality = package.evidence_quality.score if package.evidence_quality else 0
    return RCAResult(
        status=RCAStatus.NO_CONFIDENT_ROOT_CAUSE,
        primary_hypothesis=None,
        confidence=0.0,
        supporting_evidence=[],
        contradicting_evidence=[],
        alternative_hypotheses=[],
        verification_steps=[
            VerificationStep(
                title="Collect additional incident evidence",
                description=(
                    "The supplied evidence package is insufficient to determine "
                    "a confident root cause. Gather more timeline, error, and "
                    "deployment data before re-running analysis."
                ),
                priority=1,
            )
        ],
        evidence_quality=quality,
    )


def _temporal_consistency_score(package: RCAEvidencePackage) -> float:
    if not package.correlations:
        return 0.0
    return round(
        sum(correlation.score for correlation in package.correlations)
        / len(package.correlations),
        4,
    )


def _dependency_consistency_score(package: RCAEvidencePackage) -> float:
    graph = package.evidence_graph
    if graph is None or not graph.chain:
        return 0.0

    chain_score = min(1.0, len(graph.chain) / 5)
    if not graph.edges:
        return round(chain_score, 4)

    edge_average = sum(edge.confidence for edge in graph.edges) / len(graph.edges)
    return round((0.6 * chain_score) + (0.4 * edge_average), 4)


def _merge_deterministic_evaluation(
    package: RCAEvidencePackage,
    ai_evaluation: RCAHypothesisEvaluationResult,
    hypotheses: list[Hypothesis],
) -> RCAHypothesisEvaluationResult:
    temporal_score = _temporal_consistency_score(package)
    dependency_score = _dependency_consistency_score(package)

    evaluations_by_title = {
        evaluation.hypothesis.title: evaluation
        for evaluation in ai_evaluation.evaluations
    }
    merged_evaluations: list[EvaluatedHypothesis] = []

    for hypothesis in hypotheses:
        existing = evaluations_by_title.get(hypothesis.title)
        if existing is None:
            merged_evaluations.append(
                EvaluatedHypothesis(
                    hypothesis=hypothesis,
                    temporal_consistency_score=temporal_score,
                    dependency_consistency_score=dependency_score,
                )
            )
            continue

        merged_evaluations.append(
            existing.model_copy(
                update={
                    "temporal_consistency_score": round(
                        (existing.temporal_consistency_score + temporal_score) / 2,
                        4,
                    ),
                    "dependency_consistency_score": round(
                        (existing.dependency_consistency_score + dependency_score) / 2,
                        4,
                    ),
                }
            )
        )

    ranked = _rank_evaluations(merged_evaluations)
    ranked_titles = [evaluation.hypothesis.title for evaluation in ranked]

    return RCAHypothesisEvaluationResult(
        evaluations=ranked,
        ranked_titles=ranked_titles,
        summary=ai_evaluation.summary,
    )


def _rank_evaluations(
    evaluations: list[EvaluatedHypothesis],
) -> list[EvaluatedHypothesis]:
    return sorted(
        evaluations,
        key=lambda item: (
            -_combined_confidence(item),
            item.hypothesis.title,
        ),
    )


def _combined_confidence(evaluation: EvaluatedHypothesis) -> float:
    return round(
        (0.5 * evaluation.hypothesis.confidence)
        + (0.25 * evaluation.temporal_consistency_score)
        + (0.25 * evaluation.dependency_consistency_score),
        4,
    )


def _finalize_result(
    ai_result: RCAResult,
    *,
    package: RCAEvidencePackage,
    config: RCAEngineConfig,
    hypothesis_evaluation: RCAHypothesisEvaluationResult,
) -> RCAResult:
    evidence_quality = (
        package.evidence_quality.score
        if package.evidence_quality is not None
        else ai_result.evidence_quality
    )
    top_evaluation = hypothesis_evaluation.evaluations[0]
    combined_confidence = _combined_confidence(top_evaluation)

    if (
        evidence_quality < config.min_evidence_quality
        or combined_confidence < config.min_confidence
    ):
        return _insufficient_evidence_result(package).model_copy(
            update={
                "supporting_evidence": top_evaluation.supporting_evidence,
                "contradicting_evidence": top_evaluation.contradicting_evidence,
                "alternative_hypotheses": [
                    evaluation.hypothesis
                    for evaluation in hypothesis_evaluation.evaluations[1:]
                ],
                "verification_steps": ai_result.verification_steps
                or _insufficient_evidence_result(package).verification_steps,
                "evidence_quality": evidence_quality,
            }
        )

    status = ai_result.status
    if combined_confidence < config.confident_threshold:
        status = RCAStatus.LOW_CONFIDENCE
    elif status is RCAStatus.NO_CONFIDENT_ROOT_CAUSE:
        status = RCAStatus.LOW_CONFIDENCE

    primary_hypothesis = top_evaluation.hypothesis
    alternative_hypotheses = [
        evaluation.hypothesis for evaluation in hypothesis_evaluation.evaluations[1:]
    ]

    return RCAResult(
        status=status,
        primary_hypothesis=primary_hypothesis,
        confidence=combined_confidence,
        supporting_evidence=top_evaluation.supporting_evidence,
        contradicting_evidence=top_evaluation.contradicting_evidence,
        alternative_hypotheses=alternative_hypotheses,
        verification_steps=ai_result.verification_steps,
        evidence_quality=evidence_quality,
    )

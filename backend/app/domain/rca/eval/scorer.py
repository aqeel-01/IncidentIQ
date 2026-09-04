"""Metric scorers for the RCA evaluation framework."""

from __future__ import annotations

from statistics import mean

from app.domain.rca.engine import RCAEngineResult
from app.domain.rca.eval.matching import (
    filter_grounded_keys,
    filter_matched_gold_keys,
    find_matching_title,
    titles_match,
)
from app.domain.rca.eval.package_keys import extract_package_evidence_keys
from app.domain.rca.eval.types import (
    BackendAggregateMetrics,
    BenchmarkCase,
    CalibrationBin,
    CaseMetricScores,
    EvalBackendName,
)
from app.domain.rca.types import RCAStatus


def predicted_ranking(engine_result: RCAEngineResult) -> list[str]:
    """Best-effort ranked hypothesis titles from an engine result."""

    evaluation = engine_result.hypothesis_evaluation
    if evaluation is not None and evaluation.ranked_titles:
        return list(evaluation.ranked_titles)

    titles: list[str] = []
    primary = engine_result.result.primary_hypothesis
    if primary is not None:
        titles.append(primary.title)
    for alternative in engine_result.result.alternative_hypotheses:
        if alternative.title not in titles:
            titles.append(alternative.title)
    return titles


def cited_evidence_keys(engine_result: RCAEngineResult) -> list[str]:
    """Unique evidence keys cited in the final RCA result."""

    keys: list[str] = []
    for item in engine_result.result.supporting_evidence:
        if item.key not in keys:
            keys.append(item.key)
    for item in engine_result.result.contradicting_evidence:
        if item.key not in keys:
            keys.append(item.key)
    return keys


def kendall_tau_score(
    gold_order: list[str], predicted_order: list[str]
) -> float | None:
    """Normalized Kendall tau over gold items present in the prediction.

    Returns None when fewer than two gold titles appear in the prediction.
    """

    predicted_index = {title: idx for idx, title in enumerate(predicted_order)}
    present = [title for title in gold_order if title in predicted_index]
    if len(present) < 2:
        # Try fuzzy: map gold to first predicted match by exact string only here;
        # callers pass already-aligned titles when possible.
        return None

    concordant = 0
    discordant = 0
    for i in range(len(present)):
        for j in range(i + 1, len(present)):
            left = present[i]
            right = present[j]
            if predicted_index[left] < predicted_index[right]:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return None
    return (concordant - discordant) / total


def align_gold_ranking(
    gold_titles: list[str],
    predicted_titles: list[str],
    aliases_by_title: dict[str, list[str]],
) -> list[str]:
    """Map gold titles onto matching predicted titles for ranking comparison."""

    aligned: list[str] = []
    for gold in gold_titles:
        aliases = aliases_by_title.get(gold, [])
        match = find_matching_title(predicted_titles, gold, aliases)
        if match is not None and match not in aligned:
            aligned.append(match)
    return aligned


def score_case(
    case: BenchmarkCase,
    engine_result: RCAEngineResult,
    *,
    backend: EvalBackendName,
) -> CaseMetricScores:
    """Score a single RCA engine result against gold labels."""

    gold = case.gold
    result = engine_result.result
    ranking = predicted_ranking(engine_result)
    primary_title = (
        result.primary_hypothesis.title if result.primary_hypothesis else None
    )

    if (
        gold.allow_no_root_cause
        or gold.expected_status is RCAStatus.NO_CONFIDENT_ROOT_CAUSE
    ):
        accurate = result.status is RCAStatus.NO_CONFIDENT_ROOT_CAUSE or (
            result.primary_hypothesis is None
        )
    else:
        accurate = titles_match(
            primary_title,
            gold.root_cause_title,
            gold.root_cause_aliases,
        )

    primary_rank: int | None = None
    reciprocal_rank = 0.0
    matched = find_matching_title(
        ranking,
        gold.root_cause_title,
        gold.root_cause_aliases,
    )
    if matched is not None:
        primary_rank = ranking.index(matched) + 1
        reciprocal_rank = 1.0 / primary_rank

    aliases_by_title = {
        gold.root_cause_title: list(gold.root_cause_aliases),
        **{title: [] for title in gold.ranked_hypothesis_titles},
    }
    aligned_gold = align_gold_ranking(
        gold.ranked_hypothesis_titles or [gold.root_cause_title],
        ranking,
        aliases_by_title,
    )
    ranking_tau = kendall_tau_score(aligned_gold, ranking)

    cited = cited_evidence_keys(engine_result)
    package_keys = extract_package_evidence_keys(case.package)
    valid_keys = list(
        dict.fromkeys(
            [*package_keys, *gold.valid_evidence_keys, *gold.supporting_evidence_keys]
        )
    )
    grounded = filter_grounded_keys(cited, valid_keys)
    hallucinated = [key for key in cited if key not in grounded]
    hallucination_rate = (len(hallucinated) / len(cited)) if cited else 0.0

    grounding_precision: float | None = None
    grounding_recall: float | None = None
    grounding_f1: float | None = None
    gold_support = gold.supporting_evidence_keys
    if gold_support:
        matched_gold = filter_matched_gold_keys(cited, gold_support)
        grounding_precision = (len(matched_gold) / len(cited)) if cited else 0.0
        grounding_recall = len(matched_gold) / len(gold_support)
        if grounding_precision + grounding_recall > 0:
            grounding_f1 = (
                2
                * grounding_precision
                * grounding_recall
                / (grounding_precision + grounding_recall)
            )
        else:
            grounding_f1 = 0.0

    return CaseMetricScores(
        case_id=case.id,
        backend=backend,
        accurate=accurate,
        primary_title=primary_title,
        primary_rank=primary_rank,
        reciprocal_rank=reciprocal_rank,
        ranking_kendall_tau=ranking_tau,
        grounding_precision=grounding_precision,
        grounding_recall=grounding_recall,
        grounding_f1=grounding_f1,
        hallucination_rate=hallucination_rate,
        cited_evidence_keys=cited,
        hallucinated_keys=hallucinated,
        confidence=result.confidence,
        status=result.status.value,
    )


def _mean_or_none(values: list[float]) -> float | None:
    return mean(values) if values else None


def expected_calibration_error(
    confidences: list[float],
    correct: list[bool],
    *,
    n_bins: int = 10,
) -> tuple[float | None, list[CalibrationBin]]:
    """Compute ECE over equal-width confidence bins."""

    if not confidences:
        return None, []
    if len(confidences) != len(correct):
        msg = "confidences and correct flags must be the same length"
        raise ValueError(msg)

    bins: list[CalibrationBin] = []
    ece = 0.0
    total = len(confidences)
    for index in range(n_bins):
        lower = index / n_bins
        upper = (index + 1) / n_bins
        selected_conf: list[float] = []
        selected_correct: list[bool] = []
        for confidence, is_correct in zip(confidences, correct, strict=True):
            in_bin = (
                (confidence >= lower and confidence < upper)
                if index < n_bins - 1
                else (confidence >= lower and confidence <= upper)
            )
            if in_bin:
                selected_conf.append(confidence)
                selected_correct.append(is_correct)

        if selected_conf:
            mean_conf = mean(selected_conf)
            accuracy = mean(1.0 if flag else 0.0 for flag in selected_correct)
            ece += (len(selected_conf) / total) * abs(mean_conf - accuracy)
            bins.append(
                CalibrationBin(
                    lower=lower,
                    upper=upper,
                    count=len(selected_conf),
                    mean_confidence=mean_conf,
                    accuracy=accuracy,
                )
            )
        else:
            bins.append(CalibrationBin(lower=lower, upper=upper, count=0))

    return ece, bins


def aggregate_case_scores(
    backend: EvalBackendName,
    scores: list[CaseMetricScores],
) -> BackendAggregateMetrics:
    """Aggregate per-case scores into backend-level metrics."""

    evaluated = [score for score in scores if score.error is None]
    failed = [score for score in scores if score.error is not None]

    confidences = [score.confidence for score in evaluated]
    correct_flags = [score.accurate for score in evaluated]
    ece, bins = expected_calibration_error(confidences, correct_flags)

    correct_conf = [s.confidence for s in evaluated if s.accurate]
    incorrect_conf = [s.confidence for s in evaluated if not s.accurate]

    return BackendAggregateMetrics(
        backend=backend,
        cases_evaluated=len(evaluated),
        cases_failed=len(failed),
        rca_accuracy=_mean_or_none([1.0 if s.accurate else 0.0 for s in evaluated]),
        mean_reciprocal_rank=_mean_or_none([s.reciprocal_rank for s in evaluated]),
        mean_ranking_kendall_tau=_mean_or_none(
            [
                s.ranking_kendall_tau
                for s in evaluated
                if s.ranking_kendall_tau is not None
            ]
        ),
        mean_grounding_precision=_mean_or_none(
            [
                s.grounding_precision
                for s in evaluated
                if s.grounding_precision is not None
            ]
        ),
        mean_grounding_recall=_mean_or_none(
            [s.grounding_recall for s in evaluated if s.grounding_recall is not None]
        ),
        mean_grounding_f1=_mean_or_none(
            [s.grounding_f1 for s in evaluated if s.grounding_f1 is not None]
        ),
        mean_hallucination_rate=_mean_or_none(
            [s.hallucination_rate for s in evaluated]
        ),
        expected_calibration_error=ece,
        mean_confidence_when_correct=_mean_or_none(correct_conf),
        mean_confidence_when_incorrect=_mean_or_none(incorrect_conf),
        calibration_bins=bins,
        case_scores=scores,
    )

"""Investigation pipeline stage ordering."""

from __future__ import annotations

from app.db.models.investigation_job import InvestigationStage

PIPELINE_STAGE_ORDER: tuple[InvestigationStage, ...] = (
    InvestigationStage.COLLECT_SOURCES,
    InvestigationStage.PARSE,
    InvestigationStage.NORMALIZE,
    InvestigationStage.DEDUPLICATE,
    InvestigationStage.GROUP_ERRORS,
    InvestigationStage.DETECT_ANOMALIES,
    InvestigationStage.BUILD_TIMELINE,
    InvestigationStage.CORRELATE,
    InvestigationStage.BUILD_EVIDENCE,
    InvestigationStage.CALCULATE_EVIDENCE_QUALITY,
    InvestigationStage.BUILD_RCA_PACKAGE,
    InvestigationStage.RUN_RCA,
    InvestigationStage.PERSIST_RCA,
)


def stage_is_complete(
    stage: InvestigationStage,
    artifacts: dict[str, object],
) -> bool:
    return stage.value in artifacts


def next_incomplete_stage(
    artifacts: dict[str, object],
) -> InvestigationStage | None:
    for stage in PIPELINE_STAGE_ORDER:
        if not stage_is_complete(stage, artifacts):
            return stage
    return None


def investigation_progress(artifacts: dict[str, object]) -> tuple[list[str], int, int]:
    """Return completed stage ids, total pipeline stages, and percent complete."""

    completed = [
        stage.value for stage in PIPELINE_STAGE_ORDER if stage.value in artifacts
    ]
    total = len(PIPELINE_STAGE_ORDER)
    percent = int(round(len(completed) / total * 100)) if total else 0
    return completed, total, percent

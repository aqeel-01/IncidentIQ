"""End-to-end investigation pipeline orchestration."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import create_ai_model_router
from app.ai.provider import AIProvider
from app.core.config import Settings
from app.db.models.enums import EventType, IncidentStatus
from app.db.models.event import Event
from app.db.models.incident import Incident
from app.db.models.investigation_job import (
    InvestigationJob,
    InvestigationJobStatus,
    InvestigationStage,
)
from app.db.models.service import Service
from app.domain.deduplication import ErrorGroupDeduplicationService
from app.domain.deduplication.service import error_group_input_from_normalized
from app.domain.events import CanonicalEventBase, LogEvent
from app.domain.fingerprinting import compute_logical_error_fingerprint
from app.domain.ingestion import EventIngestionService, IngestionStatus
from app.domain.investigation.converters import normalized_log_record_to_event
from app.domain.investigation.sources import (
    CollectedInvestigationSources,
    InvestigationSources,
)
from app.domain.investigation.stages import next_incomplete_stage
from app.domain.investigation.types import InvestigationJobError, InvestigationJobResult
from app.domain.normalization import normalize_log_event, normalize_parsed_records
from app.domain.normalization.types import NormalizedLogRecord
from app.domain.parsing.parsers.plain_text import PlainTextLogParser
from app.domain.parsing.pipeline import LogParsingPipeline
from app.domain.parsing.types import LogFormat, ParsedLogRecord
from app.domain.rca import (
    RCAEngine,
    RCAEngineResult,
    build_rca_evidence_package,
    rca_engine_config_from_settings,
)
from app.domain.rca.package import RCAHistoricalContext
from app.domain.rca.service import RCAService
from app.domain.similar_incidents import (
    SimilarIncidentRetrievalService,
    similar_incident_retrieval_config_from_settings,
)
from app.domain.timeline.service import TimelineService
from app.domain.timeline.types import TimelineResult

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PipelineState:
    collected: CollectedInvestigationSources = field(
        default_factory=CollectedInvestigationSources
    )
    parsed_records: list[ParsedLogRecord] = field(default_factory=list)
    normalized_records: list[NormalizedLogRecord] = field(default_factory=list)
    canonical_events: list[CanonicalEventBase] = field(default_factory=list)
    ingested_event_ids: list[int] = field(default_factory=list)
    error_group_ids: list[int] = field(default_factory=list)
    timeline: TimelineResult | None = None
    evidence_group_id: int | None = None
    evidence_quality_score: int | None = None
    correlation_count: int = 0
    anomaly_count: int = 0
    rca_engine_result: RCAEngineResult | None = None
    rca_result_id: int | None = None
    historical_context: RCAHistoricalContext | None = None


class InvestigationOrchestrator:
    """Coordinate the full investigation pipeline with resumable stages."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        sources: InvestigationSources | None = None,
        ai_provider: AIProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._sources = sources or InvestigationSources()
        self._ai_provider = ai_provider
        self._parser = LogParsingPipeline()
        self._plain_text_parser = PlainTextLogParser()

    async def run(self, job_id: str) -> InvestigationJobResult:
        job = await self._load_job(job_id)
        if job is None:
            msg = f"investigation job {job_id} not found"
            raise InvestigationJobError(msg)

        incident = await self._load_incident(job.incident_id, job.project_id)
        if incident is None:
            msg = (
                f"incident {job.incident_id} not found for project {job.project_id}"
            )
            await self._mark_failed(job, error=msg)
            raise InvestigationJobError(msg)

        await self._mark_running(job)
        incident.status = IncidentStatus.INVESTIGATING

        state = _PipelineState()
        artifacts: dict[str, Any] = dict(job.stage_artifacts or {})
        self._hydrate_state_from_artifacts(state, artifacts)

        try:
            while True:
                stage = next_incomplete_stage(artifacts)
                if stage is None:
                    break

                job.stage = stage
                await self._session.flush()

                artifact = await self._run_stage(stage, job, incident, state)
                artifacts[stage.value] = artifact
                job.stage_artifacts = artifacts
                await self._session.flush()

            await self._mark_completed(job)
            return InvestigationJobResult(
                job_id=job.id,
                incident_id=job.incident_id,
                status=job.status,
                stage=job.stage,
            )
        except Exception as exc:
            logger.exception(
                "investigation job %s failed at stage %s",
                job.id,
                job.stage,
            )
            await self._mark_failed(job, error=str(exc))
            raise InvestigationJobError(str(exc)) from exc

    async def _run_stage(
        self,
        stage: InvestigationStage,
        job: InvestigationJob,
        incident: Incident,
        state: _PipelineState,
    ) -> dict[str, Any]:
        if stage is InvestigationStage.COLLECT_SOURCES:
            return await self._stage_collect_sources(state)
        if stage is InvestigationStage.PARSE:
            return await self._stage_parse(state)
        if stage is InvestigationStage.NORMALIZE:
            return await self._stage_normalize(state)
        if stage is InvestigationStage.DEDUPLICATE:
            return await self._stage_deduplicate(state)
        if stage is InvestigationStage.GROUP_ERRORS:
            return await self._stage_group_errors(job, state)
        if stage in {
            InvestigationStage.DETECT_ANOMALIES,
            InvestigationStage.BUILD_TIMELINE,
            InvestigationStage.CORRELATE,
            InvestigationStage.BUILD_EVIDENCE,
            InvestigationStage.CALCULATE_EVIDENCE_QUALITY,
        }:
            return await self._stage_timeline_bundle(stage, incident, state)
        if stage is InvestigationStage.BUILD_RCA_PACKAGE:
            return await self._stage_build_rca_package(incident, state)
        if stage is InvestigationStage.RUN_RCA:
            return await self._stage_run_rca(incident, state)
        if stage is InvestigationStage.PERSIST_RCA:
            return await self._stage_persist_rca(job, incident, state)
        msg = f"unsupported investigation stage {stage.value}"
        raise InvestigationJobError(msg)

    async def _stage_collect_sources(self, state: _PipelineState) -> dict[str, Any]:
        if not state.collected.canonical_events:
            state.collected.canonical_events.extend(self._sources.canonical_events)
        if not state.collected.raw_log_lines:
            state.collected.raw_log_lines.extend(self._sources.raw_log_lines)
        if not state.collected.log_file_paths:
            state.collected.log_file_paths.extend(self._sources.log_file_paths)
        return {
            "canonical_events": len(state.collected.canonical_events),
            "raw_log_lines": len(state.collected.raw_log_lines),
            "log_file_paths": len(state.collected.log_file_paths),
        }

    async def _stage_parse(self, state: _PipelineState) -> dict[str, Any]:
        if state.parsed_records:
            return {"parsed_records": len(state.parsed_records)}

        for line in state.collected.raw_log_lines:
            handle = io.StringIO(line + "\n")
            state.parsed_records.extend(self._plain_text_parser.iter_records(handle))

        for path in state.collected.log_file_paths:
            for record in self._parser.iter_parse(Path(path)):
                state.parsed_records.append(record)

        return {"parsed_records": len(state.parsed_records)}

    async def _stage_normalize(self, state: _PipelineState) -> dict[str, Any]:
        if not state.normalized_records:
            state.normalized_records = normalize_parsed_records(state.parsed_records)

        if not state.canonical_events:
            normalized_events: list[CanonicalEventBase] = []
            for event in state.collected.canonical_events:
                if isinstance(event, LogEvent):
                    normalized_events.append(normalize_log_event(event))
                else:
                    normalized_events.append(event)
            state.canonical_events = normalized_events

        return {
            "normalized_records": len(state.normalized_records),
            "canonical_events": len(state.canonical_events),
        }

    async def _stage_deduplicate(self, state: _PipelineState) -> dict[str, Any]:
        seen: set[str] = set()
        deduped: list[NormalizedLogRecord] = []
        for record in state.normalized_records:
            fingerprint = compute_logical_error_fingerprint(
                event_type=EventType.LOG,
                service=record.service,
                severity=record.severity,
                normalized_message=record.normalized_message,
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(record)
        removed = len(state.normalized_records) - len(deduped)
        state.normalized_records = deduped
        return {"kept": len(deduped), "removed": removed}

    async def _stage_group_errors(
        self,
        job: InvestigationJob,
        state: _PipelineState,
    ) -> dict[str, Any]:
        if state.ingested_event_ids and state.error_group_ids:
            return {
                "ingested_event_ids": state.ingested_event_ids,
                "error_group_ids": state.error_group_ids,
            }

        ingestion = EventIngestionService(self._session)
        dedupe = ErrorGroupDeduplicationService(self._session)

        events_to_ingest: list[CanonicalEventBase] = list(state.canonical_events)
        for record in state.normalized_records:
            events_to_ingest.append(
                normalized_log_record_to_event(record, source="investigation")
            )

        batch = await ingestion.ingest_batch(job.project_id, events_to_ingest)
        for result in batch.results:
            if result.status is not IngestionStatus.ACCEPTED or result.event_id is None:
                continue
            state.ingested_event_ids.append(result.event_id)

        log_format = (
            state.parsed_records[0].format
            if state.parsed_records
            else LogFormat.PLAIN_TEXT
        )
        for event_id in state.ingested_event_ids:
            event = await self._session.get(Event, event_id)
            if event is None or event.event_type is not EventType.LOG:
                continue

            normalized_message = event.message
            if event.normalized_data:
                value = event.normalized_data.get("normalized_message")
                if isinstance(value, str) and value:
                    normalized_message = value
            if not normalized_message:
                continue

            merge_input = error_group_input_from_normalized(
                NormalizedLogRecord(
                    line_number=0,
                    format=log_format,
                    timestamp=event.timestamp,
                    severity=event.severity,
                    message=event.message,
                    normalized_message=normalized_message,
                    service=None,
                    raw_data=dict(event.raw_data),
                    normalized_data=dict(event.normalized_data or {}),
                ),
                project_id=job.project_id,
                source=event.source,
                service_id=event.service_id,
            )
            merge_result = await dedupe.merge(merge_input)
            event.error_group_id = merge_result.error_group_id
            if merge_result.error_group_id not in state.error_group_ids:
                state.error_group_ids.append(merge_result.error_group_id)

        await self._session.flush()
        return {
            "ingested_event_ids": state.ingested_event_ids,
            "error_group_ids": state.error_group_ids,
        }

    async def _stage_timeline_bundle(
        self,
        stage: InvestigationStage,
        incident: Incident,
        state: _PipelineState,
    ) -> dict[str, Any]:
        timeline = await self._ensure_timeline(incident, state)

        if stage is InvestigationStage.DETECT_ANOMALIES:
            return {"anomaly_count": state.anomaly_count}
        if stage is InvestigationStage.BUILD_TIMELINE:
            return {"entry_count": len(timeline.entries)}
        if stage is InvestigationStage.CORRELATE:
            return {"correlation_count": state.correlation_count}
        if stage is InvestigationStage.BUILD_EVIDENCE:
            return {"evidence_group_id": state.evidence_group_id}
        return {"evidence_quality_score": state.evidence_quality_score}

    async def _stage_build_rca_package(
        self,
        incident: Incident,
        state: _PipelineState,
    ) -> dict[str, Any]:
        timeline = await self._ensure_timeline(incident, state)
        service_names = await self._load_service_names(incident.project_id)
        state.historical_context = await self._load_historical_context(
            incident,
            timeline,
            service_names,
        )
        package = build_rca_evidence_package(
            incident=incident,
            timeline=timeline,
            service_names=service_names,
            historical_context=state.historical_context,
        )
        return {
            "incident_id": incident.id,
            "has_package": package is not None,
            "similar_incident_count": len(
                state.historical_context.related_incident_ids
            )
            if state.historical_context is not None
            else 0,
        }

    async def _stage_run_rca(
        self,
        incident: Incident,
        state: _PipelineState,
    ) -> dict[str, Any]:
        if state.rca_engine_result is not None:
            return {
                "status": state.rca_engine_result.result.status.value,
                "confidence": state.rca_engine_result.result.confidence,
            }

        timeline = await self._ensure_timeline(incident, state)
        service_names = await self._load_service_names(incident.project_id)
        if state.historical_context is None:
            state.historical_context = await self._load_historical_context(
                incident,
                timeline,
                service_names,
            )
        package = build_rca_evidence_package(
            incident=incident,
            timeline=timeline,
            service_names=service_names,
            historical_context=state.historical_context,
        )
        router = create_ai_model_router(self._settings)
        provider = self._ai_provider or router.get_provider()
        engine = RCAEngine(config=rca_engine_config_from_settings(self._settings))
        state.rca_engine_result = await engine.analyze(package, provider)
        return {
            "status": state.rca_engine_result.result.status.value,
            "confidence": state.rca_engine_result.result.confidence,
        }

    async def _stage_persist_rca(
        self,
        job: InvestigationJob,
        incident: Incident,
        state: _PipelineState,
    ) -> dict[str, Any]:
        if state.rca_result_id is not None:
            return {"rca_result_id": state.rca_result_id}

        if state.rca_engine_result is None:
            msg = "RCA engine result is missing before persistence"
            raise InvestigationJobError(msg)

        row = await RCAService(self._session).persist(
            project_id=job.project_id,
            incident_id=job.incident_id,
            investigation_job_id=job.id,
            evidence_group_id=state.evidence_group_id,
            engine_result=state.rca_engine_result,
        )
        state.rca_result_id = row.id
        job.rca_result_id = row.id
        if state.rca_engine_result.result.primary_hypothesis is not None:
            incident.status = IncidentStatus.IDENTIFIED
        return {"rca_result_id": row.id}

    async def _ensure_timeline(
        self,
        incident: Incident,
        state: _PipelineState,
    ) -> TimelineResult:
        if state.timeline is not None:
            return state.timeline

        timeline = await TimelineService(self._session).build(incident.id)
        if timeline is None:
            msg = f"timeline could not be built for incident {incident.id}"
            raise InvestigationJobError(msg)

        state.timeline = timeline
        if timeline.evidence_group is not None:
            state.evidence_group_id = timeline.evidence_group.id
            if timeline.evidence_group.quality is not None:
                state.evidence_quality_score = timeline.evidence_group.quality.score
        state.correlation_count = len(timeline.correlations)
        state.anomaly_count = timeline.counts.get("metric", 0)
        return timeline

    async def _load_historical_context(
        self,
        incident: Incident,
        timeline: TimelineResult,
        service_names: dict[int, str],
    ) -> RCAHistoricalContext | None:
        retrieval = SimilarIncidentRetrievalService(
            self._session,
            config=similar_incident_retrieval_config_from_settings(self._settings),
        )
        return await retrieval.build_historical_context(
            incident=incident,
            timeline=timeline,
            service_names=service_names,
        )

    def _hydrate_state_from_artifacts(
        self,
        state: _PipelineState,
        artifacts: dict[str, Any],
    ) -> None:
        group_artifact = artifacts.get(InvestigationStage.GROUP_ERRORS.value)
        if isinstance(group_artifact, dict):
            ingested = group_artifact.get("ingested_event_ids")
            groups = group_artifact.get("error_group_ids")
            if isinstance(ingested, list):
                state.ingested_event_ids = [int(item) for item in ingested]
            if isinstance(groups, list):
                state.error_group_ids = [int(item) for item in groups]

        evidence_artifact = artifacts.get(InvestigationStage.BUILD_EVIDENCE.value)
        if isinstance(evidence_artifact, dict):
            evidence_group_id = evidence_artifact.get("evidence_group_id")
            if isinstance(evidence_group_id, int):
                state.evidence_group_id = evidence_group_id

        persist_artifact = artifacts.get(InvestigationStage.PERSIST_RCA.value)
        if isinstance(persist_artifact, dict):
            rca_result_id = persist_artifact.get("rca_result_id")
            if isinstance(rca_result_id, int):
                state.rca_result_id = rca_result_id

    async def _mark_running(self, job: InvestigationJob) -> None:
        now = datetime.now(UTC)
        job.status = InvestigationJobStatus.RUNNING
        job.attempt_count += 1
        job.error_message = None
        if job.started_at is None:
            job.started_at = now
        await self._session.flush()

    async def _mark_completed(self, job: InvestigationJob) -> None:
        job.status = InvestigationJobStatus.COMPLETED
        job.stage = InvestigationStage.COMPLETED
        job.completed_at = datetime.now(UTC)
        job.error_message = None
        await self._session.flush()

    async def _mark_failed(self, job: InvestigationJob, *, error: str) -> None:
        job.status = InvestigationJobStatus.FAILED
        job.stage = InvestigationStage.FAILED
        job.error_message = error
        job.completed_at = datetime.now(UTC)
        await self._session.flush()

    async def _load_job(self, job_id: str) -> InvestigationJob | None:
        result = await self._session.execute(
            select(InvestigationJob).where(InvestigationJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def _load_incident(
        self,
        incident_id: int,
        project_id: int,
    ) -> Incident | None:
        result = await self._session.execute(
            select(Incident).where(
                Incident.id == incident_id,
                Incident.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def _load_service_names(self, project_id: int) -> dict[int, str]:
        result = await self._session.execute(
            select(Service).where(Service.project_id == project_id)
        )
        return {service.id: service.name for service in result.scalars().all()}

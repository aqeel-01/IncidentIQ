"""Run the deterministic IncidentIQ end-to-end demo pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    InvestigationJob,
    InvestigationJobStatus,
    InvestigationStage,
    Organization,
    Project,
    Service,
    Severity,
)
from app.domain.demo.fake_ai import SequentialFakeAIProvider, demo_rca_staged_payloads
from app.domain.demo.scenario import (
    DEMO_INCIDENT_TITLE,
    DEMO_JOB_ID,
    DEMO_SERVICE,
    build_demo_sources,
    demo_timestamp,
    write_demo_log_file,
)
from app.domain.demo.types import (
    DemoEvidenceSummary,
    DemoPipelineSummary,
    DemoResult,
    DemoTimelineSummary,
)
from app.domain.evidence.service import EvidenceService
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.investigation import InvestigationOrchestrator
from app.domain.investigation.stages import PIPELINE_STAGE_ORDER
from app.domain.rca.service import RCAService
from app.domain.timeline.service import TimelineService


def demo_settings(*, database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
        rca_min_evidence_quality=20,
        rca_min_confidence=0.6,
        rca_confident_threshold=0.75,
    )


async def _create_schema(engine) -> None:
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_fk(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_demo_tenancy(session: AsyncSession) -> tuple[Project, Service, int]:
    """Create org/project/service/incident for the demo scenario."""

    org = Organization(name="IncidentIQ Demo", slug="incidentiq-demo")
    project = Project(
        name="Payments Demo",
        slug="payments-demo",
        organization=org,
    )
    service = Service(name=DEMO_SERVICE, project=project)
    session.add_all([org, project, service])
    await session.flush()

    created = await IncidentService(session).create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title=DEMO_INCIDENT_TITLE,
            environment="production",
            severity=Severity.HIGH,
            started_at=demo_timestamp(0),
        )
    )
    await session.flush()
    return project, service, created.incident.id


async def run_demo(
    *,
    work_dir: Path,
    database_url: str | None = None,
    job_id: str = DEMO_JOB_ID,
) -> DemoResult:
    """Execute alert→…→ranked RCA for the deterministic demo scenario."""

    work_dir.mkdir(parents=True, exist_ok=True)
    log_path = write_demo_log_file(work_dir / "payments-api-errors.jsonl")

    if database_url is None:
        db_path = (work_dir / "demo.db").resolve()
        if db_path.exists():
            db_path.unlink()
        database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    settings = demo_settings(database_url=database_url)
    engine_kwargs: dict = {}
    if database_url.startswith("sqlite"):
        engine_kwargs = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    engine = create_async_engine(database_url, **engine_kwargs)
    await _create_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            project, _service, incident_id = await seed_demo_tenancy(session)

            # Allow re-runs against a file DB without colliding job IDs.
            existing = await session.get(InvestigationJob, job_id)
            if existing is not None:
                job_id = f"{DEMO_JOB_ID}-{uuid.uuid4().hex[:8]}"

            job = InvestigationJob(
                id=job_id,
                project_id=project.id,
                incident_id=incident_id,
                status=InvestigationJobStatus.QUEUED,
                stage=InvestigationStage.QUEUED,
                stage_artifacts={},
            )
            session.add(job)
            await session.flush()

            provider = SequentialFakeAIProvider(demo_rca_staged_payloads())
            sources = build_demo_sources(log_file_path=log_path)
            orchestrator = InvestigationOrchestrator(
                session,
                settings,
                sources=sources,
                ai_provider=provider,
            )
            pipeline_result = await orchestrator.run(job.id)
            await session.commit()

            refreshed = await session.get(InvestigationJob, job.id)
            artifacts = dict(refreshed.stage_artifacts or {}) if refreshed else {}
            completed = [
                stage.value
                for stage in PIPELINE_STAGE_ORDER
                if stage.value in artifacts
            ]

            rca_records = await RCAService(session).list_for_incident(incident_id)
            if not rca_records:
                msg = "demo completed without a persisted RCA result"
                raise RuntimeError(msg)
            rca_record = rca_records[0]
            rca = rca_record.result

            timeline = await TimelineService(session).build(incident_id)
            evidence = await EvidenceService(session).get_latest_for_incident(
                incident_id
            )

            anomaly_count = 0
            correlation_count = 0
            deployment_correlation = None
            entry_count = 0
            if timeline is not None:
                entry_count = len(timeline.entries)
                anomaly_count = sum(
                    1
                    for item in timeline.entries
                    if isinstance(item.metadata, dict)
                    and item.metadata.get("anomaly") is True
                )
                correlation_count = len(timeline.correlations)
                if timeline.deployment_correlation is not None:
                    dep = timeline.deployment_correlation
                    deployment_correlation = (
                        f"related={dep.is_related} "
                        f"score={dep.relationship_score:.2f}: {dep.summary}"
                    )

            evidence_summary = DemoEvidenceSummary(
                evidence_group_id=evidence.id if evidence else None,
                item_count=len(evidence.evidence) if evidence else 0,
                quality_score=(
                    evidence.quality.score
                    if evidence is not None and evidence.quality is not None
                    else rca.evidence_quality
                ),
                quality_summary=(
                    evidence.quality.summary
                    if evidence is not None and evidence.quality is not None
                    else None
                ),
            )

            primary = rca.primary_hypothesis
            return DemoResult(
                generated_at=datetime.now(tz=UTC),
                incident_id=incident_id,
                project_id=project.id,
                service=DEMO_SERVICE,
                incident_title=DEMO_INCIDENT_TITLE,
                pipeline=DemoPipelineSummary(
                    job_id=pipeline_result.job_id,
                    status=pipeline_result.status.value,
                    stage=pipeline_result.stage.value,
                    stages_completed=completed,
                    stage_artifacts=artifacts,
                ),
                timeline=DemoTimelineSummary(
                    entry_count=entry_count,
                    anomaly_count=anomaly_count,
                    correlation_count=correlation_count,
                    deployment_correlation=deployment_correlation,
                ),
                evidence=evidence_summary,
                rca_status=rca.status,
                confidence=rca.confidence,
                evidence_quality=rca.evidence_quality,
                root_cause=primary.title if primary else None,
                root_cause_description=primary.description if primary else None,
                root_cause_rationale=primary.rationale if primary else None,
                supporting_evidence=[
                    item.model_dump(mode="json") for item in rca.supporting_evidence
                ],
                contradicting_evidence=[
                    item.model_dump(mode="json") for item in rca.contradicting_evidence
                ],
                alternative_hypotheses=[
                    item.model_dump(mode="json") for item in rca.alternative_hypotheses
                ],
                verification_steps=[
                    item.model_dump(mode="json") for item in rca.verification_steps
                ],
                rca=rca,
                ai_provider=rca_record.ai_provider,
                ai_model=rca_record.ai_model,
                engine_version=rca_record.engine_version,
                prompt_version=rca_record.prompt_version,
            )
    finally:
        await engine.dispose()


def write_demo_result(result: DemoResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path

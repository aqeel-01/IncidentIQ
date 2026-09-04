"""Run ingestion/investigation performance benchmarks."""

from __future__ import annotations

import json
import platform
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai import (
    AIProvider,
    AIProviderHealthResult,
    AIProviderName,
    GenerateRequest,
    GenerateResponse,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Organization, Project, Service
from app.db.models.enums import EventType
from app.domain.fingerprinting import compute_logical_error_fingerprint
from app.domain.ingestion import EventIngestionService
from app.domain.investigation.converters import normalized_log_record_to_event
from app.domain.investigation.streaming import (
    iter_normalize_and_deduplicate,
    iter_parsed_log_sources,
)
from app.domain.normalization import iter_normalize_parsed_records
from app.domain.parsing.pipeline import LogParsingPipeline
from app.domain.perf.generate import write_synthetic_jsonl
from app.domain.perf.memory import timed_stage
from app.domain.perf.types import (
    PerformanceReport,
    ScaleBenchmarkResult,
    StageTiming,
)
from app.domain.rca import (
    RCAEngine,
    RCAEvidencePackage,
    rca_engine_config_from_settings,
)
from app.domain.rca.package import (
    RCAEvidenceQualitySummary,
    RCAIncidentContext,
    RCASymptom,
)

DEFAULT_SCALES = (10_000, 100_000, 1_000_000)


class _SequentialFakeAIProvider(AIProvider):
    """Minimal staged provider for RCA engine overhead measurements."""

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self._call_index = 0

    @property
    def name(self) -> AIProviderName:
        return AIProviderName.OLLAMA

    @property
    def model(self) -> str:
        return "perf-fake-model"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        del request
        if self._call_index >= len(self._payloads):
            msg = "no more staged payloads"
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
            detail="ready",
            model=self.model,
            checked_at=datetime.now(tz=UTC),
        )


def _fake_rca_payloads() -> list[dict]:
    hypothesis = {
        "title": "Deployment regression",
        "description": "Synthetic hypothesis for perf.",
        "confidence": 0.82,
        "rationale": "perf",
    }
    return [
        {
            "symptoms": [
                {
                    "id": "s1",
                    "title": "HighErrorRate",
                    "kind": "alert",
                    "observation": "errors",
                    "service": "payments-api",
                }
            ],
            "summary": "errors observed",
        },
        {"hypotheses": [hypothesis], "summary": "one hypothesis"},
        {
            "evaluations": [
                {
                    "hypothesis": hypothesis,
                    "supporting_evidence": [
                        {
                            "key": "symptom:1",
                            "description": "alert",
                            "confidence": 0.8,
                            "source": "alert",
                        }
                    ],
                    "contradicting_evidence": [],
                    "temporal_consistency_score": 0.7,
                    "dependency_consistency_score": 0.7,
                }
            ],
            "ranked_titles": ["Deployment regression"],
            "summary": "ranked",
        },
        {
            "status": "confident",
            "primary_hypothesis": hypothesis,
            "confidence": 0.82,
            "supporting_evidence": [
                {
                    "key": "symptom:1",
                    "description": "alert",
                    "confidence": 0.8,
                    "source": "alert",
                }
            ],
            "contradicting_evidence": [],
            "alternative_hypotheses": [],
            "verification_steps": [
                {
                    "title": "Verify deploy",
                    "description": "Check release",
                    "priority": 1,
                }
            ],
            "evidence_quality": 80,
        },
    ]


def _stage_from_ctx(
    ctx: object,
    *,
    items_processed: int = 0,
    items_output: int = 0,
    notes: str | None = None,
) -> StageTiming:
    tracker = getattr(ctx, "tracker", None)
    return StageTiming(
        name=ctx.name,
        duration_seconds=ctx.duration_seconds,
        peak_rss_mb=getattr(tracker, "peak_rss_mb", None) if tracker else None,
        python_peak_mb=getattr(tracker, "python_peak_mb", None) if tracker else None,
        items_processed=items_processed,
        items_output=items_output,
        notes=notes,
    )


async def _prepare_db_session() -> tuple[object, async_sessionmaker[AsyncSession], int]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        org = Organization(name="perf-org", slug="perf-org")
        project = Project(name="perf-project", slug="perf-project", organization=org)
        session.add_all([org, project])
        await session.flush()
        session.add(Service(project_id=project.id, name="payments-api"))
        await session.commit()
        project_id = project.id

    return engine, session_factory, project_id


async def benchmark_scale(
    event_count: int,
    *,
    work_dir: Path,
    chunk_size: int = 1000,
    persist: bool = True,
    run_rca: bool = True,
) -> ScaleBenchmarkResult:
    """Benchmark one scale using incremental JSONL processing."""

    dataset_path = work_dir / f"events_{event_count}.jsonl"
    stages: list[StageTiming] = []

    with timed_stage("generate") as ctx:
        write_synthetic_jsonl(dataset_path, event_count)
    stages.append(
        _stage_from_ctx(ctx, items_processed=event_count, items_output=event_count)
    )

    pipeline = LogParsingPipeline()

    parsed_count = 0
    with timed_stage("ingestion") as ctx:
        for _record in pipeline.iter_parse(dataset_path):
            parsed_count += 1
    stages.append(
        _stage_from_ctx(
            ctx,
            items_processed=parsed_count,
            items_output=parsed_count,
            notes="JSONL line-oriented parse; no full-file load",
        )
    )

    normalized_count = 0
    with timed_stage("normalization") as ctx:
        for _record in iter_normalize_parsed_records(
            pipeline.iter_parse(dataset_path),
            copy_raw_data=False,
        ):
            normalized_count += 1
    stages.append(
        _stage_from_ctx(
            ctx,
            items_processed=normalized_count,
            items_output=normalized_count,
            notes="streaming normalize; copy_raw_data=False",
        )
    )

    stream, counters = iter_normalize_and_deduplicate(
        iter_parsed_log_sources(log_file_paths=[dataset_path]),
        copy_raw_data=False,
    )
    kept = 0
    with timed_stage("deduplication") as ctx:
        for _record in stream:
            kept += 1
    stages.append(
        _stage_from_ctx(
            ctx,
            items_processed=counters["parsed"],
            items_output=kept,
            notes=f"logical fingerprint dedupe; removed={counters['removed']}",
        )
    )

    severity_counts: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()
    analyzed = 0
    with timed_stage("analysis") as ctx:
        for record in iter_normalize_parsed_records(
            pipeline.iter_parse(dataset_path),
            copy_raw_data=False,
        ):
            analyzed += 1
            severity_counts[str(record.severity)] += 1
            fingerprint = compute_logical_error_fingerprint(
                event_type=EventType.LOG,
                service=record.service,
                severity=record.severity,
                normalized_message=record.normalized_message,
            )
            pattern_counts[fingerprint] += 1
    stages.append(
        _stage_from_ctx(
            ctx,
            items_processed=analyzed,
            items_output=len(pattern_counts),
            notes=(
                "streaming severity/fingerprint aggregates; "
                f"unique_fingerprints={len(pattern_counts)}"
            ),
        )
    )

    if persist:
        engine, session_factory, project_id = await _prepare_db_session()
        accepted = 0
        with timed_stage("db_ingest") as ctx:
            async with session_factory() as session:
                ingestion = EventIngestionService(session)

                def _events():
                    for record in iter_normalize_parsed_records(
                        pipeline.iter_parse(dataset_path),
                        copy_raw_data=False,
                    ):
                        yield normalized_log_record_to_event(
                            record,
                            source="perf",
                            copy_raw_data=False,
                        )

                batch: list = []
                for event in _events():
                    batch.append(event)
                    if len(batch) >= chunk_size:
                        result = await ingestion.ingest_batch(
                            project_id,
                            batch,
                            collect_results=False,
                        )
                        accepted += result.accepted
                        batch = []
                        await session.commit()
                if batch:
                    result = await ingestion.ingest_batch(
                        project_id,
                        batch,
                        collect_results=False,
                    )
                    accepted += result.accepted
                    await session.commit()
        stages.append(
            _stage_from_ctx(
                ctx,
                items_processed=event_count,
                items_output=accepted,
                notes=f"chunk_size={chunk_size}; collect_results=False",
            )
        )
        await engine.dispose()
    else:
        stages.append(
            StageTiming(
                name="db_ingest",
                duration_seconds=0.0,
                items_processed=0,
                items_output=0,
                notes="skipped",
            )
        )

    if run_rca:
        settings = Settings(app_env="test")
        package = _small_rca_package()
        provider = _SequentialFakeAIProvider(_fake_rca_payloads())
        rca_engine = RCAEngine(config=rca_engine_config_from_settings(settings))
        with timed_stage("rca") as ctx:
            await rca_engine.analyze(package, provider)
        stages.append(
            _stage_from_ctx(
                ctx,
                items_processed=1,
                items_output=1,
                notes="fake provider; package size independent of corpus N",
            )
        )
    else:
        stages.append(
            StageTiming(
                name="rca",
                duration_seconds=0.0,
                notes="skipped",
            )
        )

    by_name = {stage.name: stage for stage in stages}
    peak_rss = max(
        (s.peak_rss_mb for s in stages if s.peak_rss_mb is not None),
        default=None,
    )
    peak_py = max(
        (s.python_peak_mb for s in stages if s.python_peak_mb is not None),
        default=None,
    )
    # Prefer OS RSS; fall back to tracemalloc peak for platforms without RSS.
    reported_peak = peak_rss if peak_rss is not None else peak_py

    return ScaleBenchmarkResult(
        event_count=event_count,
        stages=stages,
        ingestion_seconds=by_name["ingestion"].duration_seconds,
        normalization_seconds=by_name["normalization"].duration_seconds,
        deduplication_seconds=by_name["deduplication"].duration_seconds,
        analysis_seconds=by_name["analysis"].duration_seconds,
        rca_seconds=by_name["rca"].duration_seconds,
        peak_rss_mb=reported_peak,
        python_peak_mb=peak_py,
        dataset_path=str(dataset_path),
        incremental=True,
    )


def _small_rca_package() -> RCAEvidencePackage:
    started = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    return RCAEvidencePackage(
        incident=RCAIncidentContext(
            incident_id=1,
            project_id=1,
            title="Perf RCA package",
            environment="production",
            severity="high",
            status="investigating",
            service="payments-api",
            started_at=started,
            occurrence_count=1,
        ),
        symptoms=[
            RCASymptom(
                id="symptom:1",
                kind="alert",
                timestamp=started,
                title="HighErrorRate",
                severity="critical",
                service="payments-api",
            )
        ],
        evidence_quality=RCAEvidenceQualitySummary(
            score=80,
            summary="synthetic",
            source_diversity=70,
            temporal_consistency=70,
            correlation_strength=70,
            completeness=70,
            consistency=70,
        ),
    )


async def run_performance_suite(
    *,
    scales: tuple[int, ...] = DEFAULT_SCALES,
    work_dir: Path,
    chunk_size: int = 1000,
    persist_max_events: int | None = 1_000_000,
) -> PerformanceReport:
    """Run benchmarks for each configured scale."""

    results: list[ScaleBenchmarkResult] = []
    notes = [
        "Large files are processed as JSONL streams (line-oriented).",
        (
            "Normalization/dedupe/analysis avoid full intermediate list "
            "copies where possible."
        ),
        "DB ingest uses fixed-size chunks with collect_results=False.",
        (
            "Peak memory prefers OS RSS; falls back to tracemalloc peak "
            "when RSS sampling is unavailable."
        ),
        (
            "1M DB ingest is skipped by default (`--persist-max 100000`); "
            "raise the limit to measure SQLite ORM insert cost at 1M."
        ),
    ]

    for count in scales:
        persist = persist_max_events is None or count <= persist_max_events
        results.append(
            await benchmark_scale(
                count,
                work_dir=work_dir,
                chunk_size=chunk_size,
                persist=persist,
            )
        )

    return PerformanceReport(
        generated_at=datetime.now(tz=UTC),
        host=platform.node(),
        python_version=sys.version.split()[0],
        scales=results,
        notes=notes,
    )


def write_performance_report(report: PerformanceReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def render_markdown_report(report: PerformanceReport) -> str:
    """Render a human-readable markdown summary of benchmark results."""

    lines = [
        "# Ingestion & investigation performance",
        "",
        f"Generated: `{report.generated_at.isoformat()}`  ",
        f"Host: `{report.host}`  ",
        f"Python: `{report.python_version}`",
        "",
        "## Summary",
        "",
        (
            "| Events | Ingestion (s) | Normalize (s) | Dedupe (s) | "
            "Analysis (s) | RCA (s) | Peak mem (MiB) |"
        ),
        (
            "| ------ | ------------- | ------------- | ---------- | "
            "------------ | ------- | -------------- |"
        ),
    ]
    for scale in report.scales:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                f"{scale.event_count:,}",
                _fmt(scale.ingestion_seconds),
                _fmt(scale.normalization_seconds),
                _fmt(scale.deduplication_seconds),
                _fmt(scale.analysis_seconds),
                _fmt(scale.rca_seconds),
                _fmt(scale.peak_rss_mb),
            )
        )

    lines.extend(["", "## Stage details", ""])
    for scale in report.scales:
        lines.append(f"### {scale.event_count:,} events")
        lines.append("")
        lines.append(
            "| Stage | Seconds | Processed | Output | Peak RSS (MiB) | Notes |"
        )
        lines.append(
            "| ----- | ------- | --------- | ------ | -------------- | ----- |"
        )
        for stage in scale.stages:
            lines.append(
                f"| {stage.name} | {_fmt(stage.duration_seconds)} | "
                f"{stage.items_processed:,} | {stage.items_output:,} | "
                f"{_fmt(stage.peak_rss_mb)} | {stage.notes or ''} |"
            )
        lines.append("")

    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.extend(
        [
            "## Method",
            "",
            "- Corpus: synthetic JSONL with repeating logical error patterns.",
            "- Ingestion: `LogParsingPipeline.iter_parse` (streaming).",
            (
                "- Normalization: `iter_normalize_parsed_records(..., "
                "copy_raw_data=False)`."
            ),
            "- Deduplication: streaming logical fingerprints.",
            (
                "- Analysis: streaming severity/fingerprint aggregates "
                "(no full list retain)."
            ),
            "- DB ingest: chunked `EventIngestionService.ingest_batch` "
            "with `collect_results=False`.",
            "- RCA: fixed evidence package + fake AI provider (engine overhead only).",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"

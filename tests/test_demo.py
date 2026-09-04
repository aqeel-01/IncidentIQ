"""Tests for the deterministic IncidentIQ end-to-end demo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.demo import run_demo, write_demo_result
from app.domain.demo.report import format_demo_report
from app.domain.demo.scenario import build_demo_sources, write_demo_log_file
from app.domain.rca import RCAStatus


def test_demo_scenario_includes_all_signal_types(tmp_path: Path) -> None:
    log_path = write_demo_log_file(tmp_path / "logs.jsonl")
    sources = build_demo_sources(log_file_path=log_path)
    kinds = {event.event_type.value for event in sources.canonical_events}
    assert kinds == {"DEPLOYMENT", "METRIC", "LOG", "ALERT"}
    assert sources.raw_log_lines
    assert sources.log_file_paths == (log_path,)
    assert log_path.read_text(encoding="utf-8").count("\n") == 3


@pytest.mark.asyncio
async def test_demo_runs_full_pipeline_and_exposes_rca_fields(
    tmp_path: Path,
) -> None:
    result = await run_demo(work_dir=tmp_path / "demo")

    assert result.reproducible is True
    assert result.deterministic_ai is True
    assert result.pipeline.status == "COMPLETED"
    assert "run_rca" in result.pipeline.stages_completed
    assert "persist_rca" in result.pipeline.stages_completed
    assert result.timeline.entry_count > 0
    assert result.evidence.item_count > 0
    assert result.evidence_quality >= 0

    assert result.rca_status is RCAStatus.CONFIDENT
    assert result.root_cause == "Deployment regression"
    assert result.confidence >= 0.75
    assert result.supporting_evidence
    assert result.contradicting_evidence
    assert result.alternative_hypotheses
    assert result.verification_steps
    assert result.rca.primary_hypothesis is not None
    assert result.rca.primary_hypothesis.title == "Deployment regression"

    report = format_demo_report(result)
    assert "Root cause:" in report
    assert "Supporting evidence:" in report
    assert "Contradicting evidence:" in report
    assert "Alternative hypotheses:" in report
    assert "Verification steps:" in report
    assert "Evidence quality:" in report

    output = write_demo_result(result, tmp_path / "result.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["root_cause"] == "Deployment regression"
    assert payload["rca"]["status"] == "confident"

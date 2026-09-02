"""Tests for versioned RCA prompts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.rca import (
    RCAPromptContext,
    RCAPromptError,
    RCAPromptStage,
    list_rca_prompt_versions,
    prompt_context_from_values,
    rca_prompt_version_from_settings,
    render_rca_prompt,
)
from app.domain.rca.prompts import _load_shared_guardrails

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "rca_prompts"
EVIDENCE_PACKAGE_FIXTURE = (
    Path(__file__).parent / "fixtures" / "rca_evidence_package_full.json"
)

_REQUIRED_GUARDRAILS = (
    "Use only the evidence explicitly supplied",
    "distinguish observed facts from inferred hypotheses",
    "contradictory evidence",
    "unsupported claims",
    "rank them by confidence",
    "insufficient evidence",
)

_STAGE_CONTEXT: dict[RCAPromptStage, dict[str, str]] = {
    RCAPromptStage.SYMPTOM_EXTRACTION: {
        "evidence_package_json": "{}",
    },
    RCAPromptStage.HYPOTHESIS_GENERATION: {
        "evidence_package_json": "{}",
        "symptoms_json": "[]",
    },
    RCAPromptStage.EVIDENCE_EVALUATION: {
        "evidence_package_json": "{}",
        "hypotheses_json": "[]",
    },
    RCAPromptStage.FINAL_RCA: {
        "evidence_package_json": "{}",
        "symptoms_json": "[]",
        "hypotheses_json": "[]",
        "evaluation_json": "{}",
    },
    RCAPromptStage.REPORT_GENERATION: {
        "evidence_package_json": "{}",
        "rca_result_json": "{}",
    },
}


def _full_context() -> RCAPromptContext:
    evidence = EVIDENCE_PACKAGE_FIXTURE.read_text(encoding="utf-8")
    return prompt_context_from_values(
        evidence_package_json=evidence,
        symptoms_json='[{"id": "event:3", "title": "HighErrorRate"}]',
        hypotheses_json='[{"title": "Deployment regression", "confidence": 0.7}]',
        evaluation_json='{"primary": {"confidence": 0.7}}',
        rca_result_json='{"status": "confident", "confidence": 0.82}',
    )


@pytest.mark.parametrize("stage", list(RCAPromptStage))
def test_render_rca_prompt_includes_guardrails(stage: RCAPromptStage) -> None:
    bundle = render_rca_prompt(
        stage,
        version="v1",
        context=prompt_context_from_values(**_STAGE_CONTEXT[stage]),
    )

    combined = f"{bundle.system_prompt}\n{bundle.user_prompt}"
    for phrase in _REQUIRED_GUARDRAILS:
        assert phrase in combined


@pytest.mark.parametrize("stage", list(RCAPromptStage))
def test_render_rca_prompt_is_deterministic(stage: RCAPromptStage) -> None:
    context = prompt_context_from_values(**_STAGE_CONTEXT[stage])

    first = render_rca_prompt(stage, version="v1", context=context)
    second = render_rca_prompt(stage, version="v1", context=context)

    assert first == second


@pytest.mark.parametrize("stage", list(RCAPromptStage))
def test_render_rca_prompt_snapshot(stage: RCAPromptStage) -> None:
    bundle = render_rca_prompt(
        stage,
        version="v1",
        context=_full_context(),
    )
    snapshot_path = FIXTURES_DIR / f"{stage.value}_v1.json"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
    actual = bundle.model_dump(mode="json")

    assert actual == expected


def test_list_rca_prompt_versions_includes_v1() -> None:
    assert "v1" in list_rca_prompt_versions()


def test_rca_prompt_version_from_settings() -> None:
    settings = Settings(rca_prompt_version="v1")
    assert rca_prompt_version_from_settings(settings) == "v1"


def test_render_rca_prompt_rejects_unknown_version() -> None:
    with pytest.raises(RCAPromptError, match="unknown RCA prompt version"):
        render_rca_prompt(
            RCAPromptStage.SYMPTOM_EXTRACTION,
            version="v99",
            context=prompt_context_from_values(evidence_package_json="{}"),
        )


def test_render_rca_prompt_requires_context_fields() -> None:
    with pytest.raises(RCAPromptError, match="missing required prompt context"):
        render_rca_prompt(
            RCAPromptStage.HYPOTHESIS_GENERATION,
            version="v1",
            context=RCAPromptContext(evidence_package_json="{}"),
        )


def test_render_rca_prompt_substitutes_evidence_package() -> None:
    evidence = EVIDENCE_PACKAGE_FIXTURE.read_text(encoding="utf-8")

    bundle = render_rca_prompt(
        RCAPromptStage.SYMPTOM_EXTRACTION,
        version="v1",
        context=prompt_context_from_values(evidence_package_json=evidence),
    )

    assert '"incident"' in bundle.user_prompt
    assert "Checkout failures" in bundle.user_prompt
    assert "{{" not in bundle.user_prompt
    assert "{{" not in bundle.system_prompt


def test_shared_guardrails_loaded_once() -> None:
    _load_shared_guardrails.cache_clear()
    first = _load_shared_guardrails("v1")
    second = _load_shared_guardrails("v1")
    assert first == second
    assert "Use only the evidence explicitly supplied" in first

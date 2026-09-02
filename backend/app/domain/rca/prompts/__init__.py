"""Versioned RCA prompt loading and rendering."""

from __future__ import annotations

import enum
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_PROMPTS_ROOT = Path(__file__).resolve().parent
_SHARED_GUARDRAILS_FILE = "shared_guardrails.txt"


class RCAPromptStage(enum.StrEnum):
    """Stages in the multi-step RCA prompt pipeline."""

    SYMPTOM_EXTRACTION = "symptom_extraction"
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    EVIDENCE_EVALUATION = "evidence_evaluation"
    FINAL_RCA = "final_rca"
    REPORT_GENERATION = "report_generation"


_STAGE_REQUIRED_FIELDS: dict[RCAPromptStage, tuple[str, ...]] = {
    RCAPromptStage.SYMPTOM_EXTRACTION: ("evidence_package_json",),
    RCAPromptStage.HYPOTHESIS_GENERATION: (
        "evidence_package_json",
        "symptoms_json",
    ),
    RCAPromptStage.EVIDENCE_EVALUATION: (
        "evidence_package_json",
        "hypotheses_json",
    ),
    RCAPromptStage.FINAL_RCA: (
        "evidence_package_json",
        "symptoms_json",
        "hypotheses_json",
        "evaluation_json",
    ),
    RCAPromptStage.REPORT_GENERATION: (
        "evidence_package_json",
        "rca_result_json",
    ),
}


class RCAPromptContext(BaseModel):
    """Template variables available when rendering RCA prompts."""

    model_config = ConfigDict(frozen=True)

    evidence_package_json: str = ""
    symptoms_json: str = ""
    hypotheses_json: str = ""
    evaluation_json: str = ""
    rca_result_json: str = ""


class RCAPromptBundle(BaseModel):
    """Rendered system and user prompts for one RCA stage."""

    model_config = ConfigDict(frozen=True)

    stage: RCAPromptStage
    version: str
    system_prompt: str
    user_prompt: str


class RCAPromptError(ValueError):
    """Raised when prompt loading or rendering fails."""


def list_rca_prompt_versions() -> list[str]:
    """Return available RCA prompt versions in sorted order."""

    return sorted(
        path.name
        for path in _PROMPTS_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def render_rca_prompt(
    stage: RCAPromptStage,
    *,
    version: str,
    context: RCAPromptContext,
) -> RCAPromptBundle:
    """Load and render the prompts for an RCA stage."""

    _validate_version(version)
    _validate_context(stage, context)

    guardrails = _load_shared_guardrails(version)
    system_template = _load_stage_file(version, stage, "system.txt")
    user_template = _load_stage_file(version, stage, "user.txt")

    render_context = _build_render_context(context, guardrails=guardrails)
    system_prompt = _render_template(system_template, render_context)
    user_prompt = _render_template(user_template, render_context)

    return RCAPromptBundle(
        stage=stage,
        version=version,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def prompt_context_from_values(**values: str) -> RCAPromptContext:
    """Build a prompt context from keyword arguments."""

    return RCAPromptContext.model_validate(values)


def _validate_version(version: str) -> None:
    if version not in list_rca_prompt_versions():
        available = ", ".join(list_rca_prompt_versions()) or "none"
        msg = f"unknown RCA prompt version {version!r}; available: {available}"
        raise RCAPromptError(msg)


def _validate_context(stage: RCAPromptStage, context: RCAPromptContext) -> None:
    missing = [
        field
        for field in _STAGE_REQUIRED_FIELDS[stage]
        if not getattr(context, field).strip()
    ]
    if missing:
        fields = ", ".join(missing)
        msg = f"missing required prompt context for {stage.value}: {fields}"
        raise RCAPromptError(msg)


def _build_render_context(
    context: RCAPromptContext,
    *,
    guardrails: str,
) -> dict[str, str]:
    return {
        "shared_guardrails": guardrails.strip(),
        "evidence_package_json": context.evidence_package_json.strip(),
        "symptoms_json": context.symptoms_json.strip(),
        "hypotheses_json": context.hypotheses_json.strip(),
        "evaluation_json": context.evaluation_json.strip(),
        "rca_result_json": context.rca_result_json.strip(),
    }


@lru_cache(maxsize=8)
def _load_shared_guardrails(version: str) -> str:
    path = _PROMPTS_ROOT / version / _SHARED_GUARDRAILS_FILE
    if not path.is_file():
        msg = f"missing shared guardrails for prompt version {version!r}"
        raise RCAPromptError(msg)
    return path.read_text(encoding="utf-8")


def _load_stage_file(version: str, stage: RCAPromptStage, filename: str) -> str:
    path = _PROMPTS_ROOT / version / stage.value / filename
    if not path.is_file():
        msg = (
            f"missing prompt file for version={version!r}, "
            f"stage={stage.value!r}, file={filename!r}"
        )
        raise RCAPromptError(msg)
    return path.read_text(encoding="utf-8")


def _render_template(template: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            msg = f"unknown prompt placeholder: {key!r}"
            raise RCAPromptError(msg)
        return context[key]

    rendered = _PLACEHOLDER_PATTERN.sub(replace, template)
    unresolved = _PLACEHOLDER_PATTERN.findall(rendered)
    if unresolved:
        keys = ", ".join(sorted(set(unresolved)))
        msg = f"unresolved prompt placeholders: {keys}"
        raise RCAPromptError(msg)
    return rendered.strip()

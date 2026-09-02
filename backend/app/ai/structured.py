"""Helpers for schema-constrained provider output."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.errors import (
    AIProviderResponseError,
    AIProviderStructuredOutputError,
)

_JSON_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def build_structured_prompt(
    request_prompt: str,
    *,
    response_model: type[BaseModel],
) -> str:
    """Augment a user prompt with JSON schema instructions."""

    schema = json.dumps(response_model.model_json_schema(), indent=2)
    return (
        f"{request_prompt.strip()}\n\n"
        "Respond with valid JSON only that matches this schema:\n"
        f"{schema}"
    )


def extract_json_object(content: str) -> dict[str, Any]:
    """Extract a JSON object from raw model text."""

    stripped = content.strip()
    if not stripped:
        msg = "provider returned empty content"
        raise AIProviderResponseError(msg)

    candidates = [stripped]
    block_match = _JSON_BLOCK_PATTERN.search(stripped)
    if block_match is not None:
        candidates.insert(0, block_match.group(1))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    msg = "provider response did not contain a JSON object"
    raise AIProviderStructuredOutputError(msg)


def validate_structured_output(
    payload: dict[str, Any],
    *,
    response_model: type[BaseModel],
) -> dict[str, Any]:
    """Validate provider JSON against a Pydantic model."""

    try:
        return response_model.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        msg = f"structured output failed validation: {exc}"
        raise AIProviderStructuredOutputError(msg) from exc

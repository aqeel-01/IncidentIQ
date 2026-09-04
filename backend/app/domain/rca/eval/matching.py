"""Title and evidence-key matching helpers for RCA evaluation."""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str) -> str:
    """Lowercase and collapse non-alphanumeric characters for fuzzy compare."""

    return _NON_ALNUM.sub(" ", value.lower()).strip()


def titles_match(predicted: str | None, gold_title: str, aliases: list[str]) -> bool:
    """Return True when predicted title matches gold or an alias."""

    if predicted is None:
        return False
    predicted_norm = normalize_text(predicted)
    if not predicted_norm:
        return False
    candidates = [gold_title, *aliases]
    for candidate in candidates:
        candidate_norm = normalize_text(candidate)
        if not candidate_norm:
            continue
        if (
            predicted_norm == candidate_norm
            or candidate_norm in predicted_norm
            or predicted_norm in candidate_norm
        ):
            return True
    return False


def find_matching_title(
    predicted_titles: list[str],
    gold_title: str,
    aliases: list[str],
) -> str | None:
    """Return the first predicted title that matches gold/aliases."""

    for title in predicted_titles:
        if titles_match(title, gold_title, aliases):
            return title
    return None


def evidence_keys_match(cited: str, valid: str) -> bool:
    """Return True when a cited evidence key matches a valid package key."""

    cited_norm = normalize_text(cited)
    valid_norm = normalize_text(valid)
    if not cited_norm or not valid_norm:
        return False
    return (
        cited_norm == valid_norm or cited_norm in valid_norm or valid_norm in cited_norm
    )


def filter_grounded_keys(cited_keys: list[str], valid_keys: list[str]) -> list[str]:
    """Return cited keys that match at least one valid evidence key."""

    grounded: list[str] = []
    for cited in cited_keys:
        if any(evidence_keys_match(cited, valid) for valid in valid_keys):
            grounded.append(cited)
    return grounded


def filter_matched_gold_keys(
    cited_keys: list[str],
    gold_keys: list[str],
) -> list[str]:
    """Return gold keys that were cited (fuzzy)."""

    matched: list[str] = []
    for gold in gold_keys:
        if any(evidence_keys_match(cited, gold) for cited in cited_keys):
            matched.append(gold)
    return matched

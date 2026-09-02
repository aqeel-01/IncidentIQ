"""Lightweight text embeddings for incident similarity."""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Tokenize normalized text for bag-of-words similarity."""

    return [
        token
        for token in _TOKEN_PATTERN.findall(text.casefold())
        if len(token) > 1
    ]


def term_frequency(tokens: list[str]) -> dict[str, float]:
    """Return normalized term frequencies for ``tokens``."""

    if not tokens:
        return {}

    counts = Counter(tokens)
    total = float(len(tokens))
    return {token: count / total for token, count in counts.items()}


def cosine_similarity(left: str, right: str) -> float:
    """Return cosine similarity between two text embeddings."""

    left_vector = term_frequency(tokenize(left))
    right_vector = term_frequency(tokenize(right))
    if not left_vector or not right_vector:
        return 0.0

    shared = set(left_vector) & set(right_vector)
    if not shared:
        return 0.0

    dot = sum(left_vector[token] * right_vector[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return round(dot / (left_norm * right_norm), 4)

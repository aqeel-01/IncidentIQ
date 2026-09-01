"""Infrastructure health checks used by the readiness endpoint.

Each check is small, independent, and returns a structured :class:`CheckResult`
instead of raising, so a single failing dependency cannot crash the endpoint.
Failures are captured explicitly (never silently swallowed) and surfaced in the
response for observability.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

# Bound every dependency probe so a hung service cannot block readiness.
_CHECK_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single dependency probe."""

    name: str
    healthy: bool
    required: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "required": self.required,
            "detail": self.detail,
        }


async def check_redis(settings: Settings) -> CheckResult:
    """Verify Redis accepts connections and responds to PING."""

    try:
        import redis.asyncio as redis
    except ImportError:  # pragma: no cover - dependency is declared in pyproject
        return CheckResult("redis", False, True, "redis client not installed")

    client = redis.from_url(settings.redis_url)
    try:
        await asyncio.wait_for(client.ping(), timeout=_CHECK_TIMEOUT_SECONDS)
        return CheckResult("redis", True, True, "ok")
    except TimeoutError:
        return CheckResult("redis", False, True, "timeout")
    except (OSError, redis.RedisError) as exc:
        return CheckResult("redis", False, True, f"unavailable: {exc}")
    finally:
        await client.aclose()


async def check_postgres(engine: AsyncEngine | None) -> CheckResult:
    """Verify PostgreSQL accepts connections via the application engine."""

    if engine is None:
        return CheckResult("postgres", False, True, "database engine not initialized")

    # Imported lazily so this module has no hard dependency on SQLAlchemy at
    # import time (keeps unit-testing individual checks cheap).
    from sqlalchemy.exc import SQLAlchemyError

    from app.db.session import check_connection

    try:
        await asyncio.wait_for(check_connection(engine), timeout=_CHECK_TIMEOUT_SECONDS)
        return CheckResult("postgres", True, True, "ok")
    except TimeoutError:
        return CheckResult("postgres", False, True, "timeout")
    except (OSError, SQLAlchemyError) as exc:
        return CheckResult("postgres", False, True, f"unavailable: {exc}")


async def run_readiness_checks(
    settings: Settings, engine: AsyncEngine | None
) -> list[CheckResult]:
    """Run all required dependency checks concurrently."""

    return list(
        await asyncio.gather(
            check_postgres(engine),
            check_redis(settings),
        )
    )

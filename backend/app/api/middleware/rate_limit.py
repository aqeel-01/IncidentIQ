"""In-memory rate limiting middleware for sensitive endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import Settings


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window counter keyed by arbitrary strings."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: float) -> bool:
        """Record a hit and return True when the request is allowed."""

        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_GLOBAL_LIMITER = SlidingWindowRateLimiter()


def get_rate_limiter() -> SlidingWindowRateLimiter:
    return _GLOBAL_LIMITER


def reset_rate_limiter() -> None:
    _GLOBAL_LIMITER.reset()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-IP limits to authentication and upload endpoints."""

    def __init__(
        self,
        app,
        settings: Settings,
        *,
        limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        super().__init__(app)
        self._settings = settings
        self._limiter = limiter or get_rate_limiter()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        rule = self._match_rule(request.url.path, request.method)
        if rule is not None:
            limit, window_seconds, name = rule
            key = f"{name}:{_client_key(request)}"
            if not self._limiter.hit(
                key,
                limit=limit,
                window_seconds=window_seconds,
            ):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "rate limit exceeded; try again later"},
                    headers={"Retry-After": str(int(window_seconds))},
                )
        return await call_next(request)

    def _match_rule(
        self,
        path: str,
        method: str,
    ) -> tuple[int, float, str] | None:
        method = method.upper()
        if method == "POST" and path == "/api/v1/auth/login":
            return (
                self._settings.auth_login_rate_limit,
                float(self._settings.auth_rate_limit_window_seconds),
                "auth-login",
            )
        if method == "POST" and path == "/api/v1/auth/bootstrap":
            return (
                self._settings.auth_bootstrap_rate_limit,
                float(self._settings.auth_rate_limit_window_seconds),
                "auth-bootstrap",
            )
        if method == "POST" and path == "/api/v1/logs/upload":
            return (
                self._settings.upload_rate_limit,
                float(self._settings.upload_rate_limit_window_seconds),
                "upload",
            )
        return None

"""HTTP metrics middleware."""

from __future__ import annotations

import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import observe_http_request, should_track_http_path


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record API latency and error status codes for Prometheus."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        if not should_track_http_path(request.url.path):
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            observe_http_request(
                method=request.method,
                status_code=status_code,
                duration_seconds=time.perf_counter() - start,
            )

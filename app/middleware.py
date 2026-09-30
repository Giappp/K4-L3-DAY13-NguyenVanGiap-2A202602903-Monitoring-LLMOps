from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_contextvars()

        # Extract x-request-id from headers or generate a new one
        # Use format: req-<8-char-hex>
        req_header = request.headers.get("x-request-id", "").strip()
        correlation_id = req_header if req_header else f"req-{uuid.uuid4().hex[:8]}"
        
        bind_contextvars(correlation_id=correlation_id)
        
        request.state.correlation_id = correlation_id
        
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        

        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = f"{duration_ms:.2f}"
        
        return response

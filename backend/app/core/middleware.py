"""Bounded request intake, per-process abuse limits and privacy-preserving tracing."""

import asyncio
import logging
import math
import re
import time
from collections import Counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders

from app.core.errors import error_response

logger = logging.getLogger("mathclub.requests")
RID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{8,80}$")


class WindowLimiter:
    """Fixed window per peer IP; deliberately ignores untrusted forwarding headers."""

    def __init__(self):
        self.buckets = {}

    def allow(self, key, limit, now):
        if not limit:
            return True, 0
        if len(self.buckets) >= 10000:
            self.buckets = {k: v for k, v in self.buckets.items() if now - v[0] < 60}
            if key not in self.buckets and len(self.buckets) >= 10000:
                return False, 60
        start, count = self.buckets.get(key, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        if count >= limit:
            return False, max(1, math.ceil(60 - (now - start)))
        self.buckets[key] = (start, count + 1)
        return True, 0


class RuntimeStats:
    def __init__(self):
        self.started = time.monotonic()
        self.status_counts = Counter()
        self.requests = 0
        self.duration_ms = 0.0

    def snapshot(self):
        return {
            "scope": "single_process",
            "uptime_seconds": round(time.monotonic() - self.started, 1),
            "requests": self.requests,
            "status_counts": dict(self.status_counts),
            "total_duration_ms": round(self.duration_ms, 1),
        }


class GuardMiddleware:
    def __init__(self, app, settings, stats):
        self.app, self.settings, self.stats = app, settings, stats
        self.limiter = WindowLimiter()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cfg = self.settings
        headers = Headers(scope=scope)
        supplied = headers.get("X-Request-ID", "")
        rid = supplied if RID_PATTERN.fullmatch(supplied) else str(uuid4())
        scope.setdefault("state", {})["request_id"] = rid
        started, status, sent = time.monotonic(), 500, False

        async def traced_send(message):
            nonlocal status, sent
            if message["type"] == "http.response.start":
                sent = True
                status = message["status"]
                out = MutableHeaders(scope=message)
                out["X-Request-ID"] = rid
                out["X-Content-Type-Options"] = "nosniff"
                out["Cache-Control"] = "no-store"
            await send(message)

        async def reject(status, code, message, extra=None):
            await error_response(rid, status, code, message, headers=extra)(
                scope, receive, traced_send
            )

        try:
            internal = scope["path"].startswith("/internal/")
            guarded = internal or scope["path"].startswith("/api/")
            if guarded and scope["method"] != "OPTIONS":
                peer = (scope.get("client") or ("unknown",))[0]
                limit = (
                    cfg.internal_rate_limit_per_minute if internal else cfg.rate_limit_per_minute
                )
                allowed, retry = self.limiter.allow((internal, peer), limit, started)
                if not allowed:
                    return await reject(
                        429, "RATE_LIMITED", "Too many requests", {"Retry-After": str(retry)}
                    )
            max_size = cfg.max_internal_request_bytes if internal else cfg.max_request_bytes
            length = headers.get("content-length")
            if length is not None:
                try:
                    size = int(length)
                except ValueError:
                    return await reject(400, "BAD_REQUEST", "Invalid Content-Length")
                if size < 0:
                    return await reject(400, "BAD_REQUEST", "Invalid Content-Length")
                if size > max_size:
                    return await reject(
                        413, "PAYLOAD_TOO_LARGE", "Request body exceeds configured limit"
                    )
            # Bound even chunked requests before parsing; the full payload is never logged.
            body = bytearray()
            try:
                async with asyncio.timeout(cfg.request_body_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        body.extend(message.get("body", b""))
                        if len(body) > max_size:
                            return await reject(
                                413, "PAYLOAD_TOO_LARGE", "Request body exceeds configured limit"
                            )
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "REQUEST_TIMEOUT", "Request body timed out")
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            try:
                async with asyncio.timeout(cfg.request_timeout_seconds):
                    await self.app(scope, replay, traced_send)
            except TimeoutError:
                if sent:
                    raise
                await reject(504, "REQUEST_TIMEOUT", "Request processing timed out")
            except Exception as exc:
                if sent:
                    raise
                # Exception repr/stack may contain private query data from injected providers.
                logger.error("request_failed type=%s trace=%s", type(exc).__name__, rid)
                await reject(500, "INTERNAL_ERROR", "An unexpected server error occurred")
        finally:
            elapsed = (time.monotonic() - started) * 1000
            self.stats.requests += 1
            self.stats.status_counts[str(status)] += 1
            self.stats.duration_ms += elapsed
            route = scope.get("route")
            logger.info(
                "method=%s route=%s status=%s duration_ms=%.1f trace=%s",
                scope["method"],
                getattr(route, "path", "unmatched"),
                status,
                elapsed,
                rid,
            )

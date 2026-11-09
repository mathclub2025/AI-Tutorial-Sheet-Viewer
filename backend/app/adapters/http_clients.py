"""Bounded HTTP contracts with read retries and a per-service circuit breaker."""

import asyncio
import time
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.core.errors import ServiceError
from app.domain.models import (
    AgentAnswer,
    AgentDocumentJobAck,
    DocumentJobStatus,
    DocumentResultAck,
    FilterCatalog,
    Question,
    SearchEnvelope,
)


class CircuitBreaker:
    def __init__(self, threshold=5, reset_seconds=30):
        self.threshold, self.reset_seconds = threshold, reset_seconds
        self.failures, self.opened_at, self.probing = 0, None, False

    def enter(self):
        if self.opened_at is not None:
            if time.monotonic() - self.opened_at < self.reset_seconds or self.probing:
                raise ServiceError(
                    "CIRCUIT_OPEN", "An upstream service is temporarily unavailable", 503
                )
            self.probing = True

    def success(self):
        self.failures, self.opened_at, self.probing = 0, None, False

    def failure(self):
        self.failures += 1
        if self.probing or self.failures >= self.threshold:
            self.opened_at = time.monotonic()
        self.probing = False

    def release(self):
        self.probing = False


def parse(model, payload):
    try:
        return model.model_validate(payload)
    except (ValidationError, TypeError, ValueError) as exc:
        raise ServiceError(
            "INVALID_UPSTREAM_RESPONSE", "Upstream response does not match contract", 502
        ) from exc


class BaseHTTPAdapter:
    def __init__(
        self, base_url, client: httpx.AsyncClient, token=None, *, settings=None, circuit=None
    ):
        self.base_url, self.client, self.token = base_url.rstrip("/"), client, token
        self.config = settings or Settings(_env_file=None)
        self.circuit = circuit or CircuitBreaker(
            self.config.circuit_failure_threshold, self.config.circuit_reset_seconds
        )

    async def request(
        self,
        method,
        path,
        trace_id,
        *,
        json=None,
        params=None,
        retry_safe=False,
        allow_not_found=False,
        allow_conflict=False,
    ):
        headers = {"X-Request-ID": trace_id}
        if self.token:
            headers["X-Internal-Token"] = self.token
        self.circuit.enter()
        tries = 1 + (self.config.upstream_read_retries if retry_safe else 0)
        try:
            for attempt in range(tries):
                try:
                    # Never follow redirects carrying internal credentials; stream to bound decoded bytes.
                    async with self.client.stream(
                        method,
                        self.base_url + path,
                        headers=headers,
                        json=json,
                        params=params,
                        timeout=self.config.upstream_timeout_seconds,
                        follow_redirects=False,
                    ) as response:
                        if response.status_code == 404 and allow_not_found:
                            self.circuit.success()
                            return None
                        if response.status_code == 409 and allow_conflict:
                            raise ServiceError(
                                "UPSTREAM_CONFLICT",
                                "Request conflicts with upstream state",
                                409,
                            )
                        if response.status_code in {429, 502, 503, 504}:
                            raise ServiceError(
                                "DEPENDENCY_UNAVAILABLE",
                                "An upstream service is temporarily unavailable",
                                503,
                            )
                        if not 200 <= response.status_code < 300:
                            raise ServiceError(
                                "UPSTREAM_ERROR", "An upstream service rejected the request", 502
                            )
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.config.upstream_max_response_bytes:
                                raise ServiceError(
                                    "INVALID_UPSTREAM_RESPONSE",
                                    "Upstream response exceeds the size limit",
                                    502,
                                )
                        import json as json_module

                        try:
                            payload = json_module.loads(body)
                        except (ValueError, UnicodeDecodeError) as exc:
                            raise ServiceError(
                                "INVALID_UPSTREAM_RESPONSE", "Upstream returned invalid JSON", 502
                            ) from exc
                        if payload is None:
                            raise ServiceError(
                                "INVALID_UPSTREAM_RESPONSE", "Upstream returned null", 502
                            )
                        self.circuit.success()
                        return payload
                except httpx.TimeoutException:
                    error = ServiceError("UPSTREAM_TIMEOUT", "An upstream service timed out", 504)
                except httpx.RequestError:
                    error = ServiceError(
                        "DEPENDENCY_UNAVAILABLE", "An upstream service is unreachable", 503
                    )
                except ServiceError as exc:
                    error = exc
                if error.status_code not in {503, 504} or attempt + 1 == tries:
                    if error.status_code in {502, 503, 504}:
                        self.circuit.failure()
                    else:
                        self.circuit.success()
                    raise error
                await asyncio.sleep(0.05 * (attempt + 1))
        finally:
            self.circuit.release()


class HTTPQuestions(BaseHTTPAdapter):
    async def search(self, request, trace_id):
        payload = await self.request(
            "POST",
            "/internal/v1/search",
            trace_id,
            json=request.model_dump(mode="json"),
            retry_safe=True,
        )
        return parse(SearchEnvelope, payload).items

    async def get(self, question_id, trace_id):
        payload = await self.request(
            "GET",
            f"/internal/v1/questions/{quote(question_id, safe='')}",
            trace_id,
            retry_safe=True,
            allow_not_found=True,
        )
        return parse(Question, payload) if payload is not None else None

    async def similar(self, question_id, limit, trace_id):
        payload = await self.request(
            "GET",
            f"/internal/v1/questions/{quote(question_id, safe='')}/similar",
            trace_id,
            params={"limit": limit},
            retry_safe=True,
        )
        return parse(SearchEnvelope, payload).items

    async def catalog(self, trace_id):
        return parse(
            FilterCatalog,
            await self.request("GET", "/internal/v1/catalog", trace_id, retry_safe=True),
        )


class HTTPAI(BaseHTTPAdapter):
    async def answer(self, request):
        return parse(
            AgentAnswer,
            await self.request(
                "POST",
                "/internal/v1/answer",
                request.request_id,
                json=request.model_dump(mode="json"),
            ),
        )

    async def explain(self, request):
        return parse(
            AgentAnswer,
            await self.request(
                "POST",
                "/internal/v1/explain",
                request.request_id,
                json=request.model_dump(mode="json"),
            ),
        )


class HTTPCapture(BaseHTTPAdapter):
    async def record(self, event):
        payload = await self.request(
            "POST",
            "/internal/v1/query-events",
            event.request_id,
            json=event.model_dump(mode="json"),
        )
        if not isinstance(payload, dict) or payload.get("accepted") is not True:
            raise ServiceError("CAPTURE_FAILED", "Query event was not acknowledged", 502)
        return True


class HTTPDocumentJobs(BaseHTTPAdapter):
    async def submit(self, request):
        return parse(
            AgentDocumentJobAck,
            await self.request(
                "POST",
                "/internal/v1/document-jobs",
                request.request_id,
                json=request.model_dump(mode="json"),
                allow_conflict=True,
            ),
        )

    async def get(self, job_id, trace_id):
        payload = await self.request(
            "GET",
            f"/internal/v1/document-jobs/{quote(job_id, safe='')}",
            trace_id,
            retry_safe=True,
            allow_not_found=True,
        )
        return parse(DocumentJobStatus, payload) if payload is not None else None


class HTTPDocumentResults(BaseHTTPAdapter):
    async def accept(self, event):
        return parse(
            DocumentResultAck,
            await self.request(
                "POST",
                "/internal/v1/document-results",
                event.request_id,
                json=event.model_dump(mode="json"),
                allow_conflict=True,
            ),
        )


class HTTPHealth:
    """Readiness bypasses circuits; requires both peers to report ready."""

    def __init__(self, client, settings):
        self.client, self.config = client, settings

    async def check(self, trace_id):
        async def one(base, token):
            try:
                # A small independent total deadline also bounds a slow streaming dependency.
                async with asyncio.timeout(self.config.health_timeout_seconds):
                    async with self.client.stream(
                        "GET",
                        base.rstrip("/") + "/health/ready",
                        headers={"X-Internal-Token": token or "", "X-Request-ID": trace_id},
                        timeout=self.config.health_timeout_seconds,
                        follow_redirects=False,
                    ) as response:
                        if response.status_code != 200:
                            return False
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 4096:
                                return False
                        import json

                        return json.loads(body).get("status") == "ready"
            except (httpx.RequestError, TimeoutError, ValueError, AttributeError):
                return False

        p2, ai = await asyncio.gather(
            one(self.config.person2_base_url, self.config.token_for("person2_service_token")),
            one(self.config.ai_base_url, self.config.token_for("ai_service_token")),
        )
        return {"person2": p2, "ai": ai}

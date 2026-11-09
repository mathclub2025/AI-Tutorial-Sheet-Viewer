"""Expose the data service's typed admin contract at the existing gateway origin.

Only explicitly registered management routes are forwarded. Human bearer tokens
are passed through; no service credential is exposed or accepted as an admin login.
"""

import inspect
import json

import httpx
from fastapi import Request, Security
from fastapi.responses import JSONResponse

from app.core.errors import ServiceError
from app.data_service.auth import bearer
from app.data_service.management_api import router as management_router
from app.domain.models import ErrorBody


async def relay(request: Request):
    cfg = request.app.state.settings
    client = request.app.state.integration_client
    if client is None or not cfg.person2_base_url:
        raise ServiceError(
            "ADMIN_NOT_CONFIGURED", "Admin APIs require the configured data service", 503
        )
    headers = {"X-Request-ID": request.state.request_id}
    if request.headers.get("authorization"):
        headers["Authorization"] = request.headers["authorization"]
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]
    try:
        async with client.stream(
            request.method,
            cfg.person2_base_url.rstrip("/") + request.url.path,
            params=request.query_params.multi_items(),
            headers=headers,
            content=await request.body(),
            follow_redirects=False,
            timeout=cfg.management_timeout_seconds,
        ) as upstream:
            body = bytearray()
            async for chunk in upstream.aiter_bytes():
                body.extend(chunk)
                if len(body) > cfg.upstream_max_response_bytes:
                    raise ServiceError(
                        "INVALID_UPSTREAM_RESPONSE", "Admin response exceeds the size limit", 502
                    )
            try:
                data = json.loads(body)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ServiceError(
                    "INVALID_UPSTREAM_RESPONSE", "Admin service returned invalid JSON", 502
                ) from exc
            if upstream.status_code >= 400:
                try:
                    error = ErrorBody.model_validate(data)
                except ValueError as exc:
                    raise ServiceError(
                        "INVALID_UPSTREAM_RESPONSE", "Admin service returned an invalid error", 502
                    ) from exc
                error.request_id = request.state.request_id
                return JSONResponse(status_code=upstream.status_code, content=error.model_dump())
            if not 200 <= upstream.status_code < 300:
                raise ServiceError(
                    "INVALID_UPSTREAM_RESPONSE", "Admin service returned an unexpected status", 502
                )
            return data
    except httpx.TimeoutException as exc:
        raise ServiceError("UPSTREAM_TIMEOUT", "Admin service timed out", 504) from exc
    except httpx.RequestError as exc:
        raise ServiceError("DEPENDENCY_UNAVAILABLE", "Admin service is unreachable", 503) from exc


def install_management_proxy(app):
    for route in management_router.routes:

        async def endpoint(**kwargs):
            return await relay(kwargs["request"])

        # Reuse the source contract, excluding server-only dependency parameters.
        # This prevents schemas drifting between the gateway and data service.
        signature = inspect.signature(route.endpoint)
        parameters = [
            p
            for p in signature.parameters.values()
            if p.name not in {"session", "user", "credential"}
        ]
        if not any(p.name == "request" for p in parameters):
            parameters.append(
                inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY, annotation=Request)
            )
        endpoint.__signature__ = signature.replace(parameters=parameters)
        endpoint.__name__ = "proxy_" + route.name
        app.add_api_route(
            route.path,
            endpoint,
            methods=sorted(route.methods),
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            responses=route.responses,
            dependencies=[] if route.path.endswith("/auth/login") else [Security(bearer)],
            summary=route.summary or route.name.replace("_", " ").title(),
        )

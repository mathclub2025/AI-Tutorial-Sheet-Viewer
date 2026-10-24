"""FastAPI application factory with injectable cross-team interfaces."""

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.adapters.demo import DemoAI, DemoQuestions
from app.adapters.http_clients import (
    HTTPAI,
    CircuitBreaker,
    HTTPCapture,
    HTTPDocumentJobs,
    HTTPDocumentResults,
    HTTPHealth,
    HTTPQuestions,
)
from app.adapters.unconfigured import NoopCapture, UnconfiguredAI, UnconfiguredQuestions
from app.api.routes import internal_router, router
from app.config import BackendMode, Settings
from app.core.errors import (
    ServiceError,
    http_error_handler,
    service_error_handler,
    validation_error_handler,
)
from app.core.middleware import GuardMiddleware, RuntimeStats
from app.services.documents import DocumentOrchestrator
from app.services.orchestrator import Orchestrator

logger = logging.getLogger("mathclub")


def create_app(
    settings: Settings | None = None,
    *,
    questions: Any = None,
    ai: Any = None,
    capture: Any = None,
    document_jobs: Any = None,
    document_results: Any = None,
    health: Any = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    config = settings or Settings()
    api = FastAPI(
        title=config.app_name,
        version="0.2.0",
        lifespan=None,
        description="MathClub integration API. Database, storage and AI models are external.",
    )
    api.state.settings = config
    api.state.stats = RuntimeStats()
    injected = (questions, ai, capture, document_jobs, document_results, health)

    @asynccontextmanager
    async def lifespan(app):
        q, a, c, jobs, results, checks = injected
        owns_client = http_client is None and config.backend_mode == BackendMode.HTTP
        client = http_client
        if owns_client:
            client = httpx.AsyncClient(
                timeout=config.upstream_timeout_seconds,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                follow_redirects=False,
                trust_env=False,
            )
        try:
            if config.backend_mode == BackendMode.DEMO:
                q, a = q or DemoQuestions(), a or DemoAI()
            elif config.backend_mode == BackendMode.HTTP:
                p2_circuit = CircuitBreaker(
                    config.circuit_failure_threshold, config.circuit_reset_seconds
                )
                ai_circuit = CircuitBreaker(
                    config.circuit_failure_threshold, config.circuit_reset_seconds
                )
                p2_options = dict(settings=config, circuit=p2_circuit)
                ai_options = dict(settings=config, circuit=ai_circuit)
                p2_token, ai_token = (
                    config.token_for("person2_service_token"),
                    config.token_for("ai_service_token"),
                )
                q = q or HTTPQuestions(config.person2_base_url, client, p2_token, **p2_options)
                a = a or HTTPAI(config.ai_base_url, client, ai_token, **ai_options)
                c = c or HTTPCapture(config.person2_base_url, client, p2_token, **p2_options)
                jobs = jobs or HTTPDocumentJobs(config.ai_base_url, client, ai_token, **ai_options)
                results = results or HTTPDocumentResults(
                    config.person2_base_url, client, p2_token, **p2_options
                )
                checks = checks or HTTPHealth(client, config)
            else:
                q, a = q or UnconfiguredQuestions(), a or UnconfiguredAI()
            c = c or NoopCapture()
            app.state.orchestrator = Orchestrator(q, a, c, config.capture_required)
            app.state.documents = DocumentOrchestrator(jobs, results)
            app.state.health = checks
            app.state.capture_configured = not isinstance(c, NoopCapture)
            app.state.document_jobs_configured = jobs is not None
            yield
        finally:
            if owns_client:
                await client.aclose()

    api.router.lifespan_context = lifespan
    api.add_exception_handler(ServiceError, service_error_handler)
    api.add_exception_handler(RequestValidationError, validation_error_handler)
    api.add_exception_handler(HTTPException, http_error_handler)
    api.add_middleware(GuardMiddleware, settings=config, stats=api.state.stats)
    # Outer CORS includes errors produced by the guard (413/429/500/504).
    api.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=config.cors_allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    api.include_router(router)
    api.include_router(internal_router)

    @api.get("/health/live", tags=["Health"])
    async def live():
        return {"status": "alive", "service": "mathclub-api"}

    @api.get("/health/ready", tags=["Health"])
    async def ready(request: Request):
        if config.backend_mode == BackendMode.UNCONFIGURED:
            raise ServiceError("NOT_CONFIGURED", "Set BACKEND_MODE=demo or http", 503)
        checked, dependencies = False, {}
        if request.app.state.health is not None:
            dependencies = await request.app.state.health.check(request.state.request_id)
            checked = True
        is_ready = (
            all(dependencies.values()) if checked else config.backend_mode == BackendMode.DEMO
        )
        if config.capture_required and not request.app.state.capture_configured:
            is_ready = False
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={
                "status": "ready" if is_ready else "not_ready",
                "mode": config.backend_mode.value,
                "dependencies": dependencies,
                "upstream_reachability_checked": checked,
                "request_id": request.state.request_id,
            },
        )

    @api.get("/api/v1/capabilities", tags=["Health"])
    async def capabilities(request: Request):
        return {
            "mode": config.backend_mode.value,
            "features": ["catalog", "search", "ask", "question_detail", "similar", "explain"],
            "query_capture_required": config.capture_required,
            "capture_configured": request.app.state.capture_configured,
            "document_orchestration_configured": request.app.state.document_jobs_configured,
            "contract_version": "0.2.0",
        }

    return api


app = create_app()

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException

from app.core.errors import http_error_handler, validation_error_handler
from app.core.middleware import GuardMiddleware, RuntimeStats, WindowLimiter
from app.data_service.api import (
    install_data_service_error_handler,
    readiness,
    require_person1_token,
    router,
)
from app.data_service.ingestion_api import add_student_extensions
from app.data_service.ingestion_api import router as ingestion_router
from app.data_service.management_api import router as management_router
from app.data_service.semantic import LocalEmbeddings
from app.data_service.service import DataService
from app.data_service.settings import DataServiceSettings
from app.persistence.database import create_database_engine, create_session_factory
from app.storage.b2 import B2Storage, StorageError
from app.storage.settings import StorageSettings

add_student_extensions(router)


def create_data_app(
    settings: DataServiceSettings | None = None,
    *,
    engine: Engine | None = None,
    session_factory: sessionmaker | None = None,
    storage=None,
    embeddings=None,
) -> FastAPI:
    config = settings or DataServiceSettings()
    owns_engine = engine is None and session_factory is None
    database_engine = engine
    factory = session_factory or (
        create_session_factory(database_engine) if database_engine is not None else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_engine = database_engine
        if app.state.session_factory is None:
            active_engine = create_database_engine(config.database_url())
            app.state.session_factory = create_session_factory(active_engine)
        try:
            if app.state.storage is None:
                storage_config = StorageSettings()
                if storage_config.b2_endpoint_url:
                    app.state.storage = B2Storage(storage_config.to_b2_settings())
            yield
        finally:
            if owns_engine and active_engine is not None:
                active_engine.dispose()

    app = FastAPI(
        title="MathClub Person 2 Data Service",
        version="0.3.0",
        description="Canonical PostgreSQL-backed data service for the MathClub integration API.",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.session_factory = factory
    app.state.data_service = DataService()
    app.state.storage = storage
    app.state.embeddings = embeddings or LocalEmbeddings(config)
    app.state.stats = RuntimeStats()
    app.state.login_limiter = WindowLimiter()
    app.add_middleware(GuardMiddleware, settings=config, stats=app.state.stats)
    app.add_middleware(CORSMiddleware, allow_origins=config.allowed_origins,
                       allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
                       expose_headers=["X-Request-ID", "Retry-After"])
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        return JSONResponse(status_code=502, content={
            "error": "STORAGE_VERIFICATION_FAILED", "message": "Storage verification failed; retry or check the uploaded bytes",
            "request_id": request.state.request_id, "details": [],
        })

    app.include_router(router)
    app.include_router(management_router)
    app.include_router(ingestion_router)
    app.add_api_route(
        "/health/ready",
        readiness,
        methods=["GET"],
        tags=["Health"],
        dependencies=[Depends(require_person1_token)],
    )
    install_data_service_error_handler(app)
    return app


app = create_data_app()

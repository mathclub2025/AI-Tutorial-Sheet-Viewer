from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.data_service.api import (
    install_data_service_error_handler,
    readiness,
    require_person1_token,
    router,
)
from app.data_service.service import DataService
from app.data_service.settings import DataServiceSettings
from app.persistence.database import create_database_engine, create_session_factory


def create_data_app(
    settings: DataServiceSettings | None = None,
    *,
    engine: Engine | None = None,
    session_factory: sessionmaker | None = None,
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
            yield
        finally:
            if owns_engine and active_engine is not None:
                active_engine.dispose()

    app = FastAPI(
        title="MathClub Person 2 Data Service",
        version="0.1.0",
        description="Canonical PostgreSQL-backed data service for the MathClub integration API.",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.session_factory = factory
    app.state.data_service = DataService()
    app.include_router(router)
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

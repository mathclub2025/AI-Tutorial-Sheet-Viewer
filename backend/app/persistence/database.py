from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str, *, pool_size: int = 5) -> Engine:
    if not database_url:
        raise ValueError("DATABASE_URL must be configured")
    if not database_url.startswith(("postgresql+psycopg://", "sqlite:")):
        raise ValueError("DATABASE_URL must use PostgreSQL with psycopg or SQLite for tests")
    options = {"pool_pre_ping": True}
    if database_url.startswith("postgresql+psycopg://"):
        options["pool_size"] = pool_size
    return create_engine(database_url, **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with factory() as session:
        with session.begin():
            yield session

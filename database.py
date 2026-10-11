"""SQLAlchemy engine and session management."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from fastapi import HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

logger = logging.getLogger("tactivision.database")


class Base(DeclarativeBase):
    pass


engine = (
    create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        # Never wait forever for the database (a hung connection blocks the whole server).
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
    if settings.database_url
    else None
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False) if engine else None

if SessionLocal is not None and settings.database_rls:
    import rls

    rls.install(SessionLocal)


def get_db() -> Iterator[Session]:
    if SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured (set DATABASE_URL).",
        )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_database_status() -> str:
    """Same contract as the original prototype: CONNECTED only if system_status says ACTIVE."""
    if engine is None:
        return "DISCONNECTED"
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT status FROM system_status WHERE name = 'TactiVision'")
            ).fetchone()
        return "CONNECTED" if row and row[0] == "ACTIVE" else "DISCONNECTED"
    except Exception as error:
        logger.warning("Database check failed: %s", str(error).strip().splitlines()[0][:300])
        return "DISCONNECTED"

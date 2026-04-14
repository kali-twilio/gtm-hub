from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_db_url = os.environ.get("SE_ASSIST_DATABASE_URL", "sqlite:///se_assist.db")

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
)

# Enable WAL mode for better concurrent read/write on SQLite
if "sqlite" in _db_url:
    @event.listens_for(engine, "connect")
    def _set_sqlite_wal(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    return SessionLocal()


def init_db():
    """Create all tables if they don't exist."""
    from . import models  # noqa: F401 — import so Base.metadata knows about them
    Base.metadata.create_all(bind=engine)

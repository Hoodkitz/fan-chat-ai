"""Database engine and session management.

The application connects as a non-superuser role so PostgreSQL RLS applies.
Each session carries an RLS context (tenant_id, user_id) in ``session.info``.
It is applied with ``set_config(..., is_local => true)`` at the start of every
transaction, so it never leaks across pooled connections.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()

_SET_CTX = text(
    "SELECT set_config('app.tenant_id', :t, true), set_config('app.user_id', :u, true)"
)


@event.listens_for(Session, "after_begin")
def _apply_context(session: Session, transaction, connection) -> None:
    ctx = session.info.get("rls")
    # set_config is a PostgreSQL-specific function. When running with SQLite
    # (tests, local sqlite file) the function does not exist and would raise
    # an OperationalError. Only execute the SET when the DB dialect supports
    # it (PostgreSQL).
    if ctx is None:
        return
    try:
        dialect_name = connection.dialect.name
    except Exception:
        dialect_name = None
    if dialect_name != "postgresql":
        return
    connection.execute(_SET_CTX, {"t": ctx[0] or "", "u": ctx[1] or ""})


def set_context(db: Session, tenant_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """Change the RLS context of a session (applies now and to later transactions)."""
    ctx = (str(tenant_id) if tenant_id else None, str(user_id) if user_id else None)
    db.info["rls"] = ctx
    # Only attempt to set Postgres session config when the connection supports it.
    try:
        dial_name = db.bind.dialect.name if db.bind is not None else None
    except Exception:
        dial_name = None
    if dial_name == "postgresql":
        db.execute(_SET_CTX, {"t": ctx[0] or "", "u": ctx[1] or ""})


def new_session(tenant_id: Optional[str] = None, user_id: Optional[str] = None) -> Session:
    db = SessionLocal()
    db.info["rls"] = (str(tenant_id) if tenant_id else None, str(user_id) if user_id else None)
    return db


@contextmanager
def scoped_session(tenant_id: Optional[str] = None, user_id: Optional[str] = None) -> Iterator[Session]:
    """Session with RLS context; commits on success, rolls back on error."""
    db = new_session(tenant_id, user_id)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

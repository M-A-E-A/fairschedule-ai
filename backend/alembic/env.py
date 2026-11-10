"""Alembic environment for FairSchedule AI.

The database URL is read from the application settings (``DATABASE_URL``
environment variable / .env), the same single source of truth the app itself
uses, so migrations and the running API can never target different databases.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlmodel import SQLModel

# Make `app` importable when alembic runs from the backend directory.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.models import AuditEvent, Building, Campus, Course, Department, Institution, Lecturer, Room  # noqa: E402, F401
from app.models import ScheduleProposal, SessionBooking, StudentGroup, User  # noqa: E402, F401

config = context.config

target_metadata = SQLModel.metadata


def _database_url() -> str:
    return get_settings().database_url.replace('%', '%%')


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    from sqlalchemy import create_engine

    connectable = create_engine(_database_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

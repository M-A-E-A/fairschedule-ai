"""Run Alembic migrations at application startup.

``SQLModel.metadata.create_all`` is intentionally not used for schema
management: PostgreSQL deployments are migrated exclusively through Alembic
(``alembic upgrade head``), and the API runs the same command on startup so
the app and the migration chain can never drift apart.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def build_alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
    # The URL comes from the environment (single source of truth shared with
    # app.core.db); env.py reads the same setting.
    config.set_main_option('sqlalchemy.url', get_settings().database_url.replace('%', '%%'))
    return config


def run_migrations() -> None:
    command.upgrade(build_alembic_config(), 'head')
